import io
import json
from dataclasses import dataclass
from random import sample
from brbot.Shared.buttons import PrevPgButton, NextPgButton
from discord.ui import View
from discord import Interaction, Guild, Embed, File, Member, DMChannel, Message

from PIL import Image, ImageFont, ImageDraw

import brbot.Core.botdata as bd


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
    "Yandere"
)
character_tags = (
    "Large Breasts",
    "Loli",
    "Monster Girl",
    "Black Guy",
    "Cat"
)
season_tags = (
    "Spring",
    "Summer",
    "Fall",
    "Winter"
)
episode_tags = {
    "<7 Episodes": (0, 6),
    "11-13 Episodes": (11, 13),
    "22-26 Episodes": (22, 26),
    "50-99 Episodes": (50, 99),
    "100+ Episodes": (100, 99999)
}

col_emojis = ("🇧", "🇮", "🇳", "🇬", "🇴")
row_emojis = ("1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣")


@dataclass
class BingoShot:
    def __init__(self, anilist_id: int, tag: str, time: str, info: str, hit: bool = False):
        self.anilist_id = anilist_id
        self.tag = tag
        self.time = time
        self.hit = hit
        self.info = info

    def get_shot_type(self) -> str | None:
        if self.tag in character_tags:
            return "character"
        elif self.tag in episode_tags:
            return "episode"
        elif self.tag == "Source Not Manga":
            return "source"
        elif self.tag in season_tags:
            return "season"
        elif self.tag == "Gloppy":
            return "free"
        elif self.tag == "Rewatch an Anime":
            return "rewatch"
        elif self.tag == "Not TV":
            return "not_tv"
        elif self.tag == "95%":
            return "95%"
        elif self.tag in bingo_tags:
            return "tag"
        else:
            return None

    async def is_valid(self, starting_anilist: dict, anilist_info: dict, poll_msg: Message = None) -> bool:
        shot_type = self.get_shot_type()
        if shot_type == "not_tv":
            return anilist_info["format"] != "TV"
        if shot_type == "free":
            return True
        if shot_type == "source":
            return anilist_info["source"] != "MANGA"
        if shot_type == "season":
            return self.tag.upper() == anilist_info["season"]
        if shot_type == "95%":
            return any(tag["rank"] > 95 for tag in anilist_info["tags"])
        if shot_type == "tag":
            return (
                    any(tag["name"].upper() == self.tag.upper() and tag["rank"] > 40 for tag in anilist_info["tags"]) or
                    any(genre.upper() == self.tag.upper() for genre in anilist_info["genres"])
            )
        if shot_type == "character":
            yes_votes = 1
            no_votes = 1
            for reaction in poll_msg.reactions:
                if reaction.emoji == "🔺":
                    yes_votes = reaction.count
                elif reaction.emoji == "🔻":
                    no_votes = reaction.count

            return yes_votes / (no_votes + yes_votes) > 0.5
        if shot_type == "rewatch":
            for show in starting_anilist:
                if show["mediaId"] != self.anilist_id:
                    continue
                if show["status"] in ("REWATCHING", "COMPLETED"):
                    return True
            return False
        if shot_type == "episode":
            return episode_tags[self.tag][0] <= anilist_info["episodes"] <= episode_tags[self.tag][1]
        return False


@dataclass
class BingoTile:
    def __init__(self, tag: str = "", hit: bool = False):
        self.tag = tag
        self.hit = hit

    def asdict(self) -> dict:
        return {
            "tag": self.tag, "hit": self.hit
        }


@dataclass
class BingoPlayer:
    def __init__(
            self, member: Member = None, dmchannel: DMChannel = None,
            shots: list[BingoShot] = None, done: bool = False, donetime: str = None, anilist_id: int = None,
            starting_anilist: list = None, board: dict[tuple[int, int], BingoTile] = None
    ):
        if shots is None:
            shots = []
        if anilist_id is None:
            anilist_id = bd.linked_profiles[member.id]
        if board is None:
            self.gen_board()
        else:
            self.board = board

        self.member = member
        self.done = done
        self.dmchannel = dmchannel
        self.shots = shots
        self.donetime = donetime
        self.anilist_id = anilist_id
        self.starting_anilist = starting_anilist

    def asdict(self) -> dict:
        shot_list = []
        for shot in self.shots:
            shot_list.append(shot.__dict__)
        board_dict = {}
        for coord, tile in self.board.items():
            board_dict[str(coord)] = tile.__dict__
        board_dict = {}
        for pos, tile in self.board.items():
            board_dict[str(pos)] = tile.asdict()
        return {
            "member_id": self.member.id, "done": self.done, "dmchannel": self.dmchannel.id,
            "shots": shot_list, "donetime": self.donetime, "anilist_id": self.anilist_id,
            "starting_anilist": self.starting_anilist, "board": board_dict
        }

    def gen_board(self) -> None:
        selected_tags = sample(bingo_tags, 25)

        board = {}
        for col in range(1, 6):
            for row in range(1, 6):
                board[col, row] = BingoTile(tag=selected_tags[0])
                del selected_tags[0]
        self.board = board

    def find_tag(self, tag) -> tuple[int, int] | None:
        for pos in self.board:
            if self.board[pos].tag == tag:
                return pos
        return None

    def has_bingo(self) -> bool:
        row_bingos = {1: [], 2: [], 3: [], 4: [], 5: []}
        for col in range(1, 6):
            col_bingo = []
            for row in range(1, 6):
                if self.board[(col, row)].hit:
                    col_bingo.append((col, row))
                    row_bingos[row].append((col, row))
                    if len(row_bingos[row]) == 5 or len(col_bingo) == 5:
                        return True
                    if len(col_bingo) == 5:
                        return True

        # Check diagonal bingos
        if all(tile.hit for tile in (
                self.board[1, 1], self.board[2, 2], self.board[3, 3], self.board[4, 4], self.board[5, 5])
               ):
            return True
        if all(tile.hit for tile in (
                self.board[1, 5], self.board[2, 4], self.board[3, 3], self.board[4, 2], self.board[5, 1])
               ):
            return True
        return False

    def draw_board_img(
            self, filepath: str, board_name: str, draw_tags: bool = False,
    ) -> None | str:

        # Generate board image. If player board: only generate tiles which are rendered.
        # Grey out other tiles.

        # Adjustments
        label_offset: int = 1
        size = 5
        label_font_size: int = 72
        font = ImageFont.truetype(f"{bd.parent}/Shared/ggsans/ggsans-Bold.ttf", label_font_size)
        tile_pixels: int = 150
        border_color: tuple[int, int, int] = (190, 190, 190)
        font_color: tuple[int, int, int] = (0, 0, 0)
        empty_color: tuple[int, int, int] = (255, 255, 255)
        hit_color: tuple[int, int, int] = (0, 255, 0)

        board_img = Image.new(
            mode="RGB",
            size=((size + label_offset) * tile_pixels, (size + label_offset) * tile_pixels),
            color=0xFFFFFF
        )
        draw: ImageDraw = ImageDraw.Draw(board_img)

        # Draw column labels/tile borders

        for label_x in range(1, size + 1):
            col_labels = \
                ("B", "E", "N", "G", "O") if self.member.id == 302266697488924672 else ("B", "I", "N", "G", "O")
            draw.rectangle(
                xy=((label_x * tile_pixels, 1), ((label_x + 1) * tile_pixels, tile_pixels)),
                fill=empty_color, outline=border_color, width=1
            )
            draw.text(
                xy=(label_x * tile_pixels + tile_pixels / 2, tile_pixels / 2), text=col_labels[label_x - 1], font=font,
                anchor="mm",
                fill=font_color
            )
        # Draw row labels/tile borders
        for label_y in range(1, size + 1):
            draw.rectangle(
                xy=((1, label_y * tile_pixels), (tile_pixels, (label_y + 1) * tile_pixels)),
                fill=empty_color, outline=border_color, width=1
            )
            draw.text(
                xy=(round(tile_pixels / 2), label_y * tile_pixels + round(tile_pixels / 2)),
                text=str(label_y), font=font, anchor="mm", fill=font_color
            )
        # Draw game tiles

        default_font_size: int = 24
        font_size = default_font_size
        font = ImageFont.truetype(f"{bd.parent}/Shared/ggsans/ggsans-Bold.ttf", font_size)

        for coords in self.board.keys():
            (row, col) = coords
            # Fill tiles with correct color, if empty, skip to next
            if self.board[coords].hit:
                draw.rectangle(
                    xy=((col * tile_pixels, row * tile_pixels), ((col + 1) * tile_pixels, (row + 1) * tile_pixels)),
                    fill=hit_color, outline=border_color, width=1
                )
            else:
                draw.rectangle(
                    xy=((col * tile_pixels, row * tile_pixels), ((col + 1) * tile_pixels, (row + 1) * tile_pixels)),
                    fill=empty_color, outline=border_color, width=1
                )

            text_pixels = draw.textlength(text=self.board[coords].tag, font=font)
            if self.board[coords].hit or draw_tags:
                while text_pixels > 0.8 * tile_pixels and font_size > 6:
                    font_size -= 2
                    font = ImageFont.truetype(f"{bd.parent}/Shared/ggsans/ggsans-Bold.ttf", font_size)
                    text_pixels = draw.textlength(text=self.board[coords].tag, font=font)

                # Draw tile resource and rails

                draw.text(
                    xy=(
                        col * tile_pixels + round(tile_pixels / 2), row * tile_pixels + round(tile_pixels / 2)
                    ),
                    text=self.board[coords].tag, anchor="mm", fill=font_color, font=font,
                )

                if font_size != default_font_size:
                    font_size = default_font_size
                    font = ImageFont.truetype(f"{bd.parent}/Shared/ggsans/ggsans-Bold.ttf", font_size)

        try:
            board_img.save(f"{filepath}/{board_name}.png")
        except PermissionError:
            return "Could not write the board. Try again in a few seconds..."
        return None


class BingoGame:
    def __init__(
            self, name: str = None, date: str = None, players: list[BingoPlayer] = None, gameid: int = None,
            active: bool = True, known_entries: dict[int, dict] = None
    ):
        if players is None:
            players: list[BingoPlayer] = []
        if known_entries is None:
            known_entries = {}

        self.name = name
        self.date = date
        self.players = players
        self.gameid = gameid
        self.active = active
        self.known_entries = known_entries

    def asdict(self) -> dict:
        player_list = []
        for player in self.players:
            player_list.append(player.asdict())
        return {
            "name": self.name, "date": self.date, "players": player_list, "gameid": self.gameid, "active": self.active,
            "known_entries": self.known_entries
        }

    def __repr__(self) -> str:
        return f"<name={self.name}> <date={self.date}> <players={self.players}> <gameid={self.gameid}> " \
               f"<active={self.active}>"

    def is_done(self) -> bool:
        done = False
        for player in self.players:
            if player.done:
                done = True
                break
        return done

    def get_player(self, player_id: int) -> tuple[None, None] | tuple[int, BingoPlayer]:
        player = None
        player_idx = None
        for idx, p in enumerate(self.players):
            if p.member.id == player_id:
                player = p
                player_idx = idx
        return player_idx, player

    def save_game(self, filepath: str) -> None:
        with open(f"{filepath}/gamedata.json", "w") as f:
            json.dump(self.asdict(), f, indent=4, separators=(",", ":"))

    def update_game_after_shot(
            self, ctx: Interaction, shot: BingoShot, player_idx: int, hit_tile: tuple[int, int] = None
    ) -> None:

        # Push updates to player boards, check if game is finished

        if self.active:
            bd.active_bingos[ctx.guild_id] = self
        else:
            del bd.active_bingos[ctx.guild_id]

        self.players[player_idx].shots.append(shot)
        if hit_tile:
            self.players[player_idx].board[hit_tile].hit = True

        self.save_game(f"{bd.parent}/Guilds/{ctx.guild_id}/Bingo/{self.name}")
        return None

    def update_boards_after_create(
            self, ctx: Interaction
    ) -> None:
        # Update master board/game state
        self.save_game(f"{bd.parent}/Guilds/{ctx.guild_id}/Bingo/{self.name}")
        bd.active_bingos[ctx.guild_id] = self
        return None

    def gen_board_embed(
            self, page: int, sender_idx: int
    ) -> tuple[Embed, File]:

        embed: Embed = Embed()
        embed.set_author(name=f"Anime Bingo", icon_url=bd.bot_avatar_url)
        max_pages: int = len(self.players)
        page: int = 1 + (page % max_pages)  # Loop back through pages both ways
        embed.set_footer(text=f'Page {page}/{max_pages}')

        # Player stats page
        player_idx: int = page - 1
        player: BingoPlayer = self.players[player_idx]
        if player_idx == sender_idx:
            draw_tags = False
        else:
            draw_tags = True
        player.draw_board_img(
            filepath=f"{bd.parent}/Guilds/{player.member.guild.id}/Bingo/{self.name}",
            board_name=f"{sender_idx}",
            draw_tags=draw_tags
        )

        embed.set_thumbnail(url=player.member.avatar.url)
        embed.description = f"### Board for {player.member.mention}"

        total_hits = len([shot.hit for shot in player.shots if shot.hit])
        if len(player.shots) > 0:
            embed.add_field(name="\u200b", value=f"**Total Shots:** {len(player.shots)}", inline=True)
            embed.add_field(
                name="\u200b", value=f"**Accuracy:** {round(100*total_hits/len(player.shots), 2)}%", inline=True
            )
        else:
            embed.add_field(name="\u200b", value=f"\u200b", inline=False)

        with open(
                f"{bd.parent}/Guilds/{player.member.guild.id}/Bingo/{self.name}/{sender_idx}.png", "rb"
        ) as f:
            file = io.BytesIO(f.read())
        image = File(file, filename="bingo_board.png")

        embed.set_image(
            url="attachment://bingo_board.png"
        )
        return embed, image


async def load_bingo_game(
        filepath: str, guild: Guild, active_only: bool = False
) -> BingoGame | None:
    with open(f"{filepath}/gamedata.json", "r") as f:
        game_dict = json.load(f)
    if active_only and not game_dict["active"]:  # Skip loading inactive games if specified for faster loads
        return BingoGame(active=False)
    # Convert player dicts back into player classes
    player_list: list = []
    for player in game_dict["players"]:

        shot_list: list = []
        for shot in player["shots"]:
            shot_list.append(
                BingoShot(
                    anilist_id=shot["anilist_id"], tag=shot["tag"], time=shot["time"], info=shot["info"]
                )
            )
        member = await guild.fetch_member(player["member_id"])

        board: dict = {}
        for pos, tile in player["board"].items():
            coords = pos[1:-1].split(",")
            coords[0] = int(coords[0])
            coords[1] = int(coords[1])
            board[tuple(coords)] = BingoTile(tag=tile["tag"], hit=tile["hit"])

        player_list.append(
            BingoPlayer(
                member=member, done=player["done"],
                dmchannel=member.dm_channel, shots=shot_list, donetime=player["donetime"],
                starting_anilist=player["starting_anilist"],
                anilist_id=player["anilist_id"], board=board
            )
        )

    game = BingoGame(
        name=game_dict["name"],
        date=game_dict["date"],
        players=player_list,
        gameid=game_dict["gameid"],
        active=game_dict["active"],
        known_entries=game_dict["known_entries"],
    )
    return game


def bingo_game_embed(ctx: Interaction, game: BingoGame) -> Embed:
    embed = Embed()
    embed.set_author(name="Anime Bingo", icon_url=bd.bot_avatar_url)
    embed.colour = 0xff9c2c
    embed.title = "It's Bingo Time"
    embed.description = f"*{ctx.user.mention} has created \"{game.name}\"!*"
    embed.set_thumbnail(url=ctx.user.avatar.url)

    player_mentions = []
    for player in game.players:
        player_mentions.append(f"<@{player.member.id}>")
    embed.add_field(
        name="Players",
        value=", ".join(player_mentions),
        inline=True
    )
    embed.add_field(
        name="\u200b",
        value="**Players, good luck!**"
    )
    embed.set_footer(text=game.date)

    return embed


def gen_rules_embed(page: int) -> Embed:
    max_pages: int = 6
    page: int = 1 + (page % max_pages)  # Loop back through pages both ways
    embed = Embed()
    embed.set_author(name="Anime Trains", icon_url=bd.bot_avatar_url)
    embed.colour = 0xff9c2c
    embed.set_footer(text=f'Page {page}/{max_pages}')
    if page == 1:
        embed.title = "Rules"
        embed.description = \
            "**1.** To win, you must obtain bingo by hitting the randomly generated tags on your bingo board.\n\n" \
            "**2.** Each shot corresponds to 3 hours of TV airing time. and can select one tag to shoot for. \n\n" \
            "**3.** Once a certain tag has been shot, that tag will not appear again on your board. " \
            "**4.** Certain shots require players to agree that the show/character matches the tag. In that case," \
            "a poll will be created. After 2 hours, if the majority agree, the shot will be marked as valid.\n\n" \
            "**5.** There are 75 possible tags, which are listed on the next page. Only 25 will appear on each board."
    elif page == 2:
        embed.title = "Possible Tags"
        embed.description = \
            "tbd"
    embed.set_footer(text=f'Page {page}/{max_pages}')
    return embed


class GameBoardView(View):
    """
    Discord UI View for handling bingo board interactions.

    Attributes:
        page (int): Which response page in server's response list to display
    """

    def __init__(self, game: BingoGame, sender_idx: int):
        super().__init__(timeout=60)
        self.add_item(PrevPgButton())
        self.add_item(NextPgButton())
        self.page = 1
        self.game = game
        self.sender_idx = sender_idx

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.data['custom_id'] == 'prev_page':
            self.page -= 1

        elif interaction.data['custom_id'] == 'next_page':
            self.page += 1

        embed, image = self.game.gen_board_embed(page=self.page, sender_idx=self.sender_idx)

        await interaction.response.edit_message(
            embed=embed, view=self
        )
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
        if interaction.data['custom_id'] == 'prev_page':
            self.page -= 1

        elif interaction.data['custom_id'] == 'next_page':
            self.page += 1

        embed = gen_rules_embed(page=self.page)

        await interaction.response.edit_message(
            embed=embed, view=self
        )
        return False
