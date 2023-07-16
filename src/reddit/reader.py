import logging
import re
import time
from datetime import datetime
from typing import List, Optional

import feedparser
import requests
from bs4 import BeautifulSoup, Tag
from markdownify import markdownify
from requests import HTTPError

from models.models import PostDTO, SORT_HOT, SORT_NEW, CommunityDTO
from reddit import USER_AGENT
from utils.exceptions import HttpNotFoundException

_DELAY_TIME = 3  # This many seconds between requests


class RedditReader:
    _SUBREDDIT_REGEX = re.compile(r'(.*reddit\.com/|^/?)r/([^/]+).*')
    _STRIP_EMPTY_REGEX = re.compile(r'\n{3,}')
    _next_request_after: int  # Updated on requests to reddit to prevent throttling

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': USER_AGENT})
        self._next_request_after = 0
        self.logger: logging.Logger = logging.getLogger(__name__)

    def _request(self, *args, allow_recurse=True, **kwargs):
        now = time.time()
        if now < self._next_request_after:
            self.logger.debug('Delaying next request')
            time.sleep(self._next_request_after - now)
        self._next_request_after = int(time.time()) + _DELAY_TIME
        response = self.session.request(*args, **kwargs)
        if 'over18' in response.url:
            if not allow_recurse:
                raise RecursionError('Reddit is trying to throw us into an infinite loop :(')
            response = self._request('POST', response.url, {'over18': 'yes'}, allow_recurse=False)

        response.raise_for_status()
        return response

    def get_subreddit_topics(self, subreddit: str, mode: str = SORT_HOT, since: datetime = None) -> List[PostDTO]:
        """Get a topics from a subreddit through its RSS feed"""
        if mode == SORT_NEW:
            feed_url = f"https://old.reddit.com/r/{subreddit}/new/.rss?sort=new"
        else:
            feed_url = f"https://old.reddit.com/r/{subreddit}/.rss"

        feed = feedparser.parse(self._request('GET', feed_url).text)

        posts = []
        for entry in feed.entries:
            created = datetime.fromisoformat(entry.published)
            updated = datetime.fromisoformat(entry.updated)
            author = entry.author if 'author' in entry else '[deleted]'
            if not since or updated > since:
                posts.append(PostDTO(reddit_link=entry.link, title=entry.title, created=created, updated=updated,
                                     author=author, upvote_ratio=1.0))
        return posts

    def get_subreddit_topics_json(self, subreddit: str, mode: str = SORT_HOT, since: datetime = None) -> List[PostDTO]:
        """Get topics from a subreddit through JSON"""
        if mode == SORT_NEW:
            feed_url = f"https://old.reddit.com/r/{subreddit}/new/.json?sort=new"
        else:
            feed_url = f"https://old.reddit.com/r/{subreddit}/.json"

        posts = []
        response = self._request('GET', feed_url).json();
        for entry in response.get('data', {}).get('children', {}):
            data = entry.get('data', [])
            posts.append(PostDTO(
                reddit_link='https://old.reddit.com' + data.get('permalink'),
                title=data.get('title'),
                created=datetime.fromtimestamp(data.get('created_utc')),
                updated=datetime.fromtimestamp(data.get('created_utc')),
                author='/u/' + data.get('author'),
                external_link=data.get('url', None),
                nsfw=data.get('over_18', None),
                upvotes=data.get('ups', 1),
                upvote_ratio=data.get('upvote_ratio', 0.5)
            ))
        return posts

    def get_post_details(self, post: PostDTO) -> PostDTO:
        """Enrich a PostDTO with all available extra data"""
        old_url = post.reddit_link.replace('www', 'old')
        response = self._request('GET', old_url)

        if response.status_code == 404:
            raise HttpNotFoundException(f"Couldn't find post on {old_url}", response=response, request=response.request)
        if response.status_code != 200:
            raise HTTPError(f"Couldn't retrieve post detail page: {response.status_code}")

        soup = BeautifulSoup(response.text, "html.parser")

        # Extract the body text if it exists
        body_text = soup.select_one('.expando form .md')
        post.body = self._html_node_to_markdown(body_text) if body_text else None

        # Extract other properties
        post_info = soup.select_one('div[data-timestamp][data-nsfw]')
        post.nsfw = post_info['data-nsfw'] != 'false'
        post.external_link = None if post_info['data-url'].startswith('/r/') else post_info['data-url']

        return post

    def get_subreddit_info(self, ident: str) -> Optional[CommunityDTO]:
        sub_url = f"https://old.reddit.com/r/{ident}/"
        response = self._request('GET', sub_url)
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        icon_elm = soup.select_one('img#header-img[src]')
        if icon_elm:
            icon = icon_elm['src']
            if icon.startswith('//'):
                icon = 'https:' + icon
        else:
            icon = None

        title = soup.select_one('head>title').text
        description = soup.select_one('head>meta[name="description"][content]')['content']
        nsfw = self.is_sub_nsfw(ident)

        return CommunityDTO(ident=ident, title=title, description=description, icon=icon, nsfw=nsfw)

    @classmethod
    def get_subreddit_ident(cls, link: str) -> str:
        """Extract the subreddit string from a path post"""
        match = cls._SUBREDDIT_REGEX.search(link)
        if match:
            return match.group(2)
        else:
            raise ValueError(f"No subreddit found in {link}")

    def _html_node_to_markdown(self, source: Tag) -> Optional[str]:
        """Convert the contents of a BeautifulSoup Tag into markdown"""
        # Make all links absolute
        for link in source.find_all('a', href=True):
            if str(link['href']).startswith('/'):
                link['href'] = 'https://old.reddit.com' + link['href']

        # Remove extraneous empty paragraphs
        html = str(source).replace('\u200B', '')
        markdown = markdownify(html)

        return self._STRIP_EMPTY_REGEX.sub('\n\n', markdown) if markdown else None

    def is_sub_nsfw(self, ident: str) -> bool:
        self.logger.debug(f"Running NSFW check on {ident}")
        nsfw_response = requests.get(f"https://old.reddit.com/r/{ident}/", headers={'User-Agent': USER_AGENT})

        return 'over18' in nsfw_response.url

