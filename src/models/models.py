from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, Integer, String, ForeignKey, Boolean
from sqlalchemy.orm import relationship, Mapped, declarative_base

Base = declarative_base()

SORT_HOT = 'hot'
SORT_NEW = 'new'


@dataclass
class CommunityDTO:
	ident: str
	title: str
	description: str
	icon: str
	nsfw: bool


class Community(Base):
	"""Represents a community/subreddit on both Lemmy and Reddit"""

	__tablename__: str = 'communities'

	id: int = Column(Integer, primary_key=True)
	lemmy_id: int = Column(Integer, nullable=False)
	ident: str = Column(String, nullable=False)
	nsfw: bool = Column(Boolean, nullable=False, default=False)
	last_scrape: datetime = Column(DateTime, nullable=True)
	created: datetime = Column(DateTime, nullable=True, default=datetime.utcnow())
	enabled: bool = Column(Boolean, nullable=False, server_default='1')
	sorting: str = Column(String(length=10), nullable=False, server_default='hot')
	# Relationship to CommunityStats
	stats: Mapped['CommunityStats'] = relationship('CommunityStats', uselist=False, backref='community', lazy='select')

	def __str__(self) -> str:
		return f"{self.ident} path:{self.path}"


class CommunityStats(Base):
	"""Metrics for a specific community"""

	__tablename__: str = 'community_stats'

	community_id: int = Column(Integer, ForeignKey(f"{Community.__tablename__}.id"), primary_key=True)
	subscribers: int = Column(Integer, nullable=False, default=0)
	posts_per_day: int = Column(Integer, nullable=False, default=0)
	min_interval: int = Column(Integer, nullable=False, default=15)
	last_update: datetime = Column(DateTime, nullable=False, default=datetime.fromtimestamp(0))


@dataclass
class PostDTO:
	reddit_link: str
	title: str
	created: datetime
	updated: datetime
	author: str
	external_link: Optional[str] = None
	body: Optional[str] = None
	nsfw: bool = False
	upvotes: int = 2
	upvote_ratio: float = 1.0

	def __str__(self) -> str:
		return f"'{self.title}' at {self.reddit_link} updated: {self.updated}"


class Post(Base):
	__tablename__: str = 'posts'

	id: int = Column(Integer, primary_key=True)
	reddit_link: str = Column(String, nullable=False)
	lemmy_link: str = Column(String, nullable=False)
	updated: datetime = Column(DateTime, nullable=False)
	nsfw: bool = Column(Boolean, nullable=False)
	community_id: int = Column(Integer, ForeignKey('communities.id'), nullable=False)

	community: Mapped[Community] = relationship('Community')

	def __str__(self) -> str:
		return f"'#{self.id}: {self.title}' on {self.community.name}"

	@classmethod
	def from_dto(cls, post: PostDTO, community: Community) -> 'Post':
		return cls(
			reddit_link=post.reddit_link,
			community=community,
			updated=post.updated,
			nsfw=post.nsfw
		)
