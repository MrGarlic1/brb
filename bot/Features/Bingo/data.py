import asyncio
import io
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from random import sample
from shutil import rmtree
from typing import Union

import interactions
from PIL import Image, ImageFont, ImageDraw
from colorama import Fore

import Core.anilist as al
import Core.botdata as bd


bingo_tags = (
    "Episodic",
    "Fantasy",
    "Female Protagonist",
    "Food",
    "Gloppy**",
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
    "Mecha/Robots/Real Robot/Super Robot",
    "Music",
    "Mystery",
    "Not TV",
    "Parody/Satire",
    "Philosophy",
    "Primarily Female Cast",
    "Primarily Male Cast",
    "Psychological",
    "Revenge",
    "Rewatch an Anime",
    "Romance",
    "School/College",
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
    "Monster Girl"
)
season_tags = (
    "Spring",
    "Summer",
    "Fall",
    "Winter"
)


@dataclass
class BingoShot:
    def __init__(self, anilist_id: int, tag: str, time: str, hit: bool = False):
        self.anilist_id = anilist_id
        self.tag = tag
        self.time = time
        self.hit = hit

    def get_shot_type(self):
        if self.tag in character_tags:
            return "character"
        elif self.tag == "Source Not Manga":
            return "source"
        elif self.tag in season_tags:
            return "season"
        elif self.tag in bingo_tags:
            return "tag"
        else:
            return None



@dataclass
class BingoTile:
    def __init__(self, tag: str = "", hit: bool = None):
        self.tag = tag
        self.hit = hit

    def asdict(self) -> dict:
        return {
            "tag": self.tag, "hit": self.hit
        }


@dataclass
class BingoPlayer:
    def __init__(
            self, member: interactions.Member = None, dmchannel: interactions.DMChannel = None,
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
        for tile in self.board:
            board_dict[tile] = self.board[tile].asdict()
        return {
            "member_id": self.member.id, "done": self.done, "dmchannel": self.dmchannel.id,
            "shots": shot_list, "donetime": self.donetime, "anilist_id": self.anilist_id,
            "starting_anilist": self.starting_anilist, "board": board_dict
        }

    def gen_board(self):
        selected_tags = sample(bingo_tags, 25)

        board = {}
        for col in range(1, 6):
            for row in range(1, 6):
                board[col, row] = BingoTile(tag=selected_tags[0])
                del selected_tags[0]
        self.board = board

    def find_tag(self, tag):
        for tile in self.board:
            if self.board[tile].tag == tag:
                return tile
        return None

    def draw_board_img(
            self, filepath: str, board_name: str, player_board: bool = False, player_idx: int = 0,

    ):

        # Generate board image. If player board: only generate tiles which are rendered.
        # Grey out other tiles.

        # Adjustments
        label_offset: int = 1
        size = 5
        label_font_size: int = 24
        font = ImageFont.truetype(f"{bd.parent}/Data/ggsans/ggsans-Bold.ttf", label_font_size)
        tile_pixels: int = 150
        border_color: tuple[int, int, int] = (190, 190, 190)
        font_color: tuple[int, int, int] = (0, 0, 0)
        empty_color: tuple[int, int, int] = (255, 255, 255)
        miss_color: tuple[int, int, int] = (255, 0, 0)
        hit_color: tuple[int, int, int] = (0, 255, 0)

        board_img = Image.new(
            mode="RGB",
            size=((size + label_offset) * tile_pixels, (size + label_offset) * tile_pixels),
            color=0xFFFFFF
        )
        draw: ImageDraw = ImageDraw.Draw(board_img)

        # Draw column labels/tile borders

        for label_x in range(1, size + 1):
            draw.rectangle(
                xy=((label_x * tile_pixels, 1), ((label_x + 1) * tile_pixels, tile_pixels)),
                fill=empty_color, outline=border_color, width=1
            )
            draw.text(
                xy=(label_x * tile_pixels + tile_pixels / 2, tile_pixels / 2), text=str(label_x), font=font,
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
        font = ImageFont.truetype(f"{bd.parent}/Data/ggsans/ggsans-Bold.ttf", font_size)

        for coords in self.board.keys():
            (row, col) = coords

            # Fill tiles with correct color, if empty, skip to next
            if self.board[coords].hit is None:
                draw.rectangle(
                    xy=((col * tile_pixels, row * tile_pixels), ((col + 1) * tile_pixels, (row + 1) * tile_pixels)),
                    fill=empty_color, outline=border_color, width=1
                )
                continue
            elif self.board[coords].hit:
                draw.rectangle(
                    xy=((col * tile_pixels, row * tile_pixels), ((col + 1) * tile_pixels, (row + 1) * tile_pixels)),
                    fill=hit_color, outline=border_color, width=1
                )
            else:
                draw.rectangle(
                    xy=((col * tile_pixels, row * tile_pixels), ((col + 1) * tile_pixels, (row + 1) * tile_pixels)),
                    fill=miss_color, outline=border_color, width=1
                )

            text_pixels = draw.textlength(text=self.board[coords].tag, font=font)

            while text_pixels > 0.8 * tile_pixels and font_size > 6:
                font_size -= 2
                font = ImageFont.truetype(f"{bd.parent}/Data/ggsans/ggsans-Bold.ttf", font_size)
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
                font = ImageFont.truetype(f"{bd.parent}/Data/ggsans/ggsans-Bold.ttf", font_size)

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
            json.dump(self.asdict(), f, separators=(",", ":"))

    async def send_player_poll(self, ctx: interactions.SlashContext, p: BingoPlayer, p_idx: int) -> None:
        """
        try:
            board_name: str = str(p.member.id)
            self.draw_board_img(
                filepath=f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{self.name}",
                board_name=str(p.member.id),
                player_idx=p_idx, player_board=True
            )
            board_img_path: str = f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{self.name}/{board_name}.png"
            await p.dmchannel.send(
                file=interactions.File(board_img_path),
                content=f"## Train board update for \"{self.name}\" in {ctx.guild.name}!"
            )

        except AttributeError:
            print(Fore.YELLOW + f"Could not find user with ID {p.member.id}" + Fore.RESET)
            del self.players[p_idx]
        """

    async def update_boards_after_shot(
            self, ctx: interactions.SlashContext,
            row: int, column: int
    ) -> None:

        # Push updates to player boards, check if game is finished

        active: bool = not self.is_done()
        self.active = active
        if self.active:
            bd.active_bingos[ctx.guild_id] = self
        else:
            del bd.active_bingos[ctx.guild_id]

        self.save_game(f"{bd.parent}/Guilds/{ctx.guild_id}/Bingo/{self.name}")
        return None

    async def update_boards_after_create(
            self, ctx: interactions.SlashContext
    ) -> None:
        """
        tasks: list = []

        for player_idx, player in enumerate(self.players):
            tasks.append(asyncio.create_task(self.update_player_board(ctx, player, player_idx)))
        await asyncio.gather(*tasks)
        """
        # Update master board/game state
        self.save_game(f"{bd.parent}/Guilds/{ctx.guild_id}/Bingo/{self.name}")
        bd.active_bingos[ctx.guild_id] = self
        return None

    async def update_player_board(self, ctx: interactions.SlashContext, p: BingoPlayer, p_idx: int) -> None:
        try:
            p.draw_board_img(
                filepath=f"{bd.parent}/Guilds/{ctx.guild_id}/Bingo/{self.name}",
                board_name=str(p.member.id),
                player_idx=p_idx, player_board=True
            )

        except AttributeError:
            print(Fore.YELLOW + f"Could not find user with ID {p.member.id}" + Fore.RESET)
            del self.players[p_idx]

    def gen_stats_embed(self, ctx: Union[interactions.SlashContext, interactions.ComponentContext],
                        expired: bool, page: int = 0) -> tuple[interactions.Embed, Union[None, interactions.File]]:
        embed: interactions.Embed = interactions.Embed()
        embed.set_author(name=f"Anime Trains", icon_url=bd.bot_avatar_url)
        footer_end: str = ' | This message is inactive.' if expired else ' | This message deactivates after 5 minutes.'
        """
        max_pages: int = len(self.players) + 1
        page: int = 1 + (page % max_pages)  # Loop back through pages both ways
        embed.set_footer(text=f'Page {page}/{max_pages} {footer_end}')

        # Game stats page
        if page == 1:
            resource_count: dict = {}
            claimed_resource_count: dict = {}
            rail_count: int = 0
            intersection_count: int = 0
            for coord, tile in self.board.items():
                if tile.resource:
                    try:
                        resource_count[tile.resource] += 1
                    except KeyError:
                        resource_count[tile.resource] = 1
                if tile.rails:
                    rail_count += 1
                    if tile.resource:
                        try:
                            claimed_resource_count[tile.resource] += 1
                        except KeyError:
                            claimed_resource_count[tile.resource] = 1
                    if len(tile.rails) > 1:
                        intersection_count += 1

            embed.title = "Game Stats"
            embed.description = f"*{self.name}*\n\u200b"
            embed.set_thumbnail(url=ctx.guild.icon.url)
            embed.add_field(name="🚂 Active?", value="✅" if self.active else "❌", inline=True)
            embed.add_field(name="🚂 Complete?", value="✅" if self.is_done() else "❌", inline=True)
            embed.add_field(name="\u200b", value="\u200b", inline=False)

            for resource, count in resource_count.items():
                if resource not in claimed_resource_count.keys():
                    claimed_resource_count[resource]: int = 0

                embed.add_field(
                    name=f"# of {resource} Claimed/Total",
                    value=f"{claimed_resource_count[resource]}/{count}", inline=True
                )

            embed.add_field(name="🛤️ Total Rails", value=rail_count, inline=True)
            embed.add_field(name="🔀 # of Crossings", value=intersection_count, inline=True)

            if self.is_done():
                self.draw_board_img(
                    filepath=f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{self.name}",
                    board_name="MASTER", player_board=False
                )
                board_img_path = f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{self.name}/MASTER.png"
                image = interactions.File(board_img_path, file_name="MASTER.png")
                embed.set_image(
                    url="attachment://MASTER.png"
                )
            else:
                with open(f"{bd.parent}/Data/nothing.png", "rb") as f:
                    file = io.BytesIO(f.read())
                image: interactions.File = interactions.File(file, file_name="nothing.png")
                embed.set_image(
                    url="attachment://nothing.png"
                )
            return embed, image

        # Player stats page
        player_idx: int = page - 2
        player: TrainPlayer = self.players[player_idx]

        if len(player.shots) == 0:
            embed.description = f"### {player.member.mention} has not placed any rails yet!"
            with open(f"{bd.parent}/Data/nothing.png", "rb") as f:
                file = io.BytesIO(f.read())
            image: interactions.File = interactions.File(file, file_name="nothing.png")
            embed.set_image(
                url="attachment://nothing.png"
            )
            return embed, image

        embed.set_thumbnail(url=player.member.avatar_url)
        embed.description = f"### Stats for {player.member.mention}"
        embed.add_field(name="\u200b", value="\u200b", inline=False)

        # Total shots/in-zone shots
        total_shots: int = len(player.shots)
        in_zone_shots: int = 0
        prev_shot_time = datetime.strptime(self.date, bd.date_format)
        time_between_shots_list = []
        weights = []

        # Get time deltas for all previous shots and current time, take weighted average
        for shot_idx, shot in enumerate(player.shots):
            if self.board[shot.coords()].zone in self.known_entries[shot.show_id]["genres"]:
                in_zone_shots += 1
            time_between_shots_list.append(
                (datetime.strptime(shot.time, bd.date_format) - prev_shot_time).total_seconds()
            )
            # Weight based on seconds elapsed since shot. Time delta minimum is 300
            weights.append(
                log(0.01 * max((datetime.now() - prev_shot_time).total_seconds(), 300)) ** -.9
            )
            prev_shot_time = datetime.strptime(shot.time, bd.date_format)

        time_between_shots_list.append((datetime.now() - prev_shot_time).total_seconds())
        weights.append(
            log((datetime.now() - prev_shot_time).total_seconds()) ** -1
        )
        avg_secs_between_shots = round(sum(time_between_shots_list) / len(time_between_shots_list))

        embed.add_field(name="🧮 Total Shots", value=total_shots, inline=True)
        embed.add_field(name="🛤️ Total Rails Used", value=player.rails, inline=True)
        embed.add_field(name="🍥 % in Zone", value=f"{round(in_zone_shots / total_shots * 100)}%", inline=True)
        embed.add_field(name="🚂 Done?", value="✅" if player.done else "❌", inline=True)
        embed.add_field(
            name="⏳ Avg. Time Between Shots", value=str(timedelta(seconds=avg_secs_between_shots)), inline=False
        )

        # Projected completion time
        if not player.shots:
            projected_time = "N/A"
        elif player.done:
            projected_time = datetime.strptime(player.donetime, "%Y%m%d%H%M%S")
            projected_time = projected_time.strftime("%Y/%m/%d at %H:%M:%S")
        else:
            # player.end is [ROW, COL]
            last_shot = player.shots[-1]
            dist_left = abs(last_shot.row - player.end[0]) + abs(last_shot.col - player.end[1])
            weighted_time_deltas = [t * w for t, w in zip(time_between_shots_list, weights)]
            weighted_avg_secs_between_shots = sum(weighted_time_deltas) / sum(weights)
            projected_time = datetime.now() + timedelta(
                seconds=round(dist_left * 1.5) * weighted_avg_secs_between_shots)
            projected_time = projected_time.strftime("%Y/%m/%d at %H:%M:%S")

        embed.add_field(
            name="🗓️ Projected Completion Date", value=projected_time, inline=False
        )

        # Shot genre pie chart

        genre_counts: dict[str, int] = {}
        for shot in self.players[player_idx].shots:
            for genre in self.known_entries[shot.show_id]["genres"]:
                if genre in genre_counts:
                    genre_counts[genre] += 1
                else:
                    genre_counts[genre] = 1

        plt.style.use("dark_background")
        fig, ax = plt.subplots()

        plt.rcParams["font.size"] = 14
        plt.rcParams["font.family"] = "gg sans"
        plt.rcParams["font.weight"] = "bold"
        wedges, text, autotexts = ax.pie(list(genre_counts.values()), autopct="%1.1f%%")
        plt.setp(autotexts, size=16, weight="medium", color="black")
        plt.title(
            label="Shot Genre Percentages              ",
            weight="bold", size=17, family="gg sans", horizontalalignment="right"
        )
        plt.legend(
            genre_counts.keys(), title="Genres", loc="lower left", framealpha=0, bbox_to_anchor=(-0.45, 0.2, 0.75, 1),
            prop=matplotlib.font_manager.FontProperties(family="gg sans", weight="medium", size=15, style="italic"),
            title_fontproperties=matplotlib.font_manager.FontProperties(family="gg sans", weight="medium", size=17)
        )
        filepath = f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{self.name}/stats_img.png"
        plt.savefig(filepath, transparent=True)
        plt.close(fig)

        with open(filepath, "rb") as f:
            file = io.BytesIO(f.read())
        image = interactions.File(file, file_name="stats_img.png")

        embed.set_image(
            url="attachment://stats_img.png"
        )
        return embed, image
        """

    def update_player_stats_after_shot(
            self, sender_idx: int, player: BingoPlayer, undo: bool = False, shot: BingoShot = None
    ):
        """
        check_gem_time = False
        if self.board[shot.coords()].resource == bd.emoji["gems"]:
            shot_list = player.shots[:-1] if undo else player.shots
            if not bd.emoji["gems"] in [self.board[shot.coords()].resource for shot in shot_list]:
                check_gem_time = True

        if undo:
            shot = player.shots[-1]
            self.board[shot.coords()].rails.remove(player.tag)
            del self.players[sender_idx].shots[-1]
            if self.players[sender_idx].done:
                self.players[sender_idx].done = False
                self.players[sender_idx].donetime = None
            if check_gem_time:
                self.players[sender_idx].score.pop("GemTime")
        else:
            self.board[shot.coords()].rails.append(player.tag)
            self.players[sender_idx].shots.append(shot)
            if shot.coords() == player.end:
                self.players[sender_idx].done = True
                self.players[sender_idx].donetime = datetime.now().strftime("%Y%m%d%H%M%S")
            if check_gem_time:
                self.players[sender_idx].score["GemTime"] = int(
                    datetime.strptime(shot.time, bd.date_format).timestamp()
                )

        self.update_vis_tiles(player_idx=sender_idx, shot_row=shot.row, shot_col=shot.col, remove=undo)
        if undo:
            shot = player.shots[-1]
            self.update_vis_tiles(player_idx=sender_idx, shot_row=shot.row, shot_col=shot.col)
            self.update_vis_tiles(player_idx=sender_idx, shot_row=player.start[0], shot_col=player.start[1])
            self.update_vis_tiles(player_idx=sender_idx, shot_row=player.end[0], shot_col=player.end[1], render_dist=0)

        if self.board[shot.coords()].terrain == "river":
            if "Pontoon Bridge" in player.inventory:
                rails = 0
                player.update_item_count("Pontoon Bridge")
            else:
                rails = 2
        else:
            rails = 1

        if self.board[shot.coords()].zone in self.known_entries[shot.show_id]["genres"]:
            rails *= 0.5
        if undo:
            self.players[sender_idx].rails -= rails
        else:
            self.players[sender_idx].rails += rails
        """
        pass


async def load_game(
        filepath: str, guild: interactions.Guild, active_only: bool = False
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
                    anilist_id=shot["anilist_id"], tag=shot["tag"], time=shot["time"]
                )
            )

        member = await guild.fetch_member(player["member_id"])
        dm = await member.fetch_dm(force=False)

        board = {}
        for pos, tile in player["board"].items():
            col = int(pos[0])
            row = int(pos[1])
            board[col, row] = BingoTile(tag=tile["tag"], hit=tile["hit"])

        player_list.append(
            BingoPlayer(
                member=member, done=player["done"],
                dmchannel=dm, shots=shot_list, donetime=player["donetime"], starting_anilist=player["starting_anilist"],
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


def del_game_files(guild_id: int, game_name: str):
    try:
        rmtree(f"{bd.parent}/Guilds/{guild_id}/Bingo/{game_name}")
    except PermissionError:
        pass


def bingo_game_embed(ctx: interactions.SlashContext, game: BingoGame) -> interactions.Embed:
    embed = interactions.Embed()
    embed.set_author(name="Anime Bingo", icon_url=bd.bot_avatar_url)
    embed.color = 0xff9c2c
    embed.title = "It's Bingo Time"
    embed.description = f"*{ctx.author.mention} has created \"{game.name}\"!*"
    embed.set_thumbnail(url=ctx.author.avatar_url)

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


def gen_rules_embed(page: int, expired: bool) -> interactions.Embed:
    """
    max_pages: int = 6
    page: int = 1 + (page % max_pages)  # Loop back through pages both ways
    footer_end: str = " | This message is inactive." if expired else " | This message deactivates after 5 minutes."
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
    embed.set_footer(text=f'Page {page}/{max_pages} {footer_end}')
    return embed
    """
    pass
