#!/usr/bin/env python3
import logging
import os
import signal
import sys
import time

from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from lemmy.api import LemmyAPI
from reddit.reader import RedditReader
from utils.stats import Stats
from utils.syncer import Syncer

syncer: Syncer
load_dotenv()
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
					level=os.getenv('LOGLEVEL', logging.INFO))
keep_running = True


def handle_signal(signum, frame):		
	global keep_running
	logging.warning(f"Received signal {signum}. Stopping as soon as possible...")
	keep_running = False


def initialize_database(db_url):
	"""Initialize the database if it doesn't exist and run migrations."""
	engine = create_engine(db_url)

	# Run migrations using Alembic
	alembic_cfg = Config("../alembic.ini")
	alembic_cfg.set_main_option("script_location", "alembic")  # Adjust the script location if needed
	alembic_cfg.set_main_option("sqlalchemy.url", db_url)
	command.upgrade(alembic_cfg, "head")

	session = sessionmaker(bind=engine)
	return session()


if __name__ == '__main__':
	for var_name in ['DATABASE_URL', 'LEMMY_BASE_URI', 'LEMMY_USERNAME', 'LEMMY_PASSWORD']:
		if not os.getenv(var_name):
			logging.error(f'Error: {var_name} environment variable is not set.')
			sys.exit(1)

	database_url = os.getenv('DATABASE_URL')
	request_community = os.getenv('REQUEST_COMMUNITY', None)

	post_threshold_upvotes = int(os.getenv('THRESH_UPVOTES', 5))
	post_threshold_ratio = float(os.getenv('THRESH_RATIO', 0.5))

	db_session = initialize_database(database_url)
	lemmy_api = LemmyAPI(base_url=os.getenv('LEMMY_BASE_URI'), username=os.getenv('LEMMY_USERNAME'),
						password=os.getenv('LEMMY_PASSWORD'))
	reddit_scraper = RedditReader()
	syncer = Syncer(db=db_session, reddit_reader=reddit_scraper, lemmy=lemmy_api, thresh_upvotes=post_threshold_upvotes,
					thresh_ratio=post_threshold_ratio, request_community=request_community)
	stats = Stats(db=db_session, lemmy=lemmy_api)

	if request_community is None:
		logging.warning('No request community is set - will not check for new requests.')

	# Set up signal handlers
	signal.signal(signal.SIGINT, handle_signal)
	signal.signal(signal.SIGTERM, handle_signal)

	stats.recalculate_stats()

	while keep_running:
		if request_community:
			syncer.check_new_subs()
		stats.update_community_stats()
		syncer.scrape_new_posts()
		time.sleep(1)
