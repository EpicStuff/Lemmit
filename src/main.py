#!/usr/bin/env python3
import logging
import os
import sys
import time

from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from lemmy.api import LemmyAPI
from reddit.reader import RedditReader
from utils.syncer import Syncer

syncer: Syncer
load_dotenv()
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    level=os.getenv('LOGLEVEL', logging.INFO))
keep_running = True


def handle_signal(signum, frame):
    global keep_running
    logging.warning(f"Received signal {signum}. Stopping gracefully...")
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
    lemmy_base_uri = os.getenv('LEMMY_BASE_URI')
    request_community = os.getenv('REQUEST_COMMUNITY', None)

    db_session = initialize_database(database_url)
    lemmy_api = LemmyAPI(base_url=lemmy_base_uri, username=os.getenv('LEMMY_USERNAME'),
                         password=os.getenv('LEMMY_PASSWORD'))
    reddit_scraper = RedditReader()
    syncer = Syncer(db=db_session, reddit_reader=reddit_scraper, lemmy=lemmy_api, request_community=request_community)

    if request_community is None:
        logging.warning('No request community is set - will not check for new requests.')

    while keep_running:
        if request_community:
            syncer.check_new_subs()
        syncer.scrape_new_posts()
        time.sleep(2)
