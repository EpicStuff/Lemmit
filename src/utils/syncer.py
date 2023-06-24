import logging
import re
import time
from datetime import datetime, timedelta
from operator import attrgetter
from typing import Type, List, Optional
from urllib.parse import urlparse

from requests import HTTPError
from sqlalchemy import or_
from sqlalchemy.orm import Session as DbSession

from lemmy.api import LemmyAPI
from models.models import Community, PostDTO, Post, CommunityDTO, SORT_HOT
from reddit.reader import RedditReader

NEW_SUB_CHECK_INTERVAL: int = 180  # Seconds between checking for new messages
PER_SUB_CHECK_INTERVAL: int = 600  # Minimal wait time before checking a subreddit for new posts

# This is a filter Lemmy uses - which unfortunately also blocks titles like 'uh oh', so a workaround is required.
VALID_TITLE = re.compile(r".*\S{3,}.*")


class Syncer:
    new_sub_check: int = None  # Last timestamp request checker ran

    def __init__(self, db: DbSession, reddit_reader: RedditReader, lemmy: LemmyAPI, request_community: str = None):
        self._db: DbSession = db
        self._reddit_reader: RedditReader = reddit_reader
        self._lemmy: LemmyAPI = lemmy
        self._logger = logging.getLogger(__name__)
        self.request_community = request_community
        self.lemmy_hostname: str = urlparse(lemmy.base_url).hostname

    def next_scrape_community(self) -> Optional[Type[Community]]:
        """Get the next community that is due for scraping."""
        return self._db.query(Community) \
            .filter(
            Community.enabled.is_(True),
            or_(
                Community.last_scrape <= datetime.utcnow() - timedelta(seconds=PER_SUB_CHECK_INTERVAL),
                Community.last_scrape.is_(None)
            )
        ) \
            .order_by(Community.last_scrape) \
            .first()

    def scrape_new_posts(self):
        community = self.next_scrape_community()

        if community:
            self._logger.info(f'Scraping subreddit: {community.ident}')
            try:
                posts = self._reddit_reader.get_subreddit_topics(community.ident, mode=community.sorting)
            except BaseException as e:
                self._logger.error(f"Error trying to retrieve topics: {str(e)}")
                return

            posts = self.filter_posted(posts)

            # Handle oldest entries first.
            posts = sorted(posts, key=attrgetter('updated'))

            for post in posts:
                self._logger.info(post)
                try:
                    post = self._reddit_reader.get_post_details(post)
                except BaseException as e:
                    self._logger.error(f"Error trying to retrieve post details, try again in a bit; {str(e)}")
                    return
                self.clone_to_lemmy(post, community)

            self._logger.info(f'Done.')
            community.last_scrape = datetime.utcnow()
            self._db.add(community)
            self._db.commit()
        else:
            self._logger.debug('No community due for update')

    def filter_posted(self, posts: List[PostDTO]) -> List[PostDTO]:
        """Filter out any posts that have already been synced to Lemmy"""
        reddit_links = [post.reddit_link for post in posts]
        existing_links_raw = self._db.query(Post.reddit_link).filter(Post.reddit_link.in_(reddit_links)).all()
        existing_links = [link[0] for link in existing_links_raw]

        filtered_posts = []
        for post in posts:
            if post.reddit_link not in existing_links:
                filtered_posts.append(post)
        return filtered_posts

    def clone_to_lemmy(self, post: PostDTO, community: Community):
        post = self.prepare_post(post, community)
        try:
            lemmy_post = self._lemmy.create_post(
                community_id=community.lemmy_id,
                name=post.title,
                body=post.body,
                url=post.external_link,
                nsfw=post.nsfw
            )
        except HTTPError as e:
            if e.response.status_code == 504 and 'Time-out' in str(e.response.text):
                # ron_burgundy_-_I_dont_believe_you.gif
                self._logger.warning(f'Timeout when trying to post {post.reddit_link}: {str(e)}\nSuuuure...')
                # TODO: check if post was actually placed through a search.
                #  If not, return, so it gets picked up next time
                lemmy_post = {'post_view': {'post': {'ap_id': f'https://some.post.in/{community.ident}'}}}  # hack
            else:
                self._logger.error(
                    f"HTTPError trying to post {post.reddit_link}: {str(e)}: {str(e.response.content)}"
                )
                return

        except Exception as e:
            self._logger.error(
                f"Something went horribly wrong when posting {post.reddit_link}: {str(e)}: {str(e.response.content)}"
            )
            return

        # Save post
        try:
            db_post = Post(reddit_link=post.reddit_link, lemmy_link=lemmy_post['post_view']['post']['ap_id'],
                           community=community, updated=datetime.utcnow(), nsfw=post.nsfw)
            self._db.add(db_post)
            self._db.commit()
        except Exception as e:
            print(f"Couldn't save {post.reddit_link} to local database. MUST REMOVE FROM LEMMY OR ELSE. {str(e)}")

    def check_new_subs(self):
        if self.new_sub_check is not None and (self.new_sub_check + NEW_SUB_CHECK_INTERVAL) > time.time():
            self._logger.debug('Not time yet for subreddit request check')
            return
        self._logger.info('Checking for new subreddit requests...')

        try:
            posts = self._get_new_sub_requests()
        except Exception as e:
            self._logger.error(f"Error trying to find new sub requests: {str(e)}")
            return

        for post in posts:
            self._logger.info('New subreddit request received')

            try:
                community = self.get_community_details_from_request_post(post)
            except SubredditRequestException as e:
                self._logger.error(str(e))
                self._lemmy.create_comment(post_id=post['post']['id'], content=str(e))
                self._lemmy.mark_post_as_read(post_id=post['post']['id'], read=True)
                continue

            try:
                lemmy_community = self._lemmy.create_community(
                    name=community.ident,
                    title=community.title,
                    description=community.description,
                    icon=community.icon,
                    nsfw=community.nsfw,
                    posting_restricted_to_mods=True
                )
                db_community = Community(
                    lemmy_id=lemmy_community['community_view']['community']['id'],
                    ident=community.ident,
                    nsfw=community.nsfw,
                    enabled=True,
                    sorting=SORT_HOT
                )
                self._db.add(db_community)
                self._db.commit()
            except Exception as e:
                self._logger.error(f'Error trying to create new community {community}: {str(e)}')
                self._lemmy.create_comment(
                    post_id=post['post']['id'],
                    content="Something went terribly wrong trying to create that community. "
                            f"[@admin@{self.lemmy_hostname}](https://{self.lemmy_hostname}/u/admin) I need an adult! :("
                )
                self._lemmy.mark_post_as_read(post_id=post['post']['id'], read=True)
                continue

            self._lemmy.create_comment(
                post_id=post['post']['id'],
                content=f"I'll get right on that. Check out "
                        f"{LemmyAPI.community_uri(community.ident, self.lemmy_hostname)}!\n\n"
                        f"[Click here to fetch this community](/search/q/!{community.ident}%40{self.lemmy_hostname}/"
                        f"type/All/sort/TopAll/listing_type/All/community_id/0/creator_id/0/page/1) for your Lemmy "
                        f"instance if you get a 404 error with the link above."
            )
            self._lemmy.mark_post_as_read(post_id=post['post']['id'], read=True)
        self.new_sub_check = int(time.time())
        self._logger.info('Done.')

    @staticmethod
    def prepare_post(post: PostDTO, community: Community) -> PostDTO:
        prefix = f"""##### This is an automated archive made by the [Lemmit Bot](https://lemmit.online/).
The original was posted on [/r/{community.ident}]({post.reddit_link.replace('https://www.', 'https://old.')}) by [{post.author}](https://old.reddit.com{post.author}) on {post.created}.\n"""
        if len(post.title) >= 200:
            prefix = prefix + f"\n**Original Title**: {post.title}\n"
            post.title = post.title[:196] + '...'
        elif not VALID_TITLE.match(post.title):
            prefix = prefix + f"\n**Original Title**: {post.title}\n"
            post.title = post.title.rstrip() + '...'
        if post.external_link and len(post.external_link) > 512:
            prefix = prefix + f"\n**Original URL**: {post.external_link}\n"
            post.external_link = None

        post.body = prefix + ('***\n' + post.body if post.body else '')

        if len(post.body) > 10000:
            post.body = post.body[:9800] + '...\n***\nContent cut off. Read original on ' + post.reddit_link

        return post

    def _get_new_sub_requests(self):
        posts = self._lemmy.get_posts(community_name=self.request_community, auth_required=True)

        ret_posts = []

        for post in posts['posts']:
            if post['read']:
                self._logger.debug(f"Already seen post {post['post']['name']}")
                continue
            ret_posts.append(post)

        return ret_posts

    def get_community_details_from_request_post(self, post: dict) -> CommunityDTO:
        """Create a new Lemmy Community based on request post"""
        # Try and extract the identifier
        ident = None
        if post['post']['url']:
            try:
                ident = RedditReader.get_subreddit_ident(post['post']['url']).lower()
            except ValueError:
                pass
        elif post['post']['name']:
            try:
                ident = RedditReader.get_subreddit_ident(post['post']['name']).lower()
            except ValueError:
                pass

        if not ident:
            raise SubredditRequestException(
                f"Couldn't determine subreddit. Try requesting with both the `url` "
                f"(https://old.reddit.com/r/whatever) and `title` (/r/whatever)."
            )

        # Skip existing
        if self.community_exists(ident):
            raise SubredditRequestException(
                f"There already is a '{ident}' community at {LemmyAPI.community_uri(ident, self.lemmy_hostname)}!"
            )

        # Figure out if subreddit exists and is open
        community = self._reddit_reader.get_subreddit_info(ident)
        if not community:
            raise SubredditRequestException(
                f'I cannot access https://old.reddit.com/r/{ident}. '
                'Does it exist and is it not private? Otherwise make a new request again later.'
            )
        self._logger.info(f"Success! Let's clone the sh!t out of {ident}")

        return community

    def community_exists(self, ident: str) -> bool:
        return self._db.query(Community).filter_by(ident=ident).first() is not None


class SubredditRequestException(Exception):
    """Exception when trying to add a new subreddit"""
