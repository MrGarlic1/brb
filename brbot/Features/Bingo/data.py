from dataclasses import dataclass
from brbot.Shared.Discord.buttons import PrevPgButton, NextPgButton
from discord.ui import View
from discord import Interaction, Embed
from enum import Enum
from datetime import datetime

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from brbot.Features.Bingo.renderservice import BingoRenderService

import brbot.Core.botdata as bd

BOARD_SIZE = 5

bingo_tags = (
    "95%",
    "Action",
    "Adventure",
    "Aliens",
    "Comedy",
    "Coming of Age",
    "Crime",
    "Cute Girls Doing Cute Things",
    "Death Game",
    "Youkai",
    "Drama",
    "Dystopian",
    "Ecchi",
    "Ensemble Cast",
    "Episodic",
    "Fantasy",
    "Female Protagonist",
    "Food",
    "Gloppy",
    "Gods/Mythology",
    "Guns",
    "Heterosexual",
    "Horror",
    "Isekai",
    "Kuudere",
    "LGBTQ+ Themes",
    "Love Triangle",
    "Magic",
    "Mahou Shoujo",
    "Male Protagonist",
    "Mecha",
    "Music",
    "Mystery",
    "Not TV",
    "Parody",
    "Philosophy",
    "Primarily Female Cast",
    "Primarily Male Cast",
    "Psychological",
    "Revenge",
    "Rewatch an Anime",
    "Romance",
    "School",
    "Sci-Fi",
    "Seinen",
    "Shoujo",
    "Shounen",
    "Slice of Life",
    "Source Not Manga",
    "Sports",
    "Super Power",
    "Supernatural",
    "Thriller",
    "Time Manipulation",
    "Tragedy",
    "Tsundere",
    "Urban/Urban Fantasy",
    "Yandere",
)
character_tags = ("Large Breasts", "Loli", "Monster Girl", "Black Guy", "Cat")
season_tags = ("Spring", "Summer", "Fall", "Winter")
episode_tags = {
    "<7 Episodes": (0, 6),
    "11-13 Episodes": (11, 13),
    "22-26 Episodes": (22, 26),
    "50-99 Episodes": (50, 99),
    "100+ Episodes": (100, 99999),
}

col_emojis = ("🇧", "🇮", "🇳", "🇬", "🇴")
row_emojis = ("1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣")


class BingoMode(Enum):
    STANDARD = 0


class ShotType(Enum):
    CHARACTER = 0
    EPISODE = 1
    SOURCE = 2
    SEASON = 3
    FREE = 5
    REWATCH = 6
    NOT_TV = 7
    NINETY_FIVE_PERCENT = 8
    TAG = 9
    OTHER = 10


@dataclass(frozen=True)
class FrozenBingoTile:
    coordinates: tuple[int, int]
    hit: bool
    tag: str


@dataclass(frozen=True)
class FrozenBingoPlayer:
    discord_user_id: int
    total_shots: int
    total_hit_shots: int
    tiles: list[FrozenBingoTile]


def bingo_game_embed(
    ctx: Interaction, game_name: str, game_date: datetime, player_mentions: list[str]
) -> Embed:
    embed = Embed()
    embed.set_author(name="Anime Bingo", icon_url=bd.bot_avatar_url)
    embed.colour = 0xFF9C2C
    embed.title = "It's Bingo Time"
    embed.description = f'*{ctx.user.mention} has created "{game_name}"!*'
    embed.set_thumbnail(url=ctx.user.avatar.url)
    embed.add_field(name="Players", value=", ".join(player_mentions), inline=True)
    embed.add_field(name="\u200b", value="**Players, good luck!**")
    embed.set_footer(text=game_date.strftime("%Y/%m/%d"))
    return embed


def gen_rules_embed(page: int) -> Embed:
    max_pages: int = 6
    page: int = 1 + (page % max_pages)  # Loop back through pages both ways
    embed = Embed()
    embed.set_author(name="Anime Trains", icon_url=bd.bot_avatar_url)
    embed.colour = 0xFF9C2C
    embed.set_footer(text=f"Page {page}/{max_pages}")
    if page == 1:
        embed.title = "Rules"
        embed.description = (
            "**1.** To win, you must obtain bingo by hitting the randomly generated tags on your bingo board.\n\n"
            "**2.** Each shot corresponds to 3 hours of TV airing time. and can select one tag to shoot for. \n\n"
            "**3.** Once a certain tag has been shot, that tag will not appear again on your board. "
            "**4.** Certain shots require players to agree that the show/character matches the tag. In that case,"
            "a poll will be created. After 2 hours, if the majority agree, the shot will be marked as valid.\n\n"
            "**5.** There are 75 possible tags, which are listed on the next page. Only 25 will appear on each board."
        )
    elif page == 2:
        embed.title = "Possible Tags"
        embed.description = "tbd"
    embed.set_footer(text=f"Page {page}/{max_pages}")
    return embed


class GameBoardView(View):
    """
    Discord UI View for handling bingo board interactions.

    Attributes:
        page (int): Which response page in server's response list to display
    """

    def __init__(
        self,
        render_service: BingoRenderService,
        players: list[FrozenBingoPlayer],
        page: int = 0,
    ):
        super().__init__(timeout=60)
        self.add_item(PrevPgButton())
        self.add_item(NextPgButton())
        self.page = page
        self.players = players
        self.render_service = render_service

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.data["custom_id"] == "prev_page":
            self.page -= 1

        elif interaction.data["custom_id"] == "next_page":
            self.page += 1

        self.page = 1 + (self.page % len(self.players))

        embed, image = self.render_service.gen_board_embed(
            players=self.players,
            discord_member=interaction.user,
            page=self.page,
        )

        await interaction.response.edit_message(embed=embed, view=self)
        return False


class GameRulesView(View):
    """
    Discord UI View for handling bingo rule interactions.

    Attributes:
        page (int): Which response page in server's response list to display
    """

    def __init__(self, page: int):
        super().__init__(timeout=60)
        self.add_item(PrevPgButton())
        self.add_item(NextPgButton())
        self.page = page

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.data["custom_id"] == "prev_page":
            self.page -= 1

        elif interaction.data["custom_id"] == "next_page":
            self.page += 1

        embed = gen_rules_embed(page=self.page)

        await interaction.response.edit_message(embed=embed, view=self)
        return False
