import json
from os import makedirs, path
from shutil import rmtree
from re import findall
from discord import Member as DiscordMember
from discord.app_commands import Choice

import logging
import matplotlib.font_manager

import brbot.Core.botdata as bd

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


async def get_members_from_str(guild, txt: str) -> list[DiscordMember]:
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
