import logging
from datetime import datetime, timedelta
from operator import or_
from typing import List

from requests import HTTPError
from sqlalchemy import asc, func
from sqlalchemy.orm import Session as DbSession

from lemmy.api import LemmyAPI
from models.models import Community, CommunityStats, Post

# Amount of minutes between CommunityStats updates
COMMUNITY_UPDATE_INTERVAL = 120

# Minimum amount of minutes between checks
INTERVAL_DESERTED = 60 * 12
INTERVAL_LOW = 120
INTERVAL_MEDIUM = 30
INTERVAL_HIGH = 10

# Deserted is the minimal value
SUBSCRIBER_INTERVAL_MAPPING = [
    (0, INTERVAL_DESERTED),
    (2, INTERVAL_LOW),
    (5, INTERVAL_MEDIUM),
    (25, INTERVAL_HIGH),
]

# Amount of Communities to update per time
BATCH_SIZE = 10

logger = logging.getLogger(__name__)


class Stats:
    def __init__(self, db: DbSession, lemmy: LemmyAPI):
        self._db: DbSession = db
        self._lemmy: LemmyAPI = lemmy

    def update_community_stats(self):
        """Update a bunch of communities"""
        self.initialize_stats()

        # Get 10 CommunityStats that have not been updated recently
        batch: List[CommunityStats] = self.get_update_batch(BATCH_SIZE)

        for community_stats in batch:
            try:
                data = self._lemmy.community(name=community_stats.community.ident)
            except HTTPError as e:
                logger.error(f"Error fetching {community_stats.community.ident} stats: {str(e.response)}")
                continue
            community_stats.subscribers = data['community_view']['counts']['subscribers']

            # While we're here, update any unknown Community.created
            if not community_stats.community.created:
                community_stats.community.created = datetime.fromisoformat(
                    data['community_view']['community']['published'])
                self._db.add(community_stats.community)

            community_stats.posts_per_day = self.get_posts_per_day(community_stats.community_id)
            community_stats.last_update = datetime.utcnow()
            community_stats.min_interval = self.decide_interval(community_stats)

            self._db.add(community_stats)
            self._db.commit()

    def initialize_stats(self):
        """Ensure that each Community has a CommunityStats counterpart"""
        statless_communities = self._db.query(Community) \
            .outerjoin(CommunityStats).filter(CommunityStats.community_id == None).all()

        for community in statless_communities:
            logger.debug(f"LOL, {community.ident} doesn't have any stats. Let's all point and laugh!")
            stats = CommunityStats(community=community, subscribers=0, posts_per_day=0, min_interval=INTERVAL_MEDIUM,
                                   last_update=datetime.fromtimestamp(0))
            self._db.add(stats)
        self._db.commit()

    def get_posts_per_day(self, community_id: int) -> int:
        """Retrieve amount of posts for community in the last 24 hours"""
        yesterday_utc = datetime.utcnow() - timedelta(hours=24)

        post_count = self._db.query(func.count(Post.id)) \
            .filter(Post.community_id == community_id, Post.updated >= yesterday_utc) \
            .scalar()

        return post_count

    def get_update_batch(self, limit: int) -> List[CommunityStats]:
        """Get a batch of CommunityStats that are due for an update"""
        yesterday_utc = datetime.utcnow() - timedelta(days=-1)
        self._db.query(CommunityStats) \
            .join(Community, CommunityStats.community_id == Community.id) \
            .filter(
            CommunityStats.last_update < datetime.utcnow() - timedelta(minutes=COMMUNITY_UPDATE_INTERVAL),
            or_(
                Community.created.is_(None),
                Community.created <= yesterday_utc
            )
        ) \
            .order_by(asc(CommunityStats.last_update), asc(CommunityStats.subscribers)) \
            .limit(limit) \
            .all()

    def decide_interval(self, community_stats: CommunityStats) -> int:
        """Decide what the next update should be, based on subscriber count and posts per day"""
        subscribers = community_stats.subscribers
        posts_per_day = community_stats.posts_per_day

        if subscribers <= 1:  # Only the bot is subscribed
            return INTERVAL_DESERTED

        if posts_per_day < 1:
            return INTERVAL_LOW

        for threshold, interval in reversed(SUBSCRIBER_INTERVAL_MAPPING):  # Work highest to lowest
            if subscribers <= threshold:
                return interval

        return INTERVAL_HIGH
