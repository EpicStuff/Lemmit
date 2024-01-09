#!/usr/bin/env python3
import argparse
import logging
import os
import sys
from typing import Type

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from lemmy.api import LemmyAPI
from models.models import Community, CommunityStats
from reddit.reader import RedditReader
from utils.syncer import Syncer

load_dotenv()
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
					level=os.getenv('LOGLEVEL', logging.INFO))


syncer: Syncer


def log_stats(community: Type[Community]):
	logging.info(f'Community {community.ident} is {"ENABLED" if community.enabled else "DISABLED"}, has {community.stats.subscribers} subscribers and {community.stats.posts_per_day} posts per day.')


def show_communities(as_markdown: bool = False):
	# Query
	results = (
		db.query(Community.ident, Community.nsfw, Community.enabled, CommunityStats.subscribers)
		.join(CommunityStats, Community.id == CommunityStats.community_id)
		.order_by(Community.enabled.desc(), Community.ident)
		.all()
	)

	def print_cli():
		max_ident = max(len("Ident"), max(len(row[0]) for row in results))
		max_enabled = len("Disabled")
		max_nsfw = len("NSFW")
		max_subs = max(len("Subscribers"), max(len(str(row[2])) for row in results))

		row_format = f"{{0:<{max_ident}}} | {{1:<{max_enabled}}} | {{2:<{max_subs}}}"
		print(row_format.format("Ident", "NSFW", "Status", "Subscribers"))
		print('-' * (max_ident + max_nsfw + max_enabled + max_subs + 6))  # 9 accounts for separators spacing

		for ident, nsfw, enabled, subscribers in results:
			print(row_format.format(
				ident,
				'NSFW' if nsfw else '',
				'Enabled' if enabled else 'Disabled',
				subscribers
			))

	def print_markdown():
		host_basename = os.getenv('LEMMY_BASE_URI', 'https://lemmit.online')
		print("| Ident | NSFW | Status | Subscribers |")
		print("|-------|------|--------|-------------|")
		for ident, nsfw, enabled, subscribers in results:
			formatted_ident = f"[{ident}]({host_basename}/c/{ident})"
			print(f"| {formatted_ident}"
				f" | {'NSFW' if nsfw else ''}"
				f" | {'Enabled' if enabled else 'Disabled'}"
				f" | {subscribers} |")

	if as_markdown:
		print_markdown()
	else:
		print_cli()


def add_community(ident: str):
	community_dto = syncer.get_community_details(ident)
	syncer.create_community(community_dto)


if __name__ == '__main__':
	if not os.getenv('DATABASE_URL'):
		logging.error('Database not found, check env.')
		sys.exit(1)
	engine = create_engine(os.getenv('DATABASE_URL'))
	db = sessionmaker(bind=engine)()

	lemmy_api = LemmyAPI(base_url=os.getenv('LEMMY_BASE_URI'), username=os.getenv('LEMMY_USERNAME'),
						password=os.getenv('LEMMY_PASSWORD'))
	reddit_scraper = RedditReader()
	syncer = Syncer(db=db, reddit_reader=reddit_scraper, lemmy=lemmy_api, thresh_ratio=1.0, thresh_upvotes=50)

	parser = argparse.ArgumentParser(description="List and modify the enabled status of a community")
	subparsers = parser.add_subparsers(dest="command", required=True, help="Commands to manage communities")
	list_parser = subparsers.add_parser('list', help="Give an overview of communities, grouped by status.")
	list_parser.add_argument('--markdown', action='store_true', help='Output list as markdown.')
	add_parser = subparsers.add_parser('add', help="Add a new community to the bot scraper")
	add_parser.add_argument('ident', help='The community to add')
	enable_parser = subparsers.add_parser('enable', help="Enable the community.")
	enable_parser.add_argument("ident", help="The community ident.")
	disable_parser = subparsers.add_parser('disable', help="Disable the community.")
	disable_parser.add_argument("ident", help="The community ident.")
	status_parser = subparsers.add_parser('status', help="Check the status of the community.")
	status_parser.add_argument("ident", help="The community ident.")
	args = parser.parse_args()

	if args.command == 'list':
		show_communities(args.markdown)
		sys.exit(0)

	if args.command == 'add':
		add_community(args.ident)
		sys.exit(0)

	community = db.query(Community).filter(Community.ident.ilike(args.ident)).first()
	if community is None:
		logging.error(f"Community '{args.ident}' not found.")
		sys.exit(1)

	if args.command == 'enable':
		# Call a function or add logic to enable the community based on ident
		if community.enabled:
			logging.error(f"Community {community.ident} is already enabled, not doing anything.")
		else:
			community.enabled = True
			db.commit()
	elif args.command == 'disable':
		if not community.enabled:
			logging.error(f"Community {community.ident} is already disabled, not doing anything.")
		else:
			community.enabled = False
			db.commit()

	log_stats(community)
