"""
Ben Samans
botutils.py
Bot functions
"""

import asyncio
import json
from dataclasses import dataclass
from os import makedirs, listdir, path, remove
from shutil import rmtree
from random import choice
from re import findall
from time import strftime

import interactions
import matplotlib.font_manager
from colorama import Fore

import Core.botdata as bd
from Features.Responses.data import gen_resp_list, load_responses
from Features.Trains.data import gen_rules_embed, load_trains_game
from Features.Bingo.data import load_bingo_game
from Features.Help.data import gen_help_embed, help_pages


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


def del_game_files(guild_id: int, game_name: str, game_type: str):
    try:
        rmtree(f"{bd.parent}/Guilds/{guild_id}/{game_type}/{game_name}")
    except PermissionError:
        pass


def load_anilist_caches() -> None:

    if not path.exists(f"{bd.parent}/Data/linked_profiles.json"):
        makedirs(f"{bd.parent}/Data", exist_ok=True)
        with open(f"{bd.parent}/Data/linked_profiles.json", "w") as f:
            json.dump({}, f, separators=(",", ":"))
    with open(f"{bd.parent}/Data/linked_profiles.json", "r") as f:
        bd.linked_profiles = {int(key): int(val) for key, val in json.load(f).items()}

    if not path.exists(f"{bd.parent}/Data/manga_rec_cache.json"):
        with open(f"{bd.parent}/Data/manga_rec_cache.json", "w") as f:
            json.dump({}, f, separators=(",", ":"))
    with open(f"{bd.parent}/Data/manga_rec_cache.json", "r") as f:
        bd.known_manga_recs = {int(key): val for key, val in json.load(f).items()}

    if not path.exists(f"{bd.parent}/Data/anime_rec_cache.json"):
        with open(f"{bd.parent}/Data/anime_rec_cache.json", "w") as f:
            json.dump({}, f, separators=(",", ":"))
    with open(f"{bd.parent}/Data/anime_rec_cache.json", "r") as f:
        bd.known_anime_recs = {int(key): val for key, val in json.load(f).items()}


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


async def close_msg(list_msg: ListMsg, delay: int, ctx: interactions.SlashContext) -> None:
    await asyncio.sleep(delay)

    if list_msg.msg_type == "rsplist":
        embed = gen_resp_list(ctx.guild, list_msg.page, True)
    elif list_msg.msg_type == "help":
        embed = gen_help_embed(page=list_msg.page, expired=True)
    elif list_msg.msg_type == "trainrules":
        embed = gen_rules_embed(list_msg.page, True)
    elif list_msg.msg_type == "bingoboard":
        sender_idx, _ = list_msg.payload.get_player(player_id=ctx.author_id)
        embed, image = list_msg.payload.gen_board_embed(
            page=list_msg.page, sender_idx=sender_idx, expired=True
        )
    else:
        embed = None
    await ctx.edit(embeds=embed)
    bd.active_msgs.remove(list_msg)


async def get_members_from_str(guild, txt: str) -> list[interactions.Member]:
    mention_pattern = r"<@(\d+)>"
    mentions = set(findall(mention_pattern, txt))

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
            if user.global_name[0:idx + 1] not in tags:
                tags.append(user.global_name[0:idx + 1].upper())
                done = True
                break
        if not done:
            tags.append(user.global_name.upper())
    return tags


def autocomplete_filter(option: str) -> dict[str: str]:
    if len(option) > 100:
        option = option[:99]
    return {"name": option, "value": option}


async def init_guilds(guilds: list[interactions.Guild]):
    for guild in guilds:
        # Make guild folder if it doesn't exist
        if not path.exists(f"{bd.parent}/Guilds/{guild.id}/Trains"):
            makedirs(f"{bd.parent}/Guilds/{guild.id}/Trains")
            print(
                Fore.WHITE + f"{strftime(bd.date_format)}:  " +
                Fore.YELLOW + f"Created guild folder for {guild.name}" + Fore.RESET
            )
        if not path.exists(f"{bd.parent}/Guilds/{guild.id}/Bingo"):
            makedirs(f"{bd.parent}/Guilds/{guild.id}/Bingo")
            print(
                Fore.WHITE + f"{strftime(bd.date_format)}:  " +
                Fore.YELLOW + f"Created guild folder for {guild.name}" + Fore.RESET
            )

        load_config(guild)
        bd.responses[guild.id] = load_responses(f"{bd.parent}/Guilds/{guild.id}/responses.json")

        print(
            Fore.WHITE + f"{strftime(bd.date_format)}:  " +
            Fore.GREEN + f"Responses loaded for {guild.name}" + Fore.RESET
        )

        # DELETE THESE LINES ONCE BOT HAS BEEN LOADED ONCE
        if path.exists(f"{bd.parent}/Guilds/{guild.id}/mentions.json"):
            bd.responses[guild.id] += load_responses(f"{bd.parent}/Guilds/{guild.id}/mentions.json")

            temp_lines = [response.__dict__ for response in bd.responses[guild.id]]
            with open(f"{bd.parent}/Guilds/{guild.id}/responses.json", "w") as f:
                json.dump(temp_lines, f, indent=4)
            remove(f"{bd.parent}/Guilds/{guild.id}/mentions.json")
            print("Legacy mentions file removed and rolled into response file.")
        # END DELETE OF LINES

        # Load trains games

        for name in listdir(f"{bd.parent}/Guilds/{guild.id}/Trains"):

            try:
                game = await load_trains_game(
                    filepath=f"{bd.parent}/Guilds/{guild.id}/Trains/{name}", guild=guild, active_only=True
                )
                if game.active:
                    bd.active_trains[guild.id] = game
                    break
            except (FileNotFoundError, TypeError, ValueError, KeyError) as e:
                print(e)
                del_game_files(guild_id=guild.id, game_name=name, game_type="Trains")
                print(
                    Fore.WHITE + f'{strftime(bd.date_format)} :  ' +
                    Fore.YELLOW + f"Invalid game \"{name}\" in guild {guild.id}, attempted delete." + Fore.RESET
                )
            except NotADirectoryError:
                pass

        # Load bingo games

        for name in listdir(f"{bd.parent}/Guilds/{guild.id}/Bingo"):

            try:
                game = await load_bingo_game(
                    filepath=f"{bd.parent}/Guilds/{guild.id}/Bingo/{name}", guild=guild, active_only=True
                )
                if game.active:
                    bd.active_bingos[guild.id] = game
                    break
            except (FileNotFoundError, TypeError, ValueError, KeyError) as e:
                print(e)
                del_game_files(guild_id=guild.id, game_name=name, game_type="Bingo")
                print(
                    Fore.WHITE + f'{strftime(bd.date_format)} :  ' +
                    Fore.YELLOW + f"Invalid game \"{name}\" in guild {guild.id}, attempted delete." + Fore.RESET
                )
            except NotADirectoryError:
                pass


def handle_page_change(ctx: interactions.api.events.Component.ctx) -> tuple[
    None | interactions.Embed, list[interactions.Button], None | interactions.File
]:
    image = None
    embed = None
    components = None
    for idx, msg in enumerate(bd.active_msgs):  # Search active messages for correct one
        if msg.num != int(ctx.message.id):
            continue

        if ctx.custom_id == "help_category":
            if not ctx.values:
                bd.active_msgs[idx].page = help_pages["general"]
            bd.active_msgs[idx].page = help_pages[ctx.values[0]]
            embed, components = gen_help_embed(bd.active_msgs[idx].page, expired=False)
            continue

        game = msg.payload

        # Update page num
        if ctx.custom_id == "prevpg":
            bd.active_msgs[idx].page -= 1
        elif ctx.custom_id == "nextpg":
            bd.active_msgs[idx].page += 1

        if msg.msg_type == "trainstats":
            embed, image = game.gen_stats_embed(
                ctx=ctx, page=bd.active_msgs[idx].page, expired=False
            )
        elif msg.msg_type == "trainscores":
            embed, image = game.gen_score_embed(
                ctx=ctx, page=bd.active_msgs[idx].page, expired=False
            )
        elif msg.msg_type == "bingoboard":
            sender_idx, _ = game.get_player(player_id=ctx.author_id)
            embed, image = game.gen_board_embed(
                page=bd.active_msgs[idx].page, sender_idx=sender_idx, expired=False
            )
        elif msg.msg_type == "trainrules":
            embed = gen_rules_embed(bd.active_msgs[idx].page, False)
        elif msg.msg_type == "rsplist":
            embed = gen_resp_list(ctx.guild, bd.active_msgs[idx].page, False)

        components = [nextpg_button(), prevpg_button()]
        break

    return embed, components, image


def generate_response(message: interactions.api.events.MessageCreate.message) -> str | None:
    if message.author.bot:
        return None
    channel = message.channel
    if channel.type == 1:  # Ignore DMs
        return None

    guild_id = message.guild.id

    to_send = [
        response.text for response in bd.responses[guild_id]
        if response.trig == message.content.lower() and response.exact
    ]
    if to_send:
        return choice(to_send)

    if not bd.config[guild_id]["ALLOW_PHRASES"]:
        return None

    to_send = [
        response.text for response in bd.responses[guild_id]
        if response.trig in message.content.lower() and not response.exact
    ]
    if to_send:
        return choice(to_send)

    return None


def setup_guild(guild: interactions.Guild):
    if not path.exists(f'{bd.parent}/Guilds/{guild.id}'):
        makedirs(f'{bd.parent}/Guilds/{guild.id}/Trains')
        with open(f'{bd.parent}/Guilds/{int(guild.id)}/config.json', 'w') as f:
            json.dump(bd.default_config, f, indent=4)
        bd.config[int(guild.id)] = bd.default_config
        bd.responses[int(guild.id)] = []
        return False

    elif not path.isfile(f'{bd.parent}/Guilds/{int(guild.id)}/config.json'):
        with open(f'{bd.parent}/Guilds/{int(guild.id)}/config.json', 'w') as f:
            json.dump(bd.default_config, f, indent=4)
        return False


def nextpg_button() -> interactions.Button:
    return interactions.Button(
        style=interactions.ButtonStyle.SECONDARY,
        label="←",
        custom_id="prevpg",
    )


def prevpg_button() -> interactions.Button:
    return interactions.Button(
        style=interactions.ButtonStyle.SECONDARY,
        label="→️",
        custom_id="nextpg",
    )
