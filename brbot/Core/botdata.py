# File containing global variables for bot.
from os import environ, path
from pathlib import Path
from dotenv import load_dotenv
from brbot.db.models import GuildConfig
import logging

logger = logging.getLogger(__name__)

load_dotenv()
pass_str: str = "✅\u200b"
fail_str: str = "❌\u200b"
upvote_emoji: str = "🔺"
downvote_emoji: str = "🔻"


def default_config(guild_id: int) -> GuildConfig:
    return GuildConfig(
        guild_id=guild_id,
        allow_phrases=True,
        limit_user_responses=False,
        max_user_responses=10,
        restrict_response_deletion=False,
        enable_nsfw=False,
    )


try:
    token: str = environ["TOKEN"]
    DATABASE_URL = environ["DATABASE_URL"]
except KeyError:
    logger.critical("No token/db found in .env file, exiting")
    exit(1)

try:
    DEV_SERVER_ID = environ["DEV_SERVER_ID"]
except KeyError:
    logger.warning(
        "DEV_SERVER_ID missing in .env; development commands will not be loaded."
    )
    DEV_SERVER_ID = None

parent: str = f"{path.dirname(path.realpath(__file__))}/.."

FEATURES_DIRECTORY = Path("brbot/Features")

# IF CHANGED, ALSO CHANGE IN alembic.ini
DATA_DIRECTORY = Path("brbot/db")

bot_id: int = 0
bot_avatar_url: str = ""
train_zones_url: str = "https://i.imgur.com/CRgbw7R.png"
date_format: str = "%Y/%m/%d %H:%M:%S"

active_msgs: list = []
active_trains: dict = {}
active_bingos: dict = {}
