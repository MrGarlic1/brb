from dataclasses import dataclass
from discord import Member, DMChannel, Interaction, Embed
from discord.ui import View
from brbot.Core.botdata import linked_profiles, bot_avatar_url, train_zones_url
from brbot.Shared.buttons import NextPgButton, PrevPgButton


@dataclass
class TrainShot:
    def __init__(self, row: int, col: int, show_id: int, info: str, time: str):
        self.row = row
        self.col = col
        self.show_id = show_id
        self.info = info
        self.time = time

    def coords(self) -> tuple[int, int]:
        return self.row, self.col


@dataclass
class TrainTile:
    def __init__(
        self,
        resource: str = None,
        terrain: str = None,
        zone: str = None,
        rails: list[str] = None,
    ):
        self.resource = resource
        self.terrain = terrain
        self.zone = zone
        self.rails = rails
        if self.rails is None:
            self.rails = []


class TrainItem:
    def __init__(
        self,
        name: str,
        emoji: str,
        description: str,
        amount: int,
        cost: float,
        showinfo: str = "",
        uses: int = -1,
    ):
        self.name = name
        self.emoji = emoji
        self.description = description
        self.amount = amount
        self.cost = cost
        self.showinfo = showinfo
        self.uses = uses

    def inv_entry(self):
        return f"{self.emoji}: (x{self.amount})"

    def shop_entry(self):
        return f"{self.emoji} {self.name} (x{self.amount}) (Cost {self.cost}): {self.description}"

    def __repr__(self):
        return f"{self.name} {self.emoji} {self.description} {self.amount} {self.cost} {self.showinfo}"


@dataclass
class TrainPlayer:
    def __init__(
        self,
        member: Member = None,
        tag: str = None,
        dmchannel: DMChannel = None,
        rails: int = 0,
        shots: list[TrainShot] = None,
        vis_tiles: list[tuple] = None,
        score: dict[str, int] = None,
        start: tuple = None,
        end: tuple = None,
        done: bool = False,
        donetime: str = None,
        inventory: dict = None,
        shops_used: list[tuple[int, int]] = None,
        anilist_id: int = None,
        least_watched_genre: str = None,
        starting_anilist: list = None,
    ):
        if vis_tiles is None:
            vis_tiles = []
        if score is None:
            score = {}
        if shots is None:
            shots = []
        if inventory is None:
            inventory = {}
        if shops_used is None:
            shops_used = []
        if anilist_id is None:
            anilist_id = linked_profiles[member.id]

        self.member = member
        self.tag = tag
        self.done = done
        self.rails = rails
        self.dmchannel = dmchannel
        self.start = start
        self.end = end
        self.score: dict[str, int] = score
        self.shots = shots
        self.donetime = donetime
        self.vis_tiles = vis_tiles
        self.inventory = inventory
        self.shops_used: list[tuple[int, int]] = shops_used
        self.anilist_id = anilist_id
        self.least_watched_genre = least_watched_genre
        self.starting_anilist = starting_anilist

    def asdict(self) -> dict:
        shot_list = []
        for shot in self.shots:
            shot_list.append(shot.__dict__)
        item_dict = {}
        for name, item in self.inventory.items():
            item_dict[name] = item.__dict__
        return {
            "member_id": self.member.id,
            "tag": self.tag,
            "done": self.done,
            "rails": self.rails,
            "dmchannel": self.dmchannel.id,
            "start": self.start,
            "end": self.end,
            "score": self.score,
            "shots": shot_list,
            "donetime": self.donetime,
            "vis_tiles": self.vis_tiles,
            "inventory": item_dict,
            "anilist_id": self.anilist_id,
            "starting_anilist": self.starting_anilist,
            "least_watched_genre": self.least_watched_genre,
        }

    def update_item_count(self, itemname) -> None:
        self.inventory[itemname].uses -= 1

        if self.inventory[itemname].uses == 0:
            self.inventory[itemname].amount -= 1

        if self.inventory[itemname].amount == 0:
            self.inventory.pop(itemname)


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

    def __init__(self, game):
        super().__init__(timeout=60)
        self.add_item(PrevPgButton())
        self.add_item(NextPgButton())
        self.page = 1
        self.game = game

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.data["custom_id"] == "prev_page":
            self.page -= 1

        elif interaction.data["custom_id"] == "next_page":
            self.page += 1

        embed, image = self.game.gen_stats_embed(interaction, self.page)

        if not image:
            await interaction.response.edit_message(
                embed=embed, view=self, attachments=[]
            )
        else:
            await interaction.response.edit_message(
                embed=embed, view=self, attachments=[image]
            )
        return False


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

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.data["custom_id"] == "prev_page":
            self.page -= 1

        elif interaction.data["custom_id"] == "next_page":
            self.page += 1

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

game_emoji: dict = {
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
    "third": "🥉",
}


def train_game_embed(ctx: Interaction, game) -> Embed:
    embed = Embed()
    embed.set_author(name="Anime Trains", icon_url=bot_avatar_url)
    embed.colour = 0xFF9C2C
    embed.title = "It's Train Time"
    embed.description = f'*{ctx.user.mention} has created "{game.name}"!*'
    embed.set_thumbnail(url=ctx.user.avatar.url)

    embed.add_field(
        name="Board Size", value=f"{game.size[0]} by {game.size[1]}", inline=True
    )
    player_mentions = []
    for player in game.players:
        player_mentions.append(f"<@{player.member.id}>")
    embed.add_field(name="Players", value=", ".join(player_mentions), inline=True)
    embed.add_field(
        name="\u200b", value="**Players, check your DMs to see your board!**"
    )
    embed.set_footer(text=game.date)

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
        name=f"{game_emoji['wheat']}: Wheat",
        value="Plus 1 point if connected to your network. Plus 3 more points if connected to a city. "
        "Each additional wheat is worth 1 point only.",
        inline=True,
    )
    embed.add_field(
        name=f"{game_emoji['wood']}: Wood",
        value="Provides 2 points for each wood connected to your network.",
        inline=True,
    )
    embed.add_field(
        name=f"{game_emoji['gems']}: Gems",
        value="Provides 2 points if connected to your network. "
        "The first player to connect gems to their network gets 3 bonus points.",
        inline=True,
    )
    embed.add_field(name="\u200b", value="\u200b", inline=False)
    embed.add_field(
        name=f"{game_emoji['city']}: City",
        value="Provides stated bonuses. Each city has a favorite season (revealed at end). "
        "Any player who shoots a city with the correct season gets 3 bonus points.",
        inline=True,
    )
    embed.add_field(
        name=f"{game_emoji['prison']}: Prison",
        value="Reduces points that other players get for intersections with your rails by 1. "
        "Reduces points gained by your own houses by 1 for each house.",
        inline=True,
    )
    embed.add_field(
        name=f"{game_emoji['house']}: House",
        value="Provides 1 points for each house connected to your network. "
        "If the house is connected to a city, then the player gains 1 bonus point per house. "
        "If the house is connected to a prison, the player loses 1 point per house.",
        inline=True,
    )
    embed.add_field(
        name=f"{game_emoji['river']} Gray dotted tiles: River",
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
    for item in default_shop().values():
        embed.add_field(
            name=f"{item.emoji} {item.name}",
            value=f"*Cost: {item.cost}*\n{item.description}",
            inline=True,
        )
    return embed


def default_shop() -> dict[str, TrainItem]:
    return {
        "Telescope": TrainItem(
            name="Telescope",
            emoji=game_emoji["telescope"],
            description="Permanently increases your vision by 1!",
            cost=3,
            amount=2,
        ),
        "Gun": TrainItem(
            name="Gun",
            emoji=game_emoji["gun"],
            description="Increase the prison's intersection penalty for other players by 0.5!",
            cost=5,
            amount=1,
        ),
        "Bucket": TrainItem(
            name="Bucket",
            emoji=game_emoji["bucket"],
            description="Allows you to create 3 river tiles at locations of your choice! (consumable)",
            cost=1,
            amount=4,
            uses=3,
        ),
        "Pontoon Bridge": TrainItem(
            name="Pontoon Bridge",
            emoji=game_emoji["bridge"],
            description="Allows you to use 0 rails when placing on a river tile! (consumed when entering a river)",
            cost=1,
            amount=4,
            uses=3,
        ),
        "Axe": TrainItem(
            name="Axe",
            emoji=game_emoji["axe"],
            description=f"Increase points gained from {game_emoji['wood']} tiles by 0.5!",
            cost=3,
            amount=2,
        ),
        "Coin": TrainItem(
            name="Coin",
            emoji=game_emoji["coin"],
            description="Increases your score by 2!",
            cost=3,
            amount=4,
        ),
        "MagLev": TrainItem(
            name="MagLev",
            emoji=game_emoji["maglev"],
            description="Faster trains! "
            "Permanently decreases the anime requirement for rails from 3 hours to 2 hours.",
            cost=3,
            amount=2,
        ),
    }
