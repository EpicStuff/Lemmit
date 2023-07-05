import os
import sys
from datetime import datetime

# Magically get the correct path.
PROJECT_PATH = os.getcwd()
SOURCE_PATH = os.path.join(PROJECT_PATH, "src")
sys.path.append(SOURCE_PATH)

from models.models import Community, PostDTO, CommunityDTO, CommunityStats

utc_now = datetime.utcnow()

TEST_COMMUNITY_DTO = CommunityDTO(ident="test_subreddit", title="Testy", description="We have all the testies.",
                                  icon='https://google.com/?search=balls.gif', nsfw=True)

TEST_COMMUNITY_STATS = CommunityStats(community_id=1, subscribers=55, posts_per_day=13)
TEST_COMMUNITY = Community(id=1, ident="test_subreddit", lemmy_id=665, nsfw=False, sorting='new', enabled=True, stats=TEST_COMMUNITY_STATS)
TEST_POSTS = [
    PostDTO(reddit_link='https://red.dit/1', title="post 1", author='/u/user1', created=utc_now, updated=utc_now,
            body="Lorem Ipsum is simply dummy text of the printing and typesetting industry. Lorem Ipsum has been the" + " industry's standard dummy text ever since the 1500s, when an unknown printer took a galley of type" + " and scrambled it to make a type specimen book. It has survived not only five centuries, but also t" + "he leap into electronic typesetting, remaining essentially unchanged. It was popularised in the 196" + "0s with the release of Letraset sheets containing Lorem Ipsum passages, and more recently with desk" + "top publishing software like Aldus PageMaker including versions of Lorem Ipsum."),
    PostDTO(reddit_link='https://red.dit/2', title="post 2", author='/u/user2', created=utc_now, updated=utc_now,
            external_link='https://nope'),
    PostDTO(reddit_link='https://red.dit/3', title="post 3", author='/u/user3', created=utc_now, updated=utc_now), ]

LEMMY_POST_RETURN = {'post_view': {'post': {'ap_id': 5, 'body': 'blabla'}}}


def get_test_data(filename: str) -> str:
    file_path = os.path.join(os.path.dirname(__file__), 'data', filename)
    with open(file_path, 'r') as file:
        return file.read()
