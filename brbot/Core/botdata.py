# File containing global variables for bot.
from os import getenv, path
from pathlib import Path
from brbot.db.models import GuildConfig
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

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
    token: str = getenv("TOKEN")
    DATABASE_URL = getenv("DATABASE_URL")
except KeyError:
    logger.critical("No token/db found in .env file, exiting")
    exit(1)

try:
    DEV_SERVER_ID: int | None = int(getenv("DEV_SERVER_ID"))
except (KeyError, ValueError, TypeError):
    DEV_SERVER_ID = None

parent: str = f"{path.dirname(path.realpath(__file__))}/.."

FEATURES_DIRECTORY = Path("brbot/Features")
DATA_DIRECTORY = Path("brbot/db")
STATIC_DIRECTORY = Path("brbot/Static")

bot_id: int = 0
bot_avatar_url: str = ""
train_zones_url: str = "https://i.imgur.com/CRgbw7R.png"
date_format: str = "%Y/%m/%d %H:%M:%S"

active_msgs: list = []
active_trains: dict = {}
active_bingos: dict = {}
