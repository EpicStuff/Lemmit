import logging
import unittest
from unittest.mock import MagicMock

from requests import HTTPError, Response
from sqlalchemy.orm import Session

from lemmy.api import LemmyAPI
from reddit.reader import RedditReader
from models.models import SORT_NEW
from tests import TEST_COMMUNITY, TEST_POSTS, LEMMY_POST_RETURN, TEST_COMMUNITY_DTO
from utils.syncer import Syncer, SubredditRequestException


class SyncerTestCase(unittest.TestCase):
    def setUp(self):
        # Set up the necessary mock objects
        self.db_session = MagicMock(spec=Session)
        self.reddit_reader = MagicMock(spec=RedditReader)
        self.lemmy_api = MagicMock(spec=LemmyAPI, base_url='https://foo.bar')

        # Create a Syncer instance for testing
        self.syncer = Syncer(db=self.db_session, reddit_reader=self.reddit_reader, lemmy=self.lemmy_api)
        self.syncer._logger = MagicMock(spec=logging.Logger)

    def test_scrape_new_posts(self):
        """Happy path"""
        # Mock the necessary objects
        self.reddit_reader.get_subreddit_topics.return_value = TEST_POSTS

        # Mock the return value of self.next_scrape_community
        self.syncer.next_scrape_community = MagicMock(return_value=TEST_COMMUNITY)

        # Call the method being tested
        self.syncer.scrape_new_posts()

        # Assert that the appropriate methods were called with the expected arguments
        self.reddit_reader.get_subreddit_topics.assert_called_once_with(TEST_COMMUNITY.ident, mode=SORT_NEW)
        self.lemmy_api.create_post.assert_called()

        # Assert that the expected number of posts were created
        self.assertEqual(self.lemmy_api.create_post.call_count, len(TEST_POSTS))
        self.syncer._logger.assert_not_called()

    def test_scrape_new_posts_get_subreddit_topics_error_fails_gracefully(self):
        # Mock the necessary objects
        self.reddit_reader.get_subreddit_topics.side_effect = HTTPError("Error")

        # Mock the return value of self.next_scrape_community
        self.syncer.next_scrape_community = MagicMock(return_value=TEST_COMMUNITY)

        # Call the method being tested
        self.syncer.scrape_new_posts()

        # Assert that the appropriate methods were called with the expected arguments
        self.reddit_reader.get_subreddit_topics.assert_called_once_with(TEST_COMMUNITY.ident, mode=SORT_NEW)
        self.lemmy_api.create_post.assert_not_called()
        self.syncer._logger.error.assert_called_once()

    def test_scrape_new_posts_get_post_details_error_fails_gracefully(self):
        # Mock the necessary objects
        self.reddit_reader.get_subreddit_topics.return_value = TEST_POSTS
        self.reddit_reader.get_post_details.side_effect = HTTPError("Error")

        # Mock the return value of self.next_scrape_community
        self.syncer.next_scrape_community = MagicMock(return_value=TEST_COMMUNITY)

        # Call the method being tested
        self.syncer.scrape_new_posts()

        # Assert that the appropriate methods were called with the expected arguments
        self.reddit_reader.get_subreddit_topics.assert_called_once_with(TEST_COMMUNITY.ident, mode=SORT_NEW)
        self.syncer._logger.error.assert_called_once()

        # Assert nothing else is done
        self.lemmy_api.create_post.assert_not_called()

    def test_clone_to_lemmy_success(self):
        # Mock the necessary objects
        post = TEST_POSTS[0]
        community = TEST_COMMUNITY

        # Mock the return values
        self.syncer.prepare_post.return_value = post
        self.lemmy_api.create_post.return_value = LEMMY_POST_RETURN

        # Call the method being tested
        self.syncer.clone_to_lemmy(post, community)

        # DB thinks everything is okay.
        self.db_session.add.return_value = None
        self.db_session.commit.return_value = None

        # Assert that the appropriate methods were called with the expected arguments
        self.lemmy_api.create_post.assert_called_once_with(
            community_id=community.lemmy_id,
            name=post.title,
            body=post.body,
            url=post.external_link,
            nsfw=post.nsfw
        )
        self.db_session.add.assert_called_once()
        self.db_session.commit.assert_called_once()

    def test_clone_to_lemmy_exception_in_create_post(self):
        # Mock the necessary objects
        post = TEST_POSTS[1]
        community = TEST_COMMUNITY

        # Mock the return value of self.prepare_post
        self.syncer.prepare_post.return_value = post

        # Mock an exception to be raised by self._lemmy.create_post
        response = Response()
        response.status_code = 500
        self.lemmy_api.create_post.side_effect = HTTPError("Error", response=response)

        # Call the method being tested
        self.syncer.clone_to_lemmy(post, community)

        # Assert that the appropriate methods were called with the expected arguments
        self.lemmy_api.create_post.assert_called_once_with(
            community_id=665,
            name='post 2',
            body=post.body,
            url='https://nope',
            nsfw=False
        )
        self.syncer._logger.error.assert_called_once_with('HTTPError trying to post https://red.dit/2: Error: None')
        self.db_session.add.assert_not_called()
        self.db_session.commit.assert_not_called()

    def test_clone_to_lemmy_timeout_is_ignored(self):
        # Mock the necessary objects
        post = TEST_POSTS[1]
        community = TEST_COMMUNITY

        # Mock the return value of self.prepare_post
        self.syncer.prepare_post.return_value = post

        # Mock an exception to be raised by self._lemmy.create_post
        response = MagicMock()
        response.status_code = 504
        response.text = b'<html>\r\n<head><title>504 Gateway Time-out</title></head>\r\n<body>\r\n<center><h1>504 ' \
                        b'Gateway Time-out</h1></center>\r\n<hr><center>openresty</center>\r\n</body>\r\n</html>\r\n'
        self.lemmy_api.create_post.side_effect = HTTPError(
            '504 Server Error: Gateway Time-out for url: https://foo.bar/api/v3/post', response=response
        )

        # Call the method being tested
        self.syncer.clone_to_lemmy(post, community)

        # Ensure logs and write to Database
        self.syncer._logger.warning.assert_called_once()
        self.db_session.add.assert_called()
        self.db_session.commit.assert_called()

    # New Subreddit requests
    def test_check_new_subs_no_new_requests(self):
        self.syncer._lemmy.get_posts = MagicMock(return_value={'posts': []})

        self.syncer.check_new_subs()

        self.syncer._lemmy.create_comment.assert_not_called()
        self.syncer._lemmy.mark_post_as_read.assert_not_called()

    def test_check_new_subs_with_new_requests(self):
        post_id = '12345'
        post = {
            'post': {
                'id': post_id,
                'url': f'https://old.reddit.com/r/{TEST_COMMUNITY_DTO.ident}/',
                'name': '',
            },
            'read': False
        }
        self.syncer._lemmy.get_posts = MagicMock(return_value={'posts': [post]})
        self.syncer.get_community_details_from_post = MagicMock(return_value=TEST_COMMUNITY_DTO)

        self.syncer.check_new_subs()

        self.syncer._lemmy.create_comment.assert_called_once_with(
            post_id=post_id,
            content="I'll get right on that. Check out [/c/test_subreddit@foo.bar](/c/test_subreddit@foo.bar)!"
        )
        self.syncer._lemmy.mark_post_as_read.assert_called_once_with(post_id=post_id, read=True)

    def test_check_new_subs_failed_community_details(self):
        post_id = '12345'
        post = {
            'post': {
                'id': post_id,
                'url': 'https://old.reddit.com/r/test/',
                'name': '',
            },
            'read': False
        }
        self.syncer._lemmy.get_posts = MagicMock(return_value={'posts': [post]})
        self.syncer.get_community_details_from_post = MagicMock(
            side_effect=SubredditRequestException('Failed to retrieve community details')
        )

        self.syncer.check_new_subs()

        self.syncer._lemmy.create_comment.assert_called_once_with(
            post_id=post_id,
            content='Failed to retrieve community details'
        )
        self.syncer._lemmy.mark_post_as_read.assert_called_once_with(post_id=post_id, read=True)

    def test_check_new_subs_failed_create_community(self):
        post_id = '12345'
        post = {
            'post': {
                'id': post_id,
                'url': 'https://old.reddit.com/r/test/',
                'name': '',
            },
            'read': False
        }
        self.syncer._lemmy.get_posts = MagicMock(return_value={'posts': [post]})
        self.syncer.get_community_details_from_post = MagicMock(return_value=TEST_COMMUNITY_DTO)

        self.syncer._lemmy.create_community = MagicMock(side_effect=Exception('Failed to create community'))

        self.syncer.check_new_subs()

        self.syncer._lemmy.create_comment.assert_called_once_with(
            post_id=post_id,
            content="Something went terribly wrong trying to create that community. "
                    "[@admin@foo.bar](https://foo.bar/u/admin) I need an adult! :("
        )

    # get_sub_details
    def test_get_sub_details_from_post_invalid_subreddit(self):
        post = {
            'post': {
                'url': 'https://old.reddit.com/r/existing/',
                'name': '/r/something_that_definitely_doesnt_exist'
            }
        }
        self.syncer._reddit_reader.get_subreddit_info = MagicMock(return_value=None)
        self.syncer.community_exists = MagicMock(return_value=False)

        with self.assertRaisesRegex(SubredditRequestException, r"Does it exist and is it not private?"):
            self.syncer.get_community_details_from_post(post)

    def test_get_sub_details_from_post_existing_community(self):
        post = {
            'post': {
                'url': 'https://old.reddit.com/r/already_existing/',
                'name': ''
            }
        }
        self.syncer._reddit_reader.get_subreddit_info = MagicMock(return_value=None)

        with self.assertRaisesRegex(SubredditRequestException, r"There already is a 'already_existing' community at"):
            self.syncer.get_community_details_from_post(post)


if __name__ == '__main__':
    unittest.main()


if __name__ == '__main__':
    unittest.main()
