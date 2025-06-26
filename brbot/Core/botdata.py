# File containing global variables for bot.

from os import environ, path
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

load_dotenv()
pass_str: str = "✅\u200b"
fail_str: str = "❌\u200b"
default_config: dict = {
    "ALLOW_PHRASES": True,
    "LIMIT_USER_RESPONSES": False,
    "MAX_USER_RESPONSES": 10,
    "USER_ONLY_DELETE": False,
}
try:
    token: str = environ["TOKEN"]
except KeyError:
    logger.critical("No token found in .env file, exiting")
    exit(1)

parent: str = f"{path.dirname(path.realpath(__file__))}/.."

bot_id: int = 0
bot_avatar_url: str = ""
train_zones_url: str = "https://i.imgur.com/CRgbw7R.png"
date_format: str = "%Y/%m/%d %H:%M:%S"

responses, mentions, config = {}, {}, {}
active_msgs: list = []
active_trains: dict = {}
active_bingos: dict = {}
linked_profiles: dict = {}
