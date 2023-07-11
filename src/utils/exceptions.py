from requests import HTTPError


class SubredditRequestException(Exception):
    """Exception when trying to add a new subreddit"""


class HttpNotFoundException(HTTPError):
    """More specific that HttpError"""
