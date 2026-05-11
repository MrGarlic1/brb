import asyncio
import io
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

from discord import (
    Interaction,
    Embed,
    File,
    Member as DiscordMember,
    Guild as DiscordGuild,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import Optional
from brbot.db.models import (
    TrainTile,
    TrainShot,
    TrainPlayer,
    TrainGame,
    TrainPlayerTile,
)
from brbot.Shared.Members.repository import get_or_create_members
from brbot.Shared.Users.repository import get_or_create_users


import brbot.Shared.Anilist.anilist as al
import brbot.Core.botdata as bd
from brbot.Features.Trains.data import (
    RIVER_RING,
    RiverDirection,
    GameEmoji,
    genre_colors,
    default_shop,
    find_anilist_changes,
)

logger = logging.getLogger(__name__)


class TrainService:
    def __init__(self):
        pass

    @staticmethod
    async def get_guild_active_train_game(
        guild_id: int, session: AsyncSession, load_players: bool = False
    ) -> Optional[TrainGame]:
        stmt = (
            select(TrainGame)
            .where(TrainGame.guild_id == guild_id)
            .where(TrainGame.active.is_(True))
        )
        if load_players:
            stmt = stmt.options(
                selectinload(TrainGame.players).selectinload(TrainPlayer.member),
                selectinload(TrainGame.players).selectinload(TrainPlayer.shots),
                selectinload(TrainGame.players).selectinload(TrainPlayer.player_tiles),
            )

        result = await session.execute(stmt)
        return result.scalars().first()

    @staticmethod
    async def create_train_game(
        guild: DiscordGuild,
        name: str,
        players: list[DiscordMember],
        height: int,
        width: int,
        session_generator: async_sessionmaker,
    ) -> str | None:
        discord_ids = [m.id for m in players]
        discord_usernames = [m.name for m in players]

        async with session_generator() as session:
            users = await get_or_create_users(discord_ids, discord_usernames, session)

            for u in users:
                if u.anilist_id is None:
                    return f"Could not create game, {u.mention_str} must link their anilist profile! (/animanga link)"

            members = await get_or_create_members(discord_ids, guild.id, session)
            member_ids_by_discord_id: dict[int, int] = {
                m.user_id: m.id for m in members
            }

            anilist_id_by_discord_id: dict[int, int] = {
                u.user_id: u.anilist_id for u in users
            }
            await session.commit()

        try:
            anilist_info_by_discord_id: dict[int, list] = {
                discord_id: await al.query_user_animelist(anilist_id)
                for discord_id, anilist_id in anilist_id_by_discord_id.items()
            }
        except Exception as e:
            logger.error(
                f"Could not find anilist information for players(s) in guild {guild.id}, aborting game creation: {e}"
            )
            return "Error connecting to anilist, please try again later."

        tags_by_discord_id = await TrainService.get_player_tags(players)

        async with session_generator() as session:
            # Add board/game
            game = TrainGame(
                guild_id=guild.id,
                name=name,
                date=datetime.now(),
                board_height=height,
                board_width=width,
                active=True,
            )
            session.add(game)
            await session.flush()
            game_id: int = game.id
            board = await TrainService.gen_trains_board(
                game_id=game_id, play_width=width, play_height=height
            )
            session.add_all(board.values())

            # Add players
            train_players = []
            for discord_id in anilist_id_by_discord_id.keys():
                train_players.append(
                    TrainPlayer(
                        game_id=game_id,
                        member_id=member_ids_by_discord_id[discord_id],
                        starting_anilist=anilist_info_by_discord_id[discord_id],
                        tag=tags_by_discord_id[discord_id],
                        rails=0,
                        done=False,
                    )
                )

            train_players = await TrainService.add_player_locations(
                train_players, board, width, height, session
            )
            session.add_all(train_players)
            await session.flush()

            # Add start/end to rendered tiles
            for player in train_players:
                await session.refresh(player, ["player_tiles"])

            for player in train_players:
                await TrainService.add_vis_tiles(
                    player,
                    (player.start_col, player.start_row),
                    (width, height),
                    board,
                    session,
                    render_dist=0,
                )
                await TrainService.add_vis_tiles(
                    player,
                    (player.end_col, player.end_row),
                    (width, height),
                    board,
                    session,
                    render_dist=0,
                )

            await session.commit()

        await TrainService.update_boards_after_create(
            guild, session_generator=session_generator
        )
        return None

    @staticmethod
    async def get_player_tags(players: list[DiscordMember]) -> dict[int, str]:
        """
        Update game players with unique short names for  to be represented on the board

        Returns:
            Dictionary of tags, keyed by discord user ID
        """
        tags_by_discord_id: dict[int, str] = {}
        used_tags: list = []
        for player in players:
            done = False
            for idx, letter in enumerate(player.global_name):
                tag = player.global_name[0 : idx + 1].upper()
                if tag not in used_tags:
                    used_tags.append(tag)
                    tags_by_discord_id[player.id] = tag
                    done = True
                    break
            if not done:
                used_tags.append(player.global_name.upper())
                tags_by_discord_id[player.id] = player.global_name.upper()
        return tags_by_discord_id

    @staticmethod
    async def gen_trains_board(
        game_id: int, play_width: int, play_height: int
    ) -> dict[tuple[int, int], TrainTile]:
        width = play_height + 2 * RIVER_RING
        height = play_width + 2 * RIVER_RING

        logger.info(f"Generating {width}x{height} board for game {game_id}")

        board: dict[tuple[int, int], TrainTile] = {}

        def next_to_resource(tilepos: tuple[int, int], resource: str) -> bool:
            # Returns true if the grid tile is directly adjacent to the specified resource
            x = tilepos[0]
            y = tilepos[1]

            for x_new in (x - 1, x + 1):
                if board.get((x_new, y)).resource == resource:
                    return True

            for y_new in (y - 1, y + 1):
                if board.get((x, y_new)).resource == resource:
                    return True

            return False

        def near_resource(tilepos: tuple[int, int], resource: str, spread: int) -> bool:
            # Returns true if the grid tile is within {spread} tiles of the specified resource
            # Tilepos is (x, y)
            x = tilepos[0]
            y = tilepos[1]

            for x_new in range(x - spread, x + spread):
                for y_new in range(y - spread, y + spread):
                    if board.get((x_new, y_new)).resource == resource:
                        return True

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

            if board[tilepos].resource is not None:
                return board[tilepos].resource

            if board[tilepos].terrain is not None:
                return None

            # Wheat
            if near_resource(tilepos, GameEmoji.WHEAT.name, 3):
                if randint(1, 1000) <= wheat_near_chance:
                    return GameEmoji.WHEAT.name
            else:
                if randint(1, 1000) <= wheat_chance:
                    return GameEmoji.WHEAT.name

            # Wood
            if near_resource(tilepos, GameEmoji.WOOD.name, 2):
                if randint(1, 1000) <= wood_near_chance:
                    return GameEmoji.WOOD.name
            else:
                if randint(1, 1000) <= wood_chance:
                    return GameEmoji.WOOD.name

            # Houses
            if next_to_resource(tilepos, GameEmoji.HOUSE.name):
                if randint(1, 1000) <= house_near_chance:
                    return GameEmoji.WOOD.HOUSE.name
            else:
                if randint(1, 1000) <= house_chance:
                    return GameEmoji.WOOD.HOUSE.name

            return None

        def generate_count_resource(
            count: int, resource: str, min_spread: int = 0
        ) -> None:
            # Grid Size is (x, y), or (col, row)
            added = 0
            attempts = 0
            while added < count:
                attempts += 1

                x = randint(1, width)
                y = randint(1, height)
                # Add resource if tile is empty and meets the minimum spread requirement
                if (
                    board[(x, y)].resource is None
                    and board[(x, y)].terrain is None
                    and not near_resource((x, y), resource, min_spread)
                ):
                    board[(x, y)].resource = resource
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
            return None

        def generate_zones() -> None:
            # Adds genre zones in randomized order to grid. Both dimensions of the grid must be divisible by 4 to allow
            # for 16 zones.

            def add_zone(z_width, z_height, start_pos, genre) -> None:
                for row in range(start_pos[0], start_pos[0] + z_height):
                    for col in range(start_pos[1], start_pos[1] + z_width):
                        board[(row, col)].zone = genre

            if play_width % 4 != 0 or play_height % 4 != 0:
                logger.error(
                    f"Invalid board dimensions ({play_width} x {play_height}) tiles, generation aborted"
                )
                raise AttributeError("Width and height must be divisible by 4.")

            zone_width: int = play_width // 4
            zone_height: int = play_height // 4
            zone_order: list = list(genre_colors.keys())
            shuffle(zone_order)

            for i in range(16):
                zone_pos = (
                    zone_height * (i // 4) + RIVER_RING + 1,
                    zone_width * (i % 4) + RIVER_RING + 1,
                )
                add_zone(zone_width, zone_height, zone_pos, zone_order[i])
            return None

        def generate_river(direction: RiverDirection) -> None:
            # Chance of river ending: [0, 1]
            base_chance: float = 0.9

            # River shape parameters. Average river width and river cohesion (higher density = less spread out river)
            avg_width: float = 1.5
            density: float = 2.2

            river_tiles: list[tuple[int, int]] = []

            if direction == RiverDirection.RIGHT:
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

            elif direction == RiverDirection.DOWN_RIGHT:
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

            elif direction == RiverDirection.DOWN:
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

            elif direction == RiverDirection.DOWN_LEFT:
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
                board[pos].terrain = "river"
            return None

        # For zones to generate, both board dimensions must be divisible by 4

        # Generate empty board
        for c in range(width):
            for r in range(height):
                if c + 1 <= RIVER_RING or c + 1 > height - RIVER_RING:
                    terrain = "river"
                elif r + 1 <= RIVER_RING or r + 1 > width - RIVER_RING:
                    terrain = "river"
                else:
                    terrain = None
                board[(c + 1, r + 1)] = TrainTile(
                    column=c,
                    row=r,
                    game_id=game_id,
                    terrain=terrain,
                )

        # Add terrain (chance out of 1000)
        river_chance = 900
        if randint(1, 1000) <= river_chance:
            river_dir = choice(list(RiverDirection))
            logger.debug(f"Generating river tiles in {river_dir} for game {game_id}")
            generate_river(river_dir)

        # Add count-based resources
        city_count: int = 4
        prison_count: int = 2
        gem_count: int = 2
        shop_count: int = 4

        generate_count_resource(
            count=city_count, resource=GameEmoji.CITY.name, min_spread=4
        )
        generate_count_resource(
            count=prison_count, resource=GameEmoji.PRISON.name, min_spread=6
        )
        generate_count_resource(
            count=gem_count, resource=GameEmoji.GEMS.name, min_spread=8
        )
        generate_count_resource(
            count=shop_count, resource=GameEmoji.SHOP.name, min_spread=8
        )

        # Add random resources
        for c in range(width):
            for r in range(height):
                board[(c + 1, r + 1)].resource = generate_random_resources(
                    (r + 1, c + 1)
                )

        # Add genre zones
        generate_zones()
        return board

    @staticmethod
    async def add_player_locations(
        players: list[TrainPlayer],
        board: dict[tuple[int, int], TrainTile],
        width: int,
        height: int,
        session: AsyncSession,
    ) -> list[TrainPlayer]:
        row_bounds = (1 + RIVER_RING, height - RIVER_RING)
        col_bounds = (1 + RIVER_RING, width - RIVER_RING)
        taken_spaces: list = []

        for player_idx, player in enumerate(players):
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
                    board[start_loc].terrain is None
                    and board[start_loc].resource is None
                    and start_loc not in taken_spaces
                ):
                    player.start = start_loc
                    taken_spaces.append(start_loc)
                    break
                attempts += 1
            if start_loc is None or attempts > 40:  # Error catch
                logger.error(
                    f"Unable to generate player {player_idx}'s starting location in game "
                    f" after {attempts}, aborting."
                )
                raise Exception(
                    "Failed generating board. Try increasing the board size?"
                )

            # Generate end locations
            attempts = 0
            end_loc = None
            while attempts <= 40:
                if quadrant == "Left":
                    end_loc = (randint(row_bounds[0], row_bounds[1]), col_bounds[1])
                else:
                    end_loc = (row_bounds[1], randint(col_bounds[0], col_bounds[1]))

                if (
                    board[end_loc].terrain is None
                    and board[end_loc].resource is None
                    and end_loc not in taken_spaces
                ):
                    player.end = end_loc
                    taken_spaces.append(end_loc)
                    break
                attempts += 1
            if end_loc is None or attempts > 40:  # Error catch
                logger.error(
                    f"Unable to generate player {player_idx}'s ending location in game "
                    f" after {attempts}, aborting."
                )
                raise Exception(
                    "Failed generating board. Try increasing the board size?"
                )

        return players

    @staticmethod
    async def add_vis_tiles(
        player: TrainPlayer,
        root_position: tuple[int, int],
        board_size: tuple[int, int],
        board: dict[tuple[int, int], TrainTile],
        session: AsyncSession,
        telescope_count: int = 0,
        render_dist: int = 4,
    ) -> None:
        shot_col = root_position[0]
        shot_row = root_position[1]
        render_dist += telescope_count

        vis_tiles_by_coordinate = {
            (tile.column, tile.row): tile for tile in player.player_tiles
        }

        new_vis_tiles: list[TrainPlayerTile] = []

        for col in range(shot_col - render_dist, shot_col + render_dist + 1):
            for row in range(shot_row - render_dist, shot_row + render_dist + 1):
                if (col, row) in vis_tiles_by_coordinate:  # Already rendered tiles
                    continue
                elif TrainService.in_bounds(col, row, size=board_size):
                    new_vis_tiles.append(
                        TrainPlayerTile(
                            tile_id=board[(col, row)].id,
                            column=col,
                            row=row,
                            player_id=player.id,
                            has_rail=shot_col == col and shot_row == row,
                        )
                    )

        session.add_all(new_vis_tiles)

    @staticmethod
    def in_bounds(row: int, col: int, size: tuple[int, int]) -> bool:
        if row < 1 or col < 1 or row > size[1] or col > size[0]:
            return False
        else:
            return True

    @staticmethod
    def is_done(players: list[TrainPlayer]) -> bool:
        done = True
        for player in players:
            if not player.done:
                done = False
                break
        return done

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

    async def set_game_anilist_info(self):
        max_concurrent = asyncio.Semaphore(6)

        async def get_player_anilist_info(player: TrainPlayer) -> TrainPlayer | None:
            async with max_concurrent:
                starting_anilist = await al.query_user_animelist(
                    bd.linked_profiles[player.member.id]
                )
                least_watched_genre = await al.query_user_genres(
                    bd.linked_profiles[player.member.id]
                )
            if not starting_anilist or not least_watched_genre:
                raise AttributeError(
                    f"Player {player.member.name} anilist info not found."
                )

            player.starting_anilist = starting_anilist
            player.least_watched_genre = least_watched_genre
            return player

        tasks: list = [get_player_anilist_info(p) for p in self.players]
        try:
            self.players = await asyncio.gather(*tasks)
        except Exception as e:
            raise e

    @staticmethod
    async def push_player_update(guild: DiscordGuild, game: TrainGame, p: TrainPlayer):
        board = {(tile.column, tile.row): tile for tile in game.tiles}
        img = TrainService.draw_board_img(
            game_width=game.board_width,
            game_height=game.board_height,
            board=board,
            player=p,
            hide_hidden_tiles=True,
        )

        await p.dmchannel.send(
            file=File(img, filename="train_board.png"),
            content=f'## Train board update for "{game.name}" in {guild.name}!',
        )

    @staticmethod
    async def update_boards_after_shot(
        guild: DiscordGuild, row: int, column: int
    ) -> None:
        # Push updates to player boards, check if game is finished
        tasks: list = []
        for player_idx, player in enumerate(self.players):
            if (row, column) in player.vis_tiles:
                logger.debug(
                    f"Sending board update with shot ({row}, {column}) to "
                    f"{player.member.name} for game {self.name} in {guild.name}"
                )
                tasks.append(
                    asyncio.create_task(
                        self.push_player_update(guild, player, player_idx)
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

    @staticmethod
    async def update_boards_after_create(
        guild: DiscordGuild, session_generator: async_sessionmaker
    ) -> None:
        async with session_generator() as session:
            stmt = (
                select(TrainGame)
                .where(TrainGame.guild_id == guild.id)
                .where(TrainGame.active)
                .options(
                    selectinload(TrainGame.players).selectinload(
                        TrainPlayer.player_tiles
                    )
                )
                .options(
                    selectinload(TrainGame.players).selectinload(TrainPlayer.member)
                )
                .options(selectinload(TrainGame.tiles))
            )
            result = await session.execute(stmt)
            game: TrainGame = result.scalar_one()

        tasks: list = []

        for player in game.players:
            if player.dmchannel is None:
                member = await guild.fetch_member(player.member.user_id)
                player.dmchannel = member.dm_channel

            logger.debug(
                f"Sending initial board to "
                f"{player.member.name} for game {game.name} in {guild.name}"
            )
            tasks.append(
                asyncio.create_task(
                    TrainService.push_player_update(guild, game, player)
                )
            )
        await asyncio.gather(*tasks)
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

    @staticmethod
    def draw_board_img(
        game_width: int,
        game_height: int,
        board: dict[tuple[int, int], TrainTile],
        player: TrainPlayer,
        hide_hidden_tiles: bool = False,
    ) -> BytesIO:
        # Generate board image. If player board: only generate tiles which are rendered.
        # Grey out other tiles.

        player_start = (player.start_col, player.start_row)
        player_end = (player.end_col, player.end_row)
        vis_tiles = {(tile.column, tile.row): tile for tile in player.player_tiles}

        # Adjustments
        label_offset: int = 1
        label_font_size: int = 24
        tile_pixels: int = 50
        hidden_tile_color: tuple[int, int, int] = (255, 255, 255)
        border_color: tuple[int, int, int] = (190, 190, 190)
        font_color: tuple[int, int, int] = (0, 0, 0)
        font_path = f"{bd.STATIC_DIRECTORY}/ggsans/ggsans-Bold.ttf"
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

        board_img = Image.new(
            mode="RGB",
            size=(
                (game_width + label_offset) * tile_pixels,
                (game_height + label_offset) * tile_pixels,
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

        for label_x in range(1, game_width + 1):
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
        for label_y in range(1, game_height + 1):
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

        for coords in board.keys():
            (row, col) = coords

            # Draw hidden tile as gray, skip to next tile
            if hide_hidden_tiles and coords not in vis_tiles:
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

            tile_zone = board[coords].zone
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
            if board[coords].terrain == "river":
                draw_hatch_pattern(row, col)

            resource_text = board[coords].resource if board[coords].resource else ""

            # Draw start/end text
            if coords == player_start and not vis_tiles[coords].has_rail:
                rail_text = "Start"
            elif coords == player_end and not vis_tiles[coords].has_rail:
                rail_text = "End"
            else:
                rail_text = vis_tiles[coords].rail_text
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

        buffer = BytesIO()
        board_img.save(buffer, format="png")
        buffer.seek(0)
        return buffer

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
