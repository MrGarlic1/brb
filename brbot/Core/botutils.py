import json
from os import makedirs, listdir, path
from shutil import rmtree
from re import findall
from typing import Sequence
from discord import Guild, Member
from discord.app_commands import Choice

import logging
import matplotlib.font_manager

import brbot.Core.botdata as bd
from brbot.Features.Responses.data import load_responses
from brbot.Features.Trains.service import load_trains_game
from brbot.Features.Bingo.data import load_bingo_game

logger = logging.getLogger(__name__)


def load_fonts(filepath) -> None:
    """
    Initializes fonts upon bot loading.
    Args:
        filepath: path to font file

    Returns:
        None
    """
    for font in matplotlib.font_manager.findSystemFonts(filepath):
        matplotlib.font_manager.fontManager.addfont(font)


def del_game_files(guild_id: int, game_name: str, game_type: str):
    """
    Deletes all game files associated with a specific game type.
    Args:
        guild_id: ID of guild with associated game data.
        game_name: Name of game to delete.
        game_type: Game type to delete.

    Returns:
        None
    """
    try:
        rmtree(f"{bd.parent}/Guilds/{guild_id}/{game_type}/{game_name}")
    except PermissionError:
        pass


def load_anilist_caches() -> None:
    """
    Loads local cache of Anilist data
    Returns:
        None
    """
    if not path.exists(f"{bd.DATA_DIRECTORY}/linked_profiles.json"):
        makedirs(f"{bd.DATA_DIRECTORY}", exist_ok=True)
        with open(f"{bd.DATA_DIRECTORY}/linked_profiles.json", "w") as f:
            json.dump({}, f, separators=(",", ":"))
    with open(f"{bd.DATA_DIRECTORY}/linked_profiles.json", "r") as f:
        bd.linked_profiles = {int(key): int(val) for key, val in json.load(f).items()}


def load_config(guild: Guild) -> None:
    """
    Loads guild-specific config data from local storage
    Args:
        guild: Discord Guild object to load config data for

    Returns:
        None
    """
    # Load and validate guild bd.configs
    try:
        with open(f"{bd.parent}/Guilds/{guild.id}/config.json", "r") as f:
            bd.config[int(guild.id)] = json.load(f)

        # Add missing keys
        for key in bd.default_config.keys():
            if key not in bd.config[int(guild.id)].keys():
                bd.config[int(guild.id)][key] = bd.default_config[key]
                logger.warning(
                    f"Config file for {guild.name} missing {key}, set to default."
                )
                with open(f"{bd.parent}/Guilds/{guild.id}/config.json", "w") as f:
                    json.dump(bd.config[int(guild.id)], f, indent=4)

        # Remove invalid keys
        temp = dict(bd.config[int(guild.id)])
        for key in bd.config[int(guild.id)].keys():
            if key not in bd.default_config.keys():
                temp = dict(bd.config[int(guild.id)])
                del temp[key]
                logger.warning(f"Invalid key {key} in {guild.name} config, removed.")
                with open(f"{bd.parent}/Guilds/{guild.id}/config.json", "w") as f:
                    json.dump(temp, f, indent=4)
        bd.config[int(guild.id)] = temp

    # Create new file if config is missing
    except FileNotFoundError:
        with open(f"{bd.parent}/Guilds/{guild.id}/config.json", "w") as f:
            json.dump(bd.default_config, f, indent=4)
            bd.config[int(guild.id)] = bd.default_config
        logger.warning(
            f"No config file found for {guild.name}, created default config file."
        )


async def get_members_from_str(guild, txt: str) -> list[Member]:
    """
    Filter/validate string input to get a list of discord members
    Args:
        guild: Guild to search for members
        txt: String input

    Returns:
        List of discord members
    """
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


def autocomplete_filter(option: str) -> Choice:
    """
    Truncates long autocomplete options to avoid hard discord character limits
    Args:
        option: Autocomplete string option
    Returns:
        Truncated discord Choice object
    """
    if len(option) > 100:
        option = option[:99]
    return Choice(name=option, value=option)


async def init_guilds(guilds: Sequence[Guild]) -> None:
    """
    Validates directory structure and configuration of guilds, creates files, corrects errors, loads guild games
    Args:
        guilds: All the guilds the bot is connected to
    Returns:
        None
    """
    for guild in guilds:
        # Make guild folder if it doesn't exist
        if not path.exists(f"{bd.parent}/Guilds/{guild.id}/Trains"):
            makedirs(f"{bd.parent}/Guilds/{guild.id}/Trains")
            logger.info(f"Created guild trains folder for {guild.name}")
        if not path.exists(f"{bd.parent}/Guilds/{guild.id}/Bingo"):
            makedirs(f"{bd.parent}/Guilds/{guild.id}/Bingo")
            logger.info(f"Created guild bingo folder for {guild.name}")

        load_config(guild)
        bd.responses[guild.id] = load_responses(
            f"{bd.parent}/Guilds/{guild.id}/responses.json"
        )

        logger.info(f"Responses loaded for {guild.name}")

        # Load trains games

        for name in listdir(f"{bd.parent}/Guilds/{guild.id}/Trains"):
            try:
                game = await load_trains_game(
                    filepath=f"{bd.parent}/Guilds/{guild.id}/Trains/{name}",
                    guild=guild,
                    active_only=True,
                )
                if game.active:
                    bd.active_trains[guild.id] = game
                    break
            except (FileNotFoundError, TypeError, ValueError, KeyError) as e:
                logger.warning(f"Error loading train data for guild {guild.name}: {e}")
                del_game_files(guild_id=guild.id, game_name=name, game_type="Trains")
                logger.warning(
                    f'Invalid trains game "{name}" in guild {guild.name}, attempted delete.'
                )
            except NotADirectoryError:
                logger.debug(f"Unknown file {name} exists in guild trains directory")

        # Load bingo games

        for name in listdir(f"{bd.parent}/Guilds/{guild.id}/Bingo"):
            try:
                game = await load_bingo_game(
                    filepath=f"{bd.parent}/Guilds/{guild.id}/Bingo/{name}",
                    guild=guild,
                    active_only=True,
                )
                if game.active:
                    bd.active_bingos[guild.id] = game
                    break
            except (FileNotFoundError, TypeError, ValueError, KeyError) as e:
                logger.warning(f"Error loading bingo data for guild {guild.name}: {e}")
                del_game_files(guild_id=guild.id, game_name=name, game_type="Bingo")
                logger.warning(
                    f'Invalid bingo game "{name}" in guild {guild.name}, attempted delete.'
                )
            except NotADirectoryError:
                logger.debug(f"Unknown file {name} exists in guild trains directory")


def setup_guild(guild: Guild) -> None:
    """
    Creates default guild directory structure when a guild is joined
    Args:
        guild: Guild that has been joined

    Returns:
        None
    """
    if not path.exists(f"{bd.parent}/Guilds/{guild.id}"):
        makedirs(f"{bd.parent}/Guilds/{guild.id}/Trains")
        with open(f"{bd.parent}/Guilds/{int(guild.id)}/config.json", "w") as f:
            json.dump(bd.default_config, f, indent=4)
        bd.config[int(guild.id)] = bd.default_config
        bd.responses[int(guild.id)] = []
        return None

    elif not path.isfile(f"{bd.parent}/Guilds/{int(guild.id)}/config.json"):
        with open(f"{bd.parent}/Guilds/{int(guild.id)}/config.json", "w") as f:
            json.dump(bd.default_config, f, indent=4)
        return None
    return None
