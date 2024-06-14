"""
Ben Samans
botutils.py
Bot functions
"""

import interactions
from responses import gen_resp_list, load_responses
from trains import gen_rules_embed, load_game, del_game_files
import json
import botdata as bd
from time import strftime
from colorama import Fore
from dataclasses import dataclass
import asyncio
import matplotlib.font_manager
from os import makedirs, listdir, path


# Class Definitions
@dataclass
class ListMsg:
    def __init__(
            self, num: int, page: int, guild: interactions.Guild, channel: interactions.BaseChannel,
            msg_type: str, payload=None
    ):
        self.num = num
        self.page = page
        self.guild = guild
        self.channel = channel
        self.msg_type = msg_type
        self.payload = payload


def dict_to_choices(dictionary: dict) -> list[interactions.SlashCommandChoice]:
    out: list = []
    for key in dictionary.keys():
        out.append(interactions.SlashCommandChoice(name=key, value=key))
    return out


def load_fonts(filepath) -> None:
    for font in matplotlib.font_manager.findSystemFonts(filepath):
        matplotlib.font_manager.fontManager.addfont(font)


def load_config(guild: interactions.Guild) -> None:
    
    # Load and validate guild bd.configs
    try:

        with open(f"{bd.parent}/Guilds/{guild.id}/config.json", "r") as f:
            bd.config[int(guild.id)] = json.load(f)

        # Add missing keys
        for key in bd.default_config.keys():
            if key not in bd.config[int(guild.id)].keys():
                bd.config[int(guild.id)][key] = bd.default_config[key]
                print(
                    Fore.WHITE + f"{strftime('%Y-%m-%d %H:%M:%S')}:  " +
                    Fore.YELLOW + f"Config file for {guild.name} missing {key}, set to default." + Fore.RESET
                )
                with open(f"{bd.parent}/Guilds/{guild.id}/config.json", "w") as f:
                    json.dump(bd.config[int(guild.id)], f, indent=4)

        # Remove invalid keys
        temp = dict(bd.config[int(guild.id)])
        for key in bd.config[int(guild.id)].keys():
            if key not in bd.default_config.keys():
                temp = dict(bd.config[int(guild.id)])
                del temp[key]
                print(
                    Fore.WHITE + f"{strftime('%Y-%m-%d %H:%M:%S')}:  " +
                    Fore.YELLOW + f"Invalid key {key} in {guild.name} config, removed." + Fore.RESET
                )
                with open(f"{bd.parent}/Guilds/{guild.id}/config.json", "w") as f:
                    json.dump(temp, f, indent=4)
        bd.config[int(guild.id)] = temp

    # Create new file if config is missing
    except FileNotFoundError:
        with open(f"{bd.parent}/Guilds/{guild.id}/config.json", "w") as f:
            json.dump(bd.default_config, f, indent=4)
            bd.config[int(guild.id)] = bd.default_config
        print(
            Fore.WHITE + f"{strftime('%Y-%m-%d %H:%M:%S')}:  " +
            Fore.YELLOW + f"No config file found for {guild.name}, created default config file." + Fore.RESET
        )


async def close_msg(list_msg: ListMsg, delay: int, ctx: interactions.SlashContext, msg: interactions.Message) -> None:
    await asyncio.sleep(delay)

    if list_msg.msg_type == "rsplist":
        embed = gen_resp_list(ctx.guild, list_msg.page, True)
    elif list_msg.msg_type == "trainrules":
        embed = gen_rules_embed(list_msg.page, True)
    else:
        embed = None
    await msg.edit(embeds=embed)
    bd.active_msgs.remove(list_msg)


async def get_members_from_str(guild, txt: str) -> list[interactions.Member]:
    mentions: list = []
    mention: str = ""
    mention_start: bool = False
    id_start: bool = False

    for char in txt:

        # Begin recording of characters until a non-integer character is encountered
        if id_start:
            try:
                int(char)
                mention += char
            except ValueError:
                try:
                    if int(mention) in mentions:
                        continue
                    mentions.append(int(mention))
                except ValueError:
                    pass
                id_start: bool = False
                mention_start: bool = False
                mention: str = ""

        # Confirm start of discord mention string
        if char == "@" and mention_start:
            id_start: bool = True

        # Mark start of discord mention string
        if char == "<":
            mention_start: bool = True

    # Check for invalid player IDs
    members: list = []
    for entry in mentions:
        member = await guild.fetch_member(entry)
        if not member or member.bot:
            pass
        else:
            members.append(member)
    return members


def get_player_tags(users: list[interactions.Member]) -> list[str]:
    tags: list = []
    for user in users:
        done = False
        for idx, letter in enumerate(user.global_name):
            if user.global_name[0:idx+1] not in tags:
                tags.append(user.global_name[0:idx+1].upper())
                done = True
                break
        if not done:
            tags.append(user.global_name.upper())
    return tags


def autocomplete_filter(option: str) -> dict[str: str]:
    if len(option) > 100:
        option = option[:99]
    return {"name": option, "value": option}


async def init_guilds(guilds: list[interactions.Guild], bot: interactions.Client):
    for guild in guilds:
        # Make guild folder if it doesn't exist
        if not path.exists(f"{bd.parent}/Guilds/{guild.id}/Trains"):
            makedirs(f"{bd.parent}/Guilds/{guild.id}/Trains")
            print(
                Fore.WHITE + f"{strftime(bd.date_format)}:  " +
                Fore.YELLOW + f"Created guild folder for {guild.name}" + Fore.RESET
            )

        load_config(guild)
        bd.mentions[guild.id] = load_responses(f"{bd.parent}/Guilds/{guild.id}/mentions.json")
        bd.responses[guild.id] = load_responses(f"{bd.parent}/Guilds/{guild.id}/responses.json")

        print(
            Fore.WHITE + f"{strftime(bd.date_format)}:  " +
            Fore.GREEN + f"Responses loaded for {guild.name}" + Fore.RESET
        )

        # Load trains games

        for name in listdir(f"{bd.parent}/Guilds/{guild.id}/Trains"):

            try:
                game = await load_game(
                    filepath=f"{bd.parent}/Guilds/{guild.id}/Trains/{name}", bot=bot, guild=guild, active_only=True
                )
                if game.active:
                    bd.active_trains[guild.id] = game
                    break
            except (FileNotFoundError, TypeError, ValueError, KeyError):
                del_game_files(guild_id=guild.id, game_name=name)
                print(
                    Fore.WHITE + f'{strftime(bd.date_format)} :  ' +
                    Fore.YELLOW + f"Invalid game \"{name}\" in guild {guild.id}, attempted delete." + Fore.RESET
                )
            except NotADirectoryError:
                pass
