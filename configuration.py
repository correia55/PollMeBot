import os
import discord

import alembic.config as aleconf
import alembic.command as alecomm
import alembic.migration as alemig
import alembic.autogenerate as aleauto

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models


# region Configuration

# Time between checks
TIME_BETWEEN_CHECKS_SEC = 43200

# Time after which a closed poll is deleted
OLDEST_CLOSED_POLL_DAYS = 10

# Limit number of polls per server
POLL_LIMIT_SERVER = 15

# endregion


# region Database

# Get the database url saved in the environment variable
database_url = os.environ.get('DATABASE_URL', None)

if database_url is None:
    print('Unable to find database url!')
    exit(1)

# Get the token for the bot saved in the environment variable
token = os.environ.get('BOT_TOKEN', None)

if token is None:
    print('Unable to find bot token!')
    exit(1)

engine = create_engine(database_url)
Session = sessionmaker(bind=engine)

MIGRATIONS_DIR = './migrations/'

config = aleconf.Config(file_='%salembic.ini' % MIGRATIONS_DIR)
config.set_main_option('script_location', MIGRATIONS_DIR)
config.set_main_option('sqlalchemy.url', database_url)

# Create tables if they don't exist
if not os.path.isdir(MIGRATIONS_DIR):
    alecomm.init(config, MIGRATIONS_DIR)

    env_file = open('%senv.py' % MIGRATIONS_DIR, 'r+')
    text = env_file.read()
    text = text.replace('target_metadata=target_metadata', 'target_metadata=target_metadata, compare_type=True')
    text = text.replace('target_metadata = None', 'import models\ntarget_metadata = models.base.metadata')
    env_file.seek(0)
    env_file.write(text)
    env_file.close()

# Makes sure the database is up to date
alecomm.upgrade(config, 'head')

# Check for changes in the database
mc = alemig.MigrationContext.configure(engine.connect())
diff_list = aleauto.compare_metadata(mc, models.base.metadata)

# Update the database
if diff_list:
    alecomm.revision(config, None, autogenerate=True)
    alecomm.upgrade(config, 'head')

# New Session
session = Session()

# endregion


# Create a client
intents = discord.Intents.default()
intents.members = True

client = discord.Client(intents=intents)
