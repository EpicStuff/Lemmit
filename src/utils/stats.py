import logging
import time
from datetime import datetime, timedelta
from operator import or_
from typing import List

from requests import HTTPError
from sqlalchemy import asc, func, and_
from sqlalchemy.orm import Session as DbSession

from lemmy.api import LemmyAPI
from models.models import Community, CommunityStats, Post

# Amount of minutes between CommunityStats updates
COMMUNITY_UPDATE_INTERVAL = 120

# Minimum amount of minutes between checks
INTERVAL_DESERTED = 60 * 12
INTERVAL_LOW = 120
INTERVAL_MEDIUM = 60
INTERVAL_HIGH = 30
INTERVAL_HIGHEST = 10


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
        if not batch:
            logger.debug("No communities due for a stats update")
            return

        for community_stats in batch:
            logger.info(f"Updating stats for {community_stats.community.ident}...")
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
            community_stats.min_interval = self.decide_interval(
                community_stats.subscribers, community_stats.posts_per_day
            )

            self._db.add(community_stats)
            self._db.commit()
            time.sleep(0.5)  # TODO - move delay to Lemmy client. 0.5s for get, 2s for POST

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
        """Get a batch of CommunityStats that are due for an update, or with an unknown Community creation"""
        yesterday_utc = datetime.utcnow() - timedelta(days=1)
        stats_threshold_utc = datetime.utcnow() - timedelta(minutes=COMMUNITY_UPDATE_INTERVAL)
        query = (
            self._db.query(CommunityStats)
            .join(Community, CommunityStats.community_id == Community.id)
            .filter(
                or_(
                    Community.created.is_(None),
                    and_(
                        CommunityStats.last_update < stats_threshold_utc,
                        Community.created <= yesterday_utc
                    ),
                )
            )
            .order_by(asc(CommunityStats.last_update), asc(CommunityStats.subscribers))
            .limit(limit)
            .all()
        )

        return query

    @staticmethod
    def decide_interval(subscribers: int, posts_per_day: int) -> int:
        """Decide what the next update should be, based on subscriber count and posts per day"""
        # No subscribers, or too little posts means check once per day
        if subscribers < 2 or posts_per_day < 1:
            return INTERVAL_DESERTED

        if subscribers >= 25 and posts_per_day >= 25:
            return INTERVAL_HIGHEST

        if subscribers >= 10 and posts_per_day >= 15:
            return INTERVAL_HIGH

        if subscribers >= 5 and posts_per_day >= 10:
            return INTERVAL_MEDIUM

        return INTERVAL_LOW
