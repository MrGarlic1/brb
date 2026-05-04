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


def default_config(guild_id: int) -> GuildConfig:
    return GuildConfig(
        guild_id=guild_id,
        allow_phrases=True,
        limit_user_responses=False,
        max_user_responses=10,
        restrict_response_deletion=False,
    )


try:
    token: str = environ["TOKEN"]
except KeyError:
    logger.critical("No token found in .env file, exiting")
    exit(1)

parent: str = f"{path.dirname(path.realpath(__file__))}/.."

FEATURES_DIRECTORY = Path("brbot/Features")

# IF CHANGED, ALSO CHANGE IN alembic.ini
DATA_DIRECTORY = Path("brbot/db")
OLD_DATA_DIRECTORY = Path("brbot/Guilds")

bot_id: int = 0
bot_avatar_url: str = ""
train_zones_url: str = "https://i.imgur.com/CRgbw7R.png"
date_format: str = "%Y/%m/%d %H:%M:%S"

active_msgs: list = []
active_trains: dict = {}
active_bingos: dict = {}
