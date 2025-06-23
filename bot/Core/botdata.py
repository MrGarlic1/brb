# File containing global variables for bot.

from os import environ, path
from dotenv import load_dotenv

load_dotenv()
pass_str: str = "✅\u200b"
fail_str: str = "❌\u200b"
default_config: dict = {
    "ALLOW_PHRASES": True,
    "LIMIT_USER_RESPONSES": False,
    "MAX_USER_RESPONSES": 10,
    "USER_ONLY_DELETE": False,
}
token: str = environ["TOKEN"]
parent: str = f"{path.dirname(path.realpath(__file__))}/.."

bot_id: int = 0
bot_avatar_url: str = ""
train_zones_url: str = "https://i.imgur.com/CRgbw7R.png"
date_format: str = "%Y/%m/%d %H:%M:%S"

emoji: dict = {
    "wheat": "🌾",
    "wood": "🌳",
    "gems": "💎",
    "city": "🌃",
    "prison": "🔒",
    "house": "🏠",
    "river": "🏞",
    "telescope": "🔭",
    "gun": "🔫",
    "bucket": "🪣",
    "bridge": "🌉",
    "axe": "🪓",
    "coin": "🪙",
    "maglev": "🚄",
    "shop": "🛒",
    "first": "🥇",
    "second": "🥈",
    "third": "🥉"
}

responses, mentions, config = {}, {}, {}
active_msgs: list = []
active_trains: dict = {}
active_bingos: dict = {}
linked_profiles: dict = {}
known_anime_recs: dict = {}
known_manga_recs: dict = {}
