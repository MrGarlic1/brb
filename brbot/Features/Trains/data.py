from dataclasses import dataclass
from datetime import datetime

from discord import Interaction, Embed, Member
from discord.ui import View
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from brbot.db.models import TrainPlayer, TrainTile, TrainItem
from brbot.Core.botdata import bot_avatar_url, train_zones_url
from brbot.Shared.Discord.buttons import NextPgButton, PrevPgButton
from enum import Enum

from brbot.db.models import TrainGame

DEFAULT_WIDTH = 16
DEFAULT_HEIGHT = 16
RIVER_RING = 1


@dataclass
class TrainItemInfo:
    name: str
    description: str
    emoji_name: str
    uses: int
    cost: int


class RiverDirection(Enum):
    RIGHT = 0
    DOWN_RIGHT = (1,)
    DOWN = 2
    DOWN_LEFT = 3


def find_anilist_changes(
    start_anilist: list[dict], end_anilist: list[dict]
) -> list[dict]:
    anilist_changes = []
    for end_anime in end_anilist:
        start_anime = next(
            (
                start_anime
                for start_anime in start_anilist
                if start_anime["mediaId"] == end_anime["mediaId"]
            ),
            None,
        )
        if (
            start_anime == end_anime
        ):  # Skip if the show is the same at the beginning and end of game
            continue

        if not start_anime:  # Show was not on player's anilist when the game started
            anilist_changes.append(end_anime)
        else:
            episode_changes = end_anime["progress"] - start_anime["progress"]
            anilist_changes.append(
                {
                    "mediaId": end_anime["mediaId"],
                    "status": end_anime["status"],
                    "progress": episode_changes,
                }
            )

    return anilist_changes


class GameStatsView(View):
    """
    Discord UI View for handling train stats interactions.

    Attributes:
        page (int): Which response page in server's response list to display
    """

    def __init__(
        self,
        game_id: int,
        game_done: bool,
        session_generator: async_sessionmaker,
        render_service,
    ):
        super().__init__(timeout=60)
        self.add_item(PrevPgButton())
        self.add_item(NextPgButton())
        self.page = 1
        self.game_id = game_id
        self.render_service = render_service
        self.session_generator = session_generator
        self.game_done = game_done

    async def render(self, interaction: Interaction):
        async with self.session_generator() as session:
            stmt = select(TrainGame).where(TrainGame.id == self.game_id)
            stmt = stmt.options(
                selectinload(TrainGame.players).selectinload(TrainPlayer.member),
                selectinload(TrainGame.tiles).selectinload(TrainTile.player_tiles),
                selectinload(TrainGame.players).selectinload(TrainPlayer.shots),
                selectinload(TrainGame.players).selectinload(TrainPlayer.player_tiles),
            )
            result = await session.execute(stmt)
            game = result.scalars().first()

        embed, image = await self.render_service.gen_stats_embed(
            game, interaction, self.page, self.game_done
        )

        if not image:
            await interaction.response.edit_message(
                embed=embed, view=self, attachments=[]
            )
        else:
            await interaction.response.edit_message(
                embed=embed, view=self, attachments=[image]
            )


class GameRulesView(View):
    """
    Discord UI View for handling train rule interactions.

    Attributes:
        page (int): Which response page in server's response list to display
    """

    def __init__(self, page: int):
        super().__init__(timeout=60)
        self.add_item(PrevPgButton())
        self.add_item(NextPgButton())
        self.page = page

    async def render(self, interaction: Interaction):
        embed = gen_rules_embed(page=self.page)

        await interaction.response.edit_message(embed=embed, view=self)
        return False


genre_colors: dict = {
    "Action": (255, 125, 125),
    "Adventure": (102, 255, 153),
    # 'Comedy': (136, 255, 136)),
    "Drama": (245, 197, 255),
    "Ecchi": (255, 204, 204),
    "Fantasy": (76, 206, 184),
    # 'Hentai': (255, 0, 255),
    "Horror": (169, 208, 142),
    # 'Mahou_Shoujo': (255, 255, 136),
    "Mecha": (217, 217, 217),
    "Music": (185, 218, 246),
    "Mystery": (174, 170, 170),
    "Psychological": (255, 217, 102),
    "Romance": (208, 125, 163),
    "Sci-Fi": (255, 242, 204),
    "Slice of Life": (121, 157, 222),
    "Sports": (237, 125, 49),
    "Supernatural": (244, 176, 132),
    "Thriller": (161, 77, 202),
}


class GameEmoji(Enum):
    WHEAT = "🌾"
    WOOD = "🌳"
    GEMS = "💎"
    CITY = "🌃"
    PRISON = "🔒"
    HOUSE = "🏠"
    RIVER = "🏞"
    TELESCOPE = "🔭"
    GUN = "🔫"
    BUCKET = "🪣"
    BRIDGE = "🌉"
    AXE = "🪓"
    COIN = "🪙"
    MAGLEV = "🚄"
    SHOP = "🛒"
    FIRST = "🥇"
    SECOND = "🥈"
    THIRD = "🥉"


def train_game_embed(
    ctx: Interaction, name: str, width: int, height: int, members: list[Member]
) -> Embed:
    embed = Embed()
    embed.set_author(name="Anime Trains", icon_url=bot_avatar_url)
    embed.colour = 0xFF9C2C
    embed.title = "It's Train Time"
    embed.description = f'*{ctx.user.mention} has created "{name}"!*'
    embed.set_thumbnail(url=ctx.user.avatar.url)

    embed.add_field(name="Board Size", value=f"{width} by {height}", inline=True)
    player_mentions = []
    for member in members:
        player_mentions.append(member.mention)
    embed.add_field(name="Players", value=", ".join(player_mentions), inline=True)
    embed.add_field(
        name="\u200b", value="**Players, check your DMs to see your board!**"
    )
    embed.set_footer(text=datetime.now())

    return embed


def gen_rules_embed(page: int) -> Embed:
    max_pages: int = 6
    page: int = 1 + (page % max_pages)  # Loop back through pages both ways
    if page == 1:
        embed = train_rules_embed()
    elif page == 2:
        embed = train_zones_embed()
    elif page == 3:
        embed = train_symbols_embed()
    elif page == 4:
        embed = train_quests_embed()
    elif page == 5:
        embed = train_items_embed()
    else:
        embed = train_scoring_embed()
    embed.set_footer(text=f"Page {page}/{max_pages}")
    return embed


def train_symbols_embed() -> Embed:
    embed = Embed()
    embed.set_author(name="Anime Trains", icon_url=bot_avatar_url)
    embed.colour = 0xFF9C2C
    embed.title = "Symbol Reference"
    embed.add_field(
        name=f"{GameEmoji.WHEAT.value}: Wheat",
        value="Plus 1 point if connected to your network. Plus 3 more points if connected to a city. "
        "Each additional wheat is worth 1 point only.",
        inline=True,
    )
    embed.add_field(
        name=f"{GameEmoji.WOOD.value}: Wood",
        value="Provides 2 points for each wood connected to your network.",
        inline=True,
    )
    embed.add_field(
        name=f"{GameEmoji.GEMS.value}: Gems",
        value="Provides 2 points if connected to your network. "
        "The first player to connect gems to their network gets 3 bonus points.",
        inline=True,
    )
    embed.add_field(name="\u200b", value="\u200b", inline=False)
    embed.add_field(
        name=f"{GameEmoji.CITY.value}: City",
        value="Provides stated bonuses. Each city has a favorite season (revealed at end). "
        "Any player who shoots a city with the correct season gets 3 bonus points.",
        inline=True,
    )
    embed.add_field(
        name=f"{GameEmoji.PRISON.value}: Prison",
        value="Reduces points that other players get for intersections with your rails by 1. "
        "Reduces points gained by your own houses by 1 for each house.",
        inline=True,
    )
    embed.add_field(
        name=f"{GameEmoji.HOUSE.value}: House",
        value="Provides 1 points for each house connected to your network. "
        "If the house is connected to a city, then the player gains 1 bonus point per house. "
        "If the house is connected to a prison, the player loses 1 point per house.",
        inline=True,
    )
    embed.add_field(
        name=f"{GameEmoji.RIVER.value} Gray dotted tiles: River",
        value="Shots made on rivers use double the normal amount of rails.",
        inline=False,
    )
    return embed


def train_quests_embed() -> Embed:
    embed = Embed()
    embed.set_author(name="Anime Trains", icon_url=bot_avatar_url)
    embed.colour = 0xFF9C2C
    embed.title = "Quests"
    embed.description = "*Quests may be completed by every player once.*"

    embed.add_field(
        name="\u200b",
        value='**1.** Completely watch one show with the "trains" tag. **Reward: 3**\n\n'
        "**2.** Make at least two shots of your least watched genre (excluding Hentai). **Reward: 4**\n\n"
        "**3.** Make a shot of shows with each of the following sources: "
        "Anime original, manga, light novel, mugi original. **Reward: 3**\n\n"
        "**4.** Do not make a single shot of a genre on its corresponding zone. **Reward: 3**\n\n"
        "**5.** Make shots with at least three shows from another player's list. **Reward: 2**\n\n"
        "**6.** Place six rails in a row on squares without resources. **Reward: 3**",
        inline=False,
    )
    return embed


def train_scoring_embed() -> Embed:
    embed = Embed()
    embed.set_author(name="Anime Trains", icon_url=bot_avatar_url)
    embed.colour = 0xFF9C2C
    embed.title = "Scoring"
    embed.description = (
        "**1.** Each player's score is calculated at the end of the game.\n\n"
        "**2.** Players earn points from the sources listed below:\n"
        "- The 1st/2nd player to finish their track earn 2/1 bonus points respectively.\n"
        "- Points from resources (see page 3) and points from quests (see page 4).\n"
        "- Players earn 1 point each time their track intersects another player's track.\n"
        "- For every 3 rails less than 26 that a player uses, they gain 2 points. "
        "For every 3 rails over 26, that player loses 2 points.\n"
    )
    return embed


def train_rules_embed() -> Embed:
    embed = Embed()
    embed.set_author(name="Anime Trains", icon_url=bot_avatar_url)
    embed.colour = 0xFF9C2C
    embed.title = "Rules"
    embed.description = (
        "**1.** Each shot (3 hours) corresponds to one track being placed down.\n\n"
        "**2.** Rails may intersect. Each intersection awards both players with an extra point. "
        "No more than two player's rails can intersect in the same location.\n\n"
        "**3.** Rails may be placed directly adjacent to any existing rails, but it must follow a single path. "
        "(No self-intersections). In addition, there must be at least one space between your rails "
        "unless they are connected.\n\n"
        "**4.** The board is generated randomly at the start of the game, and the points are tallied at "
        "the end of the game. The player with the most points at the end of the game wins.\n\n"
    )
    return embed


def train_zones_embed() -> Embed:
    embed = Embed()
    embed.set_author(name="Anime Trains", icon_url=bot_avatar_url)
    embed.colour = 0xFF9C2C
    embed.title = "Genre Zones"
    embed.description = (
        "If the primary show used for a shot has a genre matching the genre zone of the shot, "
        "only 1/2 of the usual amount of rails are consumed."
    )

    embed.add_field(
        name="\u200b",
        inline=False,
        value="**Genre zones appear as the following colors on the trains board:**",
    )
    embed.set_image(url=train_zones_url)
    return embed


def train_items_embed() -> Embed:
    embed = Embed()
    embed.set_author(name="Anime Trains", icon_url=bot_avatar_url)
    embed.colour = 0xFF9C2C
    embed.title = "Item Reference"
    for _, item in DEFAULT_SHOP_DEFINITION:
        embed.add_field(
            name=f"{GameEmoji[item.emoji_name].value} {item.name}",
            value=f"*Cost: {item.cost}*\n{item.description}",
            inline=True,
        )
    return embed


DEFAULT_SHOP_DEFINITION = [
    (
        3,
        TrainItemInfo(
            name="Telescope",
            emoji_name=GameEmoji.TELESCOPE.name,
            description="Permanently increases your vision by 1!",
            uses=0,
            cost=3,
        ),
    ),
    (
        1,
        TrainItemInfo(
            name="Gun",
            emoji_name=GameEmoji.GUN.name,
            description="Increase the prison's intersection penalty for other players by 0.5!",
            uses=0,
            cost=5,
        ),
    ),
    (
        4,
        TrainItemInfo(
            name="Bucket",
            emoji_name=GameEmoji.BUCKET.name,
            description="Allows you to create 3 river tiles at locations of your choice! (consumable)",
            cost=1,
            uses=3,
        ),
    ),
    (
        4,
        TrainItemInfo(
            name="Pontoon Bridge",
            emoji_name=GameEmoji.BRIDGE.name,
            description="Allows you to use 0 rails when placing on a river tile! (consumed when entering a river)",
            cost=1,
            uses=3,
        ),
    ),
    (
        2,
        TrainItemInfo(
            name="Axe",
            emoji_name=GameEmoji.AXE.name,
            description=f"Increase points gained from {GameEmoji.WOOD.value} tiles by 0.5!",
            cost=3,
            uses=0,
        ),
    ),
    (
        4,
        TrainItemInfo(
            name="Coin",
            emoji_name=GameEmoji.COIN.name,
            description="Increases your score by 2!",
            cost=3,
            uses=0,
        ),
    ),
    (
        2,
        TrainItemInfo(
            name="MagLev",
            emoji_name=GameEmoji.MAGLEV.name,
            description="Faster trains! "
            "Permanently decreases the anime requirement for rails from 3 hours to 2 hours.",
            cost=3,
            uses=0,
        ),
    ),
]


def make_default_shop(game_id) -> list[TrainItem]:
    return [
        TrainItem(game_id=game_id, **vars(defn))
        for count, defn in DEFAULT_SHOP_DEFINITION
        for _ in range(count)
    ]
