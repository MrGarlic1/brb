# File containing global variables for botutils.py.

from os import environ
from dotenv import load_dotenv

load_dotenv()
pass_str = "✅\u200b"
fail_str = "❌\u200b"
default_config = {
    "ALLOW_PHRASES": True,
    "LIMIT_USER_RESPONSES": False,
    "MAX_USER_RESPONSES": 10,
    "USER_ONLY_DELETE": False,
}
token = environ["TOKEN"]
parent = environ["PARENT"]
bot_id = 887530423826145310
bot_avatar_url = "https://cdn.discordapp.com/attachments/895549688026124321/1103188621193924708/ursa_cm.png"
train_zones_url = "https://i.imgur.com/AmbDhB7.png"
date_format = "%Y/%m/%d %H:%M:%S"


responses, mentions, config = {}, {}, {}
active_msgs = []
active_trains = {}
