from re import findall
from discord import Member as DiscordMember
from discord.app_commands import Choice
from pathlib import Path

import logging
import matplotlib.font_manager

logger = logging.getLogger(__name__)


def load_fonts(filepath: Path) -> None:
    """
    Initializes fonts upon bot loading.
    Args:
        filepath: path to font file

    Returns:
        None
    """
    for font in matplotlib.font_manager.findSystemFonts([filepath]):
        matplotlib.font_manager.fontManager.addfont(font)


async def get_members_from_str(guild, txt: str) -> list[DiscordMember]:
    """
    Filter/validate string input to get a list of discord members
    Args:
        guild: Guild to search for members
        txt: String input

    Returns:
        List of discord members
    """
    mention_pattern = r"<@(?:!)?(\d+)>"
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
