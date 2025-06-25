import asyncio
import io
import json
from datetime import datetime, timedelta
from math import log
from os import path
from random import randint, shuffle, choice
from typing import Union
from io import BytesIO

import logging
import matplotlib.font_manager
import matplotlib.pyplot as plt
from PIL import Image, ImageFont, ImageDraw
from pilmoji import Pilmoji

from discord import Interaction, Guild, Embed, File

import brbot.Core.anilist as al
import brbot.Core.botdata as bd
from brbot.Features.Trains.data import (
    TrainTile,
    TrainItem,
    TrainPlayer,
    TrainShot,
    game_emoji,
    genre_colors,
    default_shop,
    find_anilist_changes,
)

logger = logging.getLogger(__name__)


class TrainGame:
    def __init__(
        self,
        name: str = None,
        date: str = None,
        players: list[TrainPlayer] = None,
        board: dict[tuple[int, int], TrainTile] = None,
        gameid: int = None,
        active: bool = True,
        size: tuple = None,
        shop: dict[str, TrainItem] = None,
        known_shows: dict[int, dict] = None,
    ):
        if players is None:
            players: list[TrainPlayer] = []
        if shop is None:
            shop = default_shop()
        if known_shows is None:
            known_shows = {}
        self.name = name
        self.date = date
        self.players = players
        self.gameid = gameid
        self.active = active
        self.size = size
        self.board = board
        self.shop = shop
        self.known_shows = known_shows

    def asdict(self) -> dict:
        player_list = []
        for player in self.players:
            player_list.append(player.asdict())
        board_dict = {}
        for coord, tile in self.board.items():
            board_dict[str(coord)] = tile.__dict__
        item_dict = {}
        for name, item in self.shop.items():
            item_dict[name] = item.__dict__
        return {
            "name": self.name,
            "date": self.date,
            "players": player_list,
            "gameid": self.gameid,
            "active": self.active,
            "size": self.size,
            "board": board_dict,
            "shop": item_dict,
            "known_shows": self.known_shows,
        }

    def __repr__(self) -> str:
        return (
            f"<name={self.name}> <date={self.date}> <players={self.players}> <gameid={self.gameid}> "
            f"<active={self.active}> <size={self.size}> <board={self.board}> "
        )

    class BoardGenError(Exception):
        pass

    def is_done(self) -> bool:
        done = True
        for player in self.players:
            if not player.done:
                done = False
                break
        return done

    def in_bounds(self, row: int, col: int) -> bool:
        if row < 1 or col < 1 or row > self.size[1] or col > self.size[0]:
            return False
        else:
            return True

    def get_player(
        self, player_id: int
    ) -> Union[tuple[None, None], tuple[int, TrainPlayer]]:
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

    def gen_trains_board(
        self, play_area_size: tuple[int, int] = (16, 16), river_ring: int = 0
    ) -> None:
        width = self.size[0]
        height = self.size[1]
        play_width, play_height = play_area_size
        logger.info(f"Generating {width}x{height} board for {self.name}")

        def next_to_resource(tilepos, resource) -> bool:
            # Returns true if the grid tile is directly adjacent to the specified resource
            x = tilepos[0]
            y = tilepos[1]

            for x_new in (x - 1, x + 1):
                try:
                    if self.board[(x_new, y)].resource == resource:
                        return True
                except KeyError:
                    pass

            for y_new in (y - 1, y + 1):
                try:
                    if self.board[(x, y_new)].resource == resource:
                        return True
                except KeyError:
                    pass

            return False

        def near_resource(tilepos, resource, spread) -> bool:
            # Returns true if the grid tile is within {spread} tiles of the specified resource
            # Tilepos is (x, y)
            x = tilepos[0]
            y = tilepos[1]

            for x_new in range(x - spread, x + spread):
                for y_new in range(y - spread, y + spread):
                    try:
                        if self.board[(x_new, y_new)].resource == resource:
                            return True
                    except KeyError:
                        pass

            return False

        def generate_random_resources(tilepos) -> None | str:
            # Tilepos is (x, y)
            # Determines based on the chances below (out of 1000) if a tile will be populated with a resource.
            # Only adds to empty tiles (after count based resources have been placed)

            wheat_chance: int = 100
            wheat_near_chance: int = 50

            wood_chance: int = 130
            wood_near_chance: int = 30

            house_chance: int = 70
            house_near_chance: int = 35

            if self.board[tilepos].resource is not None:
                return self.board[tilepos].resource

            if self.board[tilepos].terrain is not None:
                return None

            # Wheat
            if near_resource(tilepos, game_emoji["wheat"], 3):
                if randint(1, 1000) <= wheat_near_chance:
                    return game_emoji["wheat"]
            else:
                if randint(1, 1000) <= wheat_chance:
                    return game_emoji["wheat"]

            # Wood
            if near_resource(tilepos, game_emoji["wood"], 2):
                if randint(1, 1000) <= wood_near_chance:
                    return game_emoji["wood"]
            else:
                if randint(1, 1000) <= wood_chance:
                    return game_emoji["wood"]

            # Houses
            if next_to_resource(tilepos, game_emoji["house"]):
                if randint(1, 1000) <= house_near_chance:
                    return game_emoji["house"]
            else:
                if randint(1, 1000) <= house_chance:
                    return game_emoji["house"]

            return None

        def generate_count_resource(
            count, resource, min_spread=0
        ) -> dict[tuple[int, int] : TrainTile]:
            # Grid Size is (x, y), or (row, col)
            added = 0
            attempts = 0
            while added < count:
                attempts += 1

                y = randint(1, width)
                x = randint(1, height)
                # Add resource if tile is empty and meets the minimum spread requirement
                if (
                    self.board[(x, y)].resource is None
                    and self.board[(x, y)].terrain is None
                    and not near_resource((x, y), resource, min_spread)
                ):
                    self.board[(x, y)].resource = resource
                    added += 1
                    attempts = 0
                # Reduces minimum spread requirement at 15 attempts and tries again
                if attempts > 15:
                    min_spread -= 1
                    attempts = 0
                # Infinite loop catch if unable to add resource
                if min_spread <= 0:
                    logger.warning(f"Failed to add {resource}, skipped")
                    break
            return self.board

        def generate_zones() -> dict[tuple[int, int] : TrainTile]:
            # Adds genre zones in randomized order to grid. Both dimensions of the grid must be divisible by 4 to allow
            # for 16 zones.

            def add_zone(z_width, z_height, start_pos, genre) -> None:
                for row in range(start_pos[0], start_pos[0] + z_height):
                    for col in range(start_pos[1], start_pos[1] + z_width):
                        self.board[(row, col)].zone = genre

            if play_width % 4 != 0 or play_height % 4 != 0:
                logger.error(
                    f"Invalid board dimensions ({play_width} x {play_height}) tiles, generation aborted"
                )
                raise self.BoardGenError("Width and height must be divisible by 4.")

            zone_width: int = play_width // 4
            zone_height: int = play_height // 4
            zone_order: list = list(genre_colors.keys())
            shuffle(zone_order)

            for i in range(16):
                zone_pos = (
                    zone_height * (i // 4) + river_ring + 1,
                    zone_width * (i % 4) + river_ring + 1,
                )
                add_zone(zone_width, zone_height, zone_pos, zone_order[i])
            return self.board

        def generate_river(direction: str = "") -> dict[tuple[int, int] : TrainTile]:
            # Chance of river ending: [0, 1]
            base_chance: float = 0.9

            # River shape parameters. Average river width and river cohesion (higher density = less spread out river)
            avg_width: float = 1.5
            density: float = 2.2

            river_tiles: list[tuple[int, int]] = []

            if direction == "Right":
                river_start = (
                    randint(round(width * 0.25), round(width * 0.75)),
                    randint(1, round(width * 0.25)),
                )
                river_tiles.append(river_start)
                river_center = [river_start[0]]

                for col in range(river_start[1] + 1, width + 1):
                    if randint(1, 1000) <= base_chance * 1000:
                        river_center.append(river_center[-1] + randint(-1, 1))
                    else:
                        break
                    for row in range(1, height + 1):
                        diff = abs(row - river_center[-1])
                        chance = 1000 * (base_chance - 0.25 / avg_width * diff**density)
                        if randint(1, 1000) <= chance:
                            river_tiles.append((row, col))

            elif direction == "DownRight":
                river_start = (
                    randint(1, round(width * 0.25)),
                    randint(1, round(width * 0.25)),
                )
                river_tiles.append(river_start)
                river_center = [river_start[0]]

                for col in range(river_start[1] + 1, width + 1):
                    if randint(1, 1000) <= base_chance * 1000:
                        river_center.append(river_center[-1] + randint(0, 2))
                    else:
                        break
                    for row in range(1, height + 1):
                        diff = abs(row - river_center[-1])
                        chance = 1000 * (base_chance - 0.25 / avg_width * diff**density)
                        if randint(1, 1000) <= chance:
                            river_tiles.append((row, col))

            elif direction == "Down":
                river_start = (
                    randint(1, round(width * 0.25)),
                    randint(round(width * 0.25), round(width * 0.75)),
                )
                river_tiles.append(river_start)
                river_center = [river_start[1]]

                for row in range(river_start[0] + 1, height + 1):
                    if randint(1, 1000) <= base_chance * 1000:
                        river_center.append(river_center[-1] + randint(-1, 1))
                    else:
                        break
                    for col in range(1, width + 1):
                        diff = abs(col - river_center[-1])
                        chance = 1000 * (base_chance - 0.25 / avg_width * diff**density)
                        if randint(1, 1000) <= chance:
                            river_tiles.append((row, col))

            elif direction == "DownLeft":
                river_start = (
                    randint(round(height * 0.75), height),
                    randint(1, round(width * 0.25)),
                )
                river_tiles.append(river_start)
                river_center = [river_start[0]]

                for col in range(river_start[1] + 1, width + 1):
                    if randint(1, 1000) <= base_chance * 1000:
                        river_center.append(river_center[-1] + randint(-2, 0))
                    else:
                        break
                    for row in range(1, height + 1):
                        diff = abs(row - river_center[-1])
                        chance = 1000 * (base_chance - 0.25 / avg_width * diff**density)
                        if randint(1, 1000) <= chance:
                            river_tiles.append((row, col))
            else:
                pass

            for pos in river_tiles:
                self.board[pos].terrain = "river"
            return self.board

        # For zones to generate, both board dimensions must be divisible by 4

        # Generate empty board
        self.board = {}
        for r in range(height):
            for c in range(width):
                if r + 1 <= river_ring or r + 1 > height - river_ring:
                    terrain = "river"
                elif c + 1 <= river_ring or c + 1 > width - river_ring:
                    terrain = "river"
                else:
                    terrain = None
                self.board[(r + 1, c + 1)] = TrainTile(terrain=terrain)

        # Add terrain (chance out of 1000)
        river_chance = 900
        if randint(1, 1000) <= river_chance:
            river_dir = ("Down", "DownLeft", "DownRight", "Right")
            river_dir = choice(river_dir)
            logger.debug(f"Generating river tiles in {river_dir} for {self.name}")
            self.board = generate_river(river_dir)

        # Add count-based resources
        city_count: int = 4
        prison_count: int = 2
        gem_count: int = 2
        shop_count: int = 4

        self.board = generate_count_resource(
            count=city_count, resource=game_emoji["city"], min_spread=4
        )
        self.board = generate_count_resource(
            count=prison_count, resource=game_emoji["prison"], min_spread=6
        )
        self.board = generate_count_resource(
            count=gem_count, resource=game_emoji["gems"], min_spread=8
        )
        self.board = generate_count_resource(
            count=shop_count, resource=game_emoji["shop"], min_spread=8
        )

        # Add random resources
        for c in range(width):
            for r in range(height):
                self.board[(r + 1, c + 1)].resource = generate_random_resources(
                    (r + 1, c + 1)
                )

        # Add genre zones
        self.board = generate_zones()
        return None

    def update_vis_tiles(
        self,
        player_idx: int,
        shot_row: int,
        shot_col: int,
        remove: bool = False,
        render_dist: int = 4,
    ):
        if "Telescope" in self.players[player_idx].inventory:
            render_dist += self.players[player_idx].inventory["Telescope"].amount

        for row in range(shot_row - render_dist, shot_row + render_dist + 1):
            for col in range(shot_col - render_dist, shot_col + render_dist + 1):
                if (row, col) in self.players[
                    player_idx
                ].vis_tiles:  # Already rendered tiles
                    if remove:
                        if not any(
                            (
                                abs(player_shot.row - row) <= render_dist
                                and abs(player_shot.col - col) <= render_dist
                                for player_shot in self.players[player_idx].shots
                            )
                        ):
                            self.players[player_idx].vis_tiles.remove((row, col))
                    else:
                        continue
                elif self.in_bounds(row, col):
                    self.players[player_idx].vis_tiles.append((row, col))

    def gen_player_locations(self, river_ring: int) -> None:
        row_bounds: tuple[int, int] = (1 + river_ring, self.size[1] - river_ring)
        col_bounds: tuple[int, int] = (1 + river_ring, self.size[0] - river_ring)
        taken_spaces: list = []

        for player_idx, player in enumerate(self.players):
            quadrant: str = choice(("Left", "Top"))

            # Generate start locations (NOTE: game.size is (width, height) while coordinates are in (row, col)
            attempts: int = 0
            start_loc = None
            while attempts <= 40:
                if quadrant == "Left":
                    start_loc = (randint(row_bounds[0], row_bounds[1]), col_bounds[0])
                else:
                    start_loc = (row_bounds[0], randint(col_bounds[0], col_bounds[1]))

                if (
                    self.board[start_loc].terrain is None
                    and self.board[start_loc].resource is None
                    and start_loc not in taken_spaces
                ):
                    player.start = start_loc
                    taken_spaces.append(start_loc)
                    break
                attempts += 1
            if start_loc is None or attempts > 40:  # Error catch
                logger.error(
                    f"Unable to generate {player.member.name} starting location in game "
                    f"{self.name} after {attempts}, aborting."
                )
                raise self.BoardGenError(
                    "Failed generating board. Try increasing the board size?"
                )
            self.update_vis_tiles(player_idx, start_loc[0], start_loc[1])

            # Generate end locations
            attempts = 0
            end_loc = None
            while attempts <= 40:
                if quadrant == "Left":
                    end_loc = (randint(row_bounds[0], row_bounds[1]), col_bounds[1])
                else:
                    end_loc = (row_bounds[1], randint(col_bounds[0], col_bounds[1]))

                if (
                    self.board[end_loc].terrain is None
                    and self.board[end_loc].resource is None
                    and end_loc not in taken_spaces
                ):
                    player.end = end_loc
                    taken_spaces.append(end_loc)
                    break
                attempts += 1
            if end_loc is None or attempts > 40:  # Error catch
                logger.error(
                    f"Unable to generate {player.member.name} ending location in game "
                    f"{self.name} after {attempts}, aborting."
                )
                raise self.BoardGenError(
                    "Failed generating board. Try increasing the board size?"
                )
            self.update_vis_tiles(player_idx, end_loc[0], end_loc[1], render_dist=0)

    def is_valid_shot(self, player: TrainPlayer, shot_row: int, shot_col: int) -> bool:
        if player is None:  # Player not in game
            return False

        if player.done:
            return False

        if player.shots:
            base_coords = tuple(player.shots[-1].coords())
        else:
            if (shot_row, shot_col) == player.start:
                return True
            else:
                return False

        if not self.in_bounds(shot_row, shot_col):  # Out of bounds shots
            return False

        if (
            len(self.board[(shot_row, shot_col)].rails) >= 2
        ):  # Tiles with too many players on them
            return False

        # Shots not adjacent to player's rail endpoint
        if abs(shot_row - base_coords[0]) + abs(shot_col - base_coords[1]) != 1:
            return False

        base_intersecting_tag = None
        for tag in self.board[
            base_coords
        ].rails:  # Shots that move along someone else's rails for more than 1 tile
            if tag != player.tag:
                base_intersecting_tag = tag
        if base_intersecting_tag in self.board[(shot_row, shot_col)].rails:
            return False

        # Tiles that run next to your current rails

        test_coords = (
            (shot_row, shot_col + 1),
            (shot_row, shot_col - 1),
            (shot_row + 1, shot_col),
            (shot_row - 1, shot_col),
        )

        for coord in test_coords:
            if not self.in_bounds(coord[0], coord[1]) or coord == base_coords:
                continue
            elif player.tag in self.board[coord].rails:
                return False

        return True

    async def push_player_update(self, ctx: Interaction, p: TrainPlayer, p_idx: int):
        try:
            board_name: str = str(p.member.id)
            self.draw_board_img(
                filepath=f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{self.name}",
                board_name=str(p.member.id),
                player_idx=p_idx,
                player_board=True,
            )
            board_img_path: str = (
                f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{self.name}/{board_name}.png"
            )
            try:
                with open(board_img_path, "rb") as f:
                    file = BytesIO(f.read())
            except FileNotFoundError:
                logger.error(
                    f'Unable to find board image "{board_name}" in "{board_img_path} '
                    f"for game {self.name} in {ctx.guild.name}"
                )
                await ctx.response.send_message(bd.fail_str, ephemeral=True)
                return True

            await p.dmchannel.send(
                file=File(file, filename=board_img_path),
                content=f'## Train board update for "{self.name}" in {ctx.guild.name}!',
            )

        except AttributeError:
            logger.warning(f"Could not find user with ID {p.member.id}, removing.")
            del self.players[p_idx]

    async def update_boards_after_shot(
        self, ctx: Interaction, row: int, column: int
    ) -> None:
        # Push updates to player boards, check if game is finished
        tasks: list = []
        for player_idx, player in enumerate(self.players):
            if (row, column) in player.vis_tiles:
                logger.debug(
                    f"Sending board update with shot ({row}, {column}) to "
                    f"{player.member.name} for game {self.name} in {ctx.guild.name}"
                )
                tasks.append(
                    asyncio.create_task(
                        self.push_player_update(ctx, player, player_idx)
                    )
                )
        await asyncio.gather(*tasks)
        active: bool = not self.is_done()
        self.active = active
        if self.active:
            bd.active_trains[ctx.guild_id] = self
        else:
            del bd.active_trains[ctx.guild_id]

        self.save_game(f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{self.name}")
        return None

    async def update_boards_after_create(self, ctx: Interaction) -> None:
        tasks: list = []

        for player_idx, player in enumerate(self.players):
            logger.debug(
                f"Sending initial board to "
                f"{player.member.name} for game {self.name} in {ctx.guild.name}"
            )
            tasks.append(
                asyncio.create_task(self.push_player_update(ctx, player, player_idx))
            )
        await asyncio.gather(*tasks)

        # Update master board/game state
        self.save_game(f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{self.name}")
        bd.active_trains[ctx.guild_id] = self
        return None

    def gen_stats_embed(
        self, ctx: Interaction, page: int = 0
    ) -> tuple[Embed, Union[None, File]]:
        embed: Embed = Embed()
        embed.set_author(name="Anime Trains", icon_url=bd.bot_avatar_url)

        max_pages: int = len(self.players) + 1
        page: int = 1 + (page % max_pages)  # Loop back through pages both ways
        embed.set_footer(text=f"Page {page}/{max_pages}")

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
            embed.add_field(
                name="🚂 Active?", value="✅" if self.active else "❌", inline=True
            )
            embed.add_field(
                name="🚂 Complete?", value="✅" if self.is_done() else "❌", inline=True
            )
            embed.add_field(name="\u200b", value="\u200b", inline=False)

            for resource, count in resource_count.items():
                if resource not in claimed_resource_count.keys():
                    claimed_resource_count[resource]: int = 0

                embed.add_field(
                    name=f"# of {resource} Claimed/Total",
                    value=f"{claimed_resource_count[resource]}/{count}",
                    inline=True,
                )

            embed.add_field(name="🛤️ Total Rails", value=rail_count, inline=True)
            embed.add_field(
                name="🔀 # of Crossings", value=intersection_count, inline=True
            )

            if self.is_done():
                self.draw_board_img(
                    filepath=f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{self.name}",
                    board_name="MASTER",
                    player_board=False,
                )
                board_img_path = (
                    f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{self.name}/MASTER.png"
                )
                try:
                    with open(board_img_path, "rb") as f:
                        file = BytesIO(f.read())
                except FileNotFoundError:
                    logger.warning(
                        f"Could not find image at {board_img_path} for "
                        f"game {self.name} in {ctx.guild.name}, skipping image send"
                    )
                    return embed, None

                image = File(file, filename="MASTER.png")
                embed.set_image(url="attachment://MASTER.png")
                return embed, image
            else:
                return embed, None

        # Player stats page
        player_idx: int = page - 2
        player: TrainPlayer = self.players[player_idx]

        if len(player.shots) == 0:
            embed.description = (
                f"### {player.member.mention} has not placed any rails yet!"
            )
            return embed, None

        embed.set_thumbnail(url=player.member.avatar.url)
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
            if (
                self.board[shot.coords()].zone
                in self.known_shows[shot.show_id]["genres"]
            ):
                in_zone_shots += 1
            time_between_shots_list.append(
                (
                    datetime.strptime(shot.time, bd.date_format) - prev_shot_time
                ).total_seconds()
            )
            # Weight based on seconds elapsed since shot. Time delta minimum is 300
            weights.append(
                log(0.01 * max((datetime.now() - prev_shot_time).total_seconds(), 300))
                ** -0.9
            )
            prev_shot_time = datetime.strptime(shot.time, bd.date_format)

        time_between_shots_list.append(
            (datetime.now() - prev_shot_time).total_seconds()
        )
        weights.append(log((datetime.now() - prev_shot_time).total_seconds()) ** -1)
        avg_secs_between_shots = round(
            sum(time_between_shots_list) / len(time_between_shots_list)
        )

        embed.add_field(name="🧮 Total Shots", value=total_shots, inline=True)
        embed.add_field(name="🛤️ Total Rails Used", value=player.rails, inline=True)
        embed.add_field(
            name="🍥 % in Zone",
            value=f"{round(in_zone_shots / total_shots * 100)}%",
            inline=True,
        )
        embed.add_field(
            name="🚂 Done?", value="✅" if player.done else "❌", inline=True
        )
        embed.add_field(
            name="⏳ Avg. Time Between Shots",
            value=str(timedelta(seconds=avg_secs_between_shots)),
            inline=False,
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
            dist_left = abs(last_shot.row - player.end[0]) + abs(
                last_shot.col - player.end[1]
            )
            weighted_time_deltas = [
                t * w for t, w in zip(time_between_shots_list, weights)
            ]
            weighted_avg_secs_between_shots = sum(weighted_time_deltas) / sum(weights)
            projected_time = datetime.now() + timedelta(
                seconds=round(dist_left * 1.5) * weighted_avg_secs_between_shots
            )
            projected_time = projected_time.strftime("%Y/%m/%d at %H:%M:%S")

        embed.add_field(
            name="🗓️ Projected Completion Date", value=projected_time, inline=False
        )

        # Shot genre pie chart

        genre_counts: dict[str, int] = {}
        for shot in self.players[player_idx].shots:
            for genre in self.known_shows[shot.show_id]["genres"]:
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
            weight="bold",
            size=17,
            family="gg sans",
            horizontalalignment="right",
        )
        plt.legend(
            genre_counts.keys(),
            title="Genres",
            loc="lower left",
            framealpha=0,
            bbox_to_anchor=(-0.45, 0.2, 0.75, 1),
            prop=matplotlib.font_manager.FontProperties(
                family="gg sans", weight="medium", size=15, style="italic"
            ),
            title_fontproperties=matplotlib.font_manager.FontProperties(
                family="gg sans", weight="medium", size=17
            ),
        )
        filepath = f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{self.name}/stats_img.png"
        plt.savefig(filepath, transparent=True)
        plt.close(fig)

        with open(filepath, "rb") as f:
            file = io.BytesIO(f.read())
        image = File(file, filename="stats_img.png")

        embed.set_image(url="attachment://stats_img.png")
        return embed, image

    def draw_board_img(
        self,
        filepath: str,
        board_name: str,
        player_board: bool = False,
        player_idx: int = 0,
    ):
        # Generate board image. If player board: only generate tiles which are rendered.
        # Grey out other tiles.

        # Adjustments
        label_offset: int = 1
        label_font_size: int = 24
        tile_pixels: int = 50
        hidden_tile_color: tuple[int, int, int] = (255, 255, 255)
        border_color: tuple[int, int, int] = (190, 190, 190)
        font_color: tuple[int, int, int] = (0, 0, 0)
        font_path = f"{bd.parent}/Shared/ggsans/ggsans-Bold.ttf"
        default_font = False

        try:
            base_font = ImageFont.truetype(font_path, label_font_size)
        except FileNotFoundError:
            logger.warning(
                f"Could not find ggsans-Bold at {font_path}, using default font"
            )
            default_font = True
            base_font = ImageFont.load_default()
        font = base_font

        player = self.players[player_idx]
        board_img = Image.new(
            mode="RGB",
            size=(
                (self.size[0] + label_offset) * tile_pixels,
                (self.size[1] + label_offset) * tile_pixels,
            ),
            color=0xFFFFFF,
        )
        draw: ImageDraw = ImageDraw.Draw(board_img)
        pilmoji: Pilmoji = Pilmoji(board_img)

        def draw_hatch_pattern(hatch_row: int, hatch_col: int):
            hatch_row += label_offset
            hatch_col += label_offset
            hatch_color: tuple[int, int, int] = (40, 40, 40)
            padding: int = 1

            x_start: int = tile_pixels * (hatch_col - 1)
            y_start: int = tile_pixels * (hatch_row - 1)

            x, y = x_start, y_start
            while y < y_start + tile_pixels:
                xy = (
                    (x_start + padding, y + padding),
                    (x + tile_pixels - padding, y_start + tile_pixels - padding),
                )
                draw.line(xy=xy, fill=hatch_color, width=1)
                x -= 4
                y += 4

            x, y = x_start, y_start
            while x < x_start + tile_pixels:
                xy = (
                    (x + padding, y_start + padding),
                    (x_start + tile_pixels - padding, y + tile_pixels - padding),
                )
                draw.line(xy=xy, fill=hatch_color, width=1)
                x += 4
                y -= 4

        # Draw column labels/tile borders

        for label_x in range(1, self.size[0] + 1):
            draw.rectangle(
                xy=(
                    (label_x * tile_pixels, 1),
                    ((label_x + 1) * tile_pixels, tile_pixels),
                ),
                fill=hidden_tile_color,
                outline=border_color,
                width=1,
            )
            draw.text(
                xy=(label_x * tile_pixels + tile_pixels / 2, tile_pixels / 2),
                text=str(label_x),
                font=font,
                anchor="mm",
                fill=font_color,
            )
        # Draw row labels/tile borders
        for label_y in range(1, self.size[1] + 1):
            draw.rectangle(
                xy=(
                    (1, label_y * tile_pixels),
                    (tile_pixels, (label_y + 1) * tile_pixels),
                ),
                fill=hidden_tile_color,
                outline=border_color,
                width=1,
            )
            draw.text(
                xy=(
                    round(tile_pixels / 2),
                    label_y * tile_pixels + round(tile_pixels / 2),
                ),
                text=str(label_y),
                font=font,
                anchor="mm",
                fill=font_color,
            )
        # Draw game tiles

        default_font_size: int = 24
        font_size = default_font_size
        emoji_pixels: int = font_size - 4
        if not default_font:
            font = ImageFont.truetype(font_path, font_size)

        for coords in self.board.keys():
            (row, col) = coords

            # Draw hidden tile as gray, skip to next tile
            if player_board and coords not in player.vis_tiles:
                draw.rectangle(
                    xy=(
                        (col * tile_pixels, row * tile_pixels),
                        ((col + 1) * tile_pixels, (row + 1) * tile_pixels),
                    ),
                    fill=hidden_tile_color,
                    outline=border_color,
                    width=1,
                )
                continue

            # Draw non-hidden tiles

            tile_zone = self.board[coords].zone
            if tile_zone is None:
                tile_color: tuple[int, int, int] = (255, 255, 255)
            else:
                tile_color = genre_colors[tile_zone]

            draw.rectangle(
                xy=(
                    (col * tile_pixels, row * tile_pixels),
                    (col * tile_pixels + tile_pixels, row * tile_pixels + tile_pixels),
                ),
                fill=tile_color,
                outline=border_color,
                width=1,
            )
            if self.board[coords].terrain == "river":
                draw_hatch_pattern(row, col)

            resource_text = (
                self.board[coords].resource if self.board[coords].resource else ""
            )

            # Draw start/end text
            if coords == player.start and not self.board[coords].rails:
                rail_text = "Start"
            elif coords == player.end and not self.board[coords].rails:
                rail_text = "End"
            else:
                rail_text = "".join(self.board[coords].rails)
            text_pixels = draw.textlength(text=resource_text + rail_text, font=font)

            # Dynamic font/emoji sizing depending on length of text
            if resource_text and rail_text:
                text_pixels += emoji_pixels
                text_offset = round(emoji_pixels * 0.4)
            else:
                text_offset = 0

            while text_pixels > 0.8 * tile_pixels and font_size > 6:
                font_size -= 2
                emoji_pixels -= 2
                if not default_font:
                    font = ImageFont.truetype(
                        f"{bd.parent}/Shared/ggsans/ggsans-Bold.ttf", font_size
                    )
                text_pixels = draw.textlength(text=resource_text + rail_text, font=font)
                if resource_text:
                    text_pixels += emoji_pixels

            # Draw tile resource and rails
            pilmoji.text(
                xy=(
                    col * tile_pixels + round(tile_pixels / 2) - text_offset,
                    row * tile_pixels + round(tile_pixels / 2),
                ),
                text=rail_text + resource_text,
                anchor="mm",
                fill=font_color,
                font=font,
                emoji_position_offset=(-round(font_size / 2), -round(font_size / 2)),
                emoji_scale_factor=1.1,
            )
            if font_size != default_font_size:
                font_size = default_font_size
                emoji_pixels = font_size - 4
                if not default_font:
                    font = ImageFont.truetype(
                        f"{bd.parent}/Shared/ggsans/ggsans-Bold.ttf", font_size
                    )

        try:
            board_img.save(f"{filepath}/{board_name}.png")
        except PermissionError:
            logger.error(f"Permission denied for board {board_name} at {filepath}")
            return "Could not write the board. Try again in a few seconds..."
        return None

    def update_player_stats_after_shot(
        self,
        sender_idx: int,
        player: TrainPlayer,
        undo: bool = False,
        shot: TrainShot = None,
    ):
        check_gem_time = False
        if self.board[shot.coords()].resource == game_emoji["gems"]:
            shot_list = player.shots[:-1] if undo else player.shots
            if game_emoji["gems"] not in [
                self.board[shot.coords()].resource for shot in shot_list
            ]:
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
                self.players[sender_idx].donetime = datetime.now().strftime(
                    "%Y%m%d%H%M%S"
                )
            if check_gem_time:
                self.players[sender_idx].score["GemTime"] = int(
                    datetime.strptime(shot.time, bd.date_format).timestamp()
                )

        self.update_vis_tiles(
            player_idx=sender_idx, shot_row=shot.row, shot_col=shot.col, remove=undo
        )
        if undo:
            shot = player.shots[-1]
            self.update_vis_tiles(
                player_idx=sender_idx, shot_row=shot.row, shot_col=shot.col
            )
            self.update_vis_tiles(
                player_idx=sender_idx,
                shot_row=player.start[0],
                shot_col=player.start[1],
            )
            self.update_vis_tiles(
                player_idx=sender_idx,
                shot_row=player.end[0],
                shot_col=player.end[1],
                render_dist=0,
            )

        if self.board[shot.coords()].terrain == "river":
            if "Pontoon Bridge" in player.inventory:
                rails = 0
                player.update_item_count("Pontoon Bridge")
            else:
                rails = 2
        else:
            rails = 1

        if self.board[shot.coords()].zone in self.known_shows[shot.show_id]["genres"]:
            rails *= 0.5
        if undo:
            self.players[sender_idx].rails -= rails
        else:
            self.players[sender_idx].rails += rails

    def buy_item(self, itemname: str, showinfo: str, ctx: Interaction) -> bool:
        player_idx, player = self.get_player(ctx.user.id)
        if player is None or self.shop[itemname].amount < 1 or not player.shots:
            return True

        player_loc = (player.shots[-1].row, player.shots[-1].col)

        if self.board[player_loc].resource not in (
            game_emoji["shop"],
            game_emoji["city"],
        ):
            return True

        if player_loc in player.shops_used:
            return True

        if itemname in self.players[player_idx].inventory:
            self.players[player_idx].inventory[itemname].amount += 1
        else:
            self.players[player_idx].inventory[itemname] = default_shop()[itemname]
            self.players[player_idx].inventory[itemname].amount = 1
            self.players[player_idx].inventory[itemname].showinfo += f" {showinfo}"

        player.shops_used.append(player_loc)
        logger.debug(
            f"Player {player.member.name} bought {itemname} for game {self.name} in {ctx.guild.name}"
        )
        self.shop[itemname].amount -= 1
        self.save_game(f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{self.name}")
        return False

    def use_bucket(self, ctx: Interaction, row: int, col: int) -> bool:
        player_idx, player = self.get_player(ctx.user.id)
        if player is None:
            return True

        if "Bucket" not in player.inventory or not self.in_bounds(row, col):
            return True

        self.board[(row, col)].terrain = "river"

        player.update_item_count("Bucket")
        return False

    async def calculate_player_scores(self, ctx: Interaction) -> None:
        def add_to_score(p: TrainPlayer, key: str, val: int):
            if key in player.score:
                p.score[key] += val
            else:
                p.score[key] = val

        for player in self.players:
            if player.donetime is None:
                player.donetime = datetime.now().strftime("%Y%m%d%H%M%S")
        self.players.sort(key=lambda p: p.donetime)

        # Find player prison counts and gun effects before counting score for intersection scoring
        player_prison_counts = {}
        player_starting_anilists = []

        for player in self.players:
            player.score = {}  # Avoid re-adding to non-zero score
            player_starting_anilists += player.starting_anilist
            track_resources = [
                self.board[shot.coords()].resource for shot in player.shots
            ]
            player_prison_counts[player.tag] = track_resources.count(
                game_emoji["prison"]
            )
            if player_prison_counts[player.tag] != 0 and "Gun" in player.inventory:
                player_prison_counts[player.tag] += 0.5 * player.inventory["Gun"].amount

        city_coords: dict[tuple[int, int], str] = {}
        for idx, player in enumerate(self.players):
            # Quest Scoring

            ending_anilist = await al.query_user_animelist(player.anilist_id)
            anilist_changes = find_anilist_changes(
                player.starting_anilist, ending_anilist
            )

            # Fast finish scoring
            if idx == 0:
                player.score["speed bonus"] = 2
            elif idx == 1:
                player.score["speed bonus"] = 1

            # Item score bonuses
            axe_bonus = 0
            if "Axe" in player.inventory:
                axe_bonus += 0.5 * player.inventory["Axe"].amount

            if "Coin" in player.inventory:
                add_to_score(
                    p=player, key="coins", val=2 * player.inventory["Coin"].amount
                )

            has_city = False
            num_houses = 0

            least_watched_genre_shots = 0
            anime_sources = []
            genre_zone_matched = False
            shots_without_resources = 0
            shots_without_resources_quest_complete = False
            different_player_anime_shots = []
            train_tag_quest_complete = False

            for shot in player.shots:
                shot_tile: TrainTile = self.board[shot.coords()]
                shot_anime_info = self.known_shows[shot.show_id]

                if not train_tag_quest_complete and any(
                    tag["name"] == "Trains" and tag["rank"] > 40
                    for tag in shot_anime_info["tags"]
                ):
                    if any(
                        anime["mediaId"] == shot.show_id
                        and anime["progress"] == shot_anime_info["episodes"]
                        for anime in anilist_changes
                    ):
                        train_tag_quest_complete = True
                if len(shot_tile.rails) > 1:
                    intersecting_player_tag = [
                        tag for tag in shot_tile.rails if tag != player.tag
                    ][0]
                    add_to_score(
                        p=player,
                        key="intersections",
                        val=1 - player_prison_counts[intersecting_player_tag],
                    )

                if shot_tile.resource == game_emoji["city"]:
                    has_city = True
                    if shot.coords() not in city_coords:
                        city_coords[shot.coords()] = choice(
                            ["SPRING", "SUMMER", "AUTUMN", "WINTER"]
                        )
                    if shot_anime_info["season"] == city_coords[shot.coords()]:
                        add_to_score(p=player, key="city season bonus", val=3)
                elif shot_tile.resource == game_emoji["wheat"]:
                    add_to_score(p=player, key="wheat", val=1)

                elif shot_tile.resource == game_emoji["wood"]:
                    add_to_score(p=player, key="wood", val=2)

                elif shot_tile.resource == game_emoji["gems"]:
                    add_to_score(p=player, key="gems", val=2)

                elif shot_tile.resource == game_emoji["house"]:
                    num_houses += 1
                    add_to_score(p=player, key="houses", val=1)

                if not shots_without_resources_quest_complete:
                    if not shot_tile.resource:
                        shots_without_resources += 1
                        if shots_without_resources >= 6:
                            shots_without_resources_quest_complete = True
                    else:
                        shots_without_resources = 0
                if player.least_watched_genre in shot_anime_info["genres"]:
                    least_watched_genre_shots += 1
                if shot_anime_info["source"] not in anime_sources:
                    anime_sources.append(shot_anime_info["source"])
                if shot_tile.zone in shot_anime_info["genres"]:
                    genre_zone_matched = True
                if any(
                    shot.show_id == d["mediaId"] for d in player_starting_anilists
                ) and not any(
                    d["mediaId"] == shot.show_id for d in player.starting_anilist
                ):
                    if shot.show_id not in different_player_anime_shots:
                        different_player_anime_shots.append(shot.show_id)

            if has_city and "wheat" in player.score:
                player.score["wheat"] += 3
            if has_city and "houses" in player.score:
                player.score["houses"] += 1 * num_houses
                player.score["houses"] -= player_prison_counts[player.tag] * num_houses

            player.score["rails bonus"] = -2 * int((player.rails - 26) / 3)

            if least_watched_genre_shots >= 2:
                player.score["quest: least watched genre"] = 4
            if len(anime_sources) >= 4:
                player.score["quest: different sources"] = 3
            if not genre_zone_matched:
                player.score["quest: genre zone match"] = 3
            if shots_without_resources_quest_complete:
                player.score["quest: shots without resources"] = 3
            if len(different_player_anime_shots) >= 3:
                player.score["quest: other player's shows"] = 2
            if train_tag_quest_complete:
                player.score["quest: train tag"] = 3

            player.score["total"] = sum(player.score.values())

        self.save_game(f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{self.name}")

    def gen_score_embed(
        self, ctx: Interaction, page: int = 0
    ) -> tuple[Embed, Union[None, File]]:
        embed = Embed()

        max_pages: int = len(self.players) + 1
        page: int = 1 + (page % max_pages)  # Loop back through pages both ways
        embed.set_footer(text=f"Page {page}/{max_pages}")
        embed.set_author(name="Anime Trains", icon_url=bd.bot_avatar_url)
        embed.colour = 0xFF9C2C

        self.players.sort(key=lambda p: p.score["total"], reverse=True)

        if page == 1:
            embed.title = "Game Complete!"
            embed.description = "*Scoring results are as follows...*"
            for idx, player in enumerate(self.players):
                place_emojis = {
                    0: game_emoji["first"],
                    1: game_emoji["second"],
                    2: game_emoji["third"],
                }
                place_emoji = place_emojis.get(idx, "")
                embed.add_field(
                    name="\u200b",
                    value=f"{place_emoji} {player.member.mention}'s score is **{player.score['total']}**",
                    inline=False,
                )
            board_img_path = (
                f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{self.name}/MASTER.png"
            )
            if not path.exists(board_img_path):
                self.draw_board_img(
                    filepath=f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{self.name}",
                    board_name="MASTER",
                    player_board=False,
                )
            try:
                with open(board_img_path, "rb") as f:
                    file = BytesIO(f.read())
            except FileNotFoundError:
                return embed, None

            image = File(file, filename="MASTER.png")
            embed.set_image(url="attachment://MASTER.png")
            return embed, image

        player_idx: int = page - 2
        embed.set_thumbnail(url=self.players[player_idx].member.avatar.url)
        embed.title = f"{self.players[player_idx].member.name}"
        for category, score in self.players[player_idx].score.items():
            embed.add_field(name=category.title(), value=score)

        return embed, None


async def load_trains_game(
    filepath: str, guild: Guild, active_only: bool = False
) -> TrainGame | None:
    with open(f"{filepath}/gamedata.json", "r") as f:
        game_dict = json.load(f)
    if (
        active_only and not game_dict["active"]
    ):  # Skip loading inactive games if specified for faster loads
        return TrainGame(active=False)

    # Convert str/list keys back into tuple for use in game
    board: dict = {}
    for key, val in game_dict["board"].items():
        coords = key[1:-1].split(",")
        coords[0] = int(coords[0])
        coords[1] = int(coords[1])
        coords = tuple(coords)
        board[coords] = TrainTile(
            resource=game_dict["board"][key]["resource"],
            zone=game_dict["board"][key]["zone"],
            rails=game_dict["board"][key]["rails"],
            terrain=game_dict["board"][key]["terrain"],
        )

    shop: dict = {}

    for item in game_dict["shop"].values():
        shop[item["name"]] = TrainItem(
            name=item["name"],
            emoji=item["emoji"],
            description=item["description"],
            amount=item["amount"],
            cost=item["cost"],
            showinfo=item["showinfo"],
            uses=item["uses"],
        )

    # Convert player dicts back into player classes
    player_list: list = []
    for player in game_dict["players"]:
        shot_list: list = []
        for shot in player["shots"]:
            shot_list.append(
                TrainShot(
                    row=shot["row"],
                    col=shot["col"],
                    show_id=shot["show_id"],
                    info=shot["info"],
                    time=shot["time"],
                )
            )

        item_dict: dict = {}
        for name, item in player["inventory"].items():
            if "showinfo" not in item:
                item["showinfo"] = ""
            item_dict[name] = TrainItem(
                name=item["name"],
                emoji=item["emoji"],
                description=item["description"],
                amount=item["amount"],
                cost=item["cost"],
                showinfo=item["showinfo"],
                uses=item["showinfo"],
            )

        member = await guild.fetch_member(player["member_id"])
        dm_channel = (
            await member.create_dm() if not member.dm_channel else member.dm_channel
        )
        player_list.append(
            TrainPlayer(
                member=member,
                tag=player["tag"],
                done=player["done"],
                rails=player["rails"],
                dmchannel=dm_channel,
                start=tuple(player["start"]),
                end=tuple(player["end"]),
                score=player["score"],
                shots=shot_list,
                vis_tiles=[tuple(tile) for tile in player["vis_tiles"]],
                donetime=player["donetime"],
                inventory=item_dict,
                starting_anilist=player["starting_anilist"],
                anilist_id=player["anilist_id"],
                least_watched_genre=player["least_watched_genre"],
            )
        )

    game = TrainGame(
        name=game_dict["name"],
        date=game_dict["date"],
        players=player_list,
        board=board,
        gameid=game_dict["gameid"],
        active=game_dict["active"],
        size=tuple(game_dict["size"]),
        shop=shop,
        known_shows={
            int(show_id): show_info
            for show_id, show_info in game_dict["known_shows"].items()
        },
    )
    return game
