from datetime import datetime, timezone
from random import randint, shuffle, choice

import logging

from discord import (
    Interaction,
    Member as DiscordMember,
    Guild as DiscordGuild,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import Optional, Sequence
from brbot.db.models import (
    Member,
    TrainTile,
    TrainItem,
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


class GameService:
    def __init__(self):
        pass

    @staticmethod
    async def get_guild_train_game(
        guild_id: int,
        session: AsyncSession,
        load_players: bool = False,
        active: bool = True,
        name: str = None,
    ) -> Optional[TrainGame]:
        stmt = (
            select(TrainGame)
            .where(TrainGame.guild_id == guild_id)
            .where(TrainGame.active.is_(active))
        )
        if name is not None:
            stmt = stmt.where(TrainGame.name == name)
        if load_players:
            stmt = stmt.options(
                selectinload(TrainGame.players).selectinload(TrainPlayer.member),
                selectinload(TrainGame.tiles),
                selectinload(TrainGame.players).selectinload(TrainPlayer.shots),
                selectinload(TrainGame.players).selectinload(TrainPlayer.player_tiles),
            )

        result = await session.execute(stmt)
        return result.scalars().first()

    @staticmethod
    async def get_guild_game_names(
        guild_id: int, session: AsyncSession
    ) -> Optional[Sequence[str]]:
        stmt = select(TrainGame.name).where(TrainGame.guild_id == guild_id)
        result = await session.execute(stmt)
        return result.scalars().all()

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
        play_width = width
        play_height = height
        width += 2 * RIVER_RING
        height += 2 * RIVER_RING
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

        tags_by_discord_id = await GameService.get_player_tags(players)

        async with session_generator() as session:
            # Add board/game
            game = TrainGame(
                guild_id=guild.id,
                name=name,
                date=datetime.now(timezone.utc),
                board_height=height,
                board_width=width,
                active=True,
            )
            session.add(game)
            await session.flush()
            game_id: int = game.id
            board = await GameService.gen_trains_board(
                game_id=game_id, play_width=play_width, play_height=play_height
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
            train_players = await GameService.add_player_locations(
                train_players, board, width, height
            )

            session.add_all(train_players)
            await session.flush()

            # Add start/end to rendered tiles
            for player in train_players:
                await session.refresh(player, ["player_tiles"])

            for player in train_players:
                await GameService.add_vis_tiles(
                    player,
                    (player.start_col, player.start_row),
                    (width, height),
                    board,
                    session,
                    render_dist=0,
                    is_shot=False
                )
                await GameService.add_vis_tiles(
                    player,
                    (player.end_col, player.end_row),
                    (width, height),
                    board,
                    session,
                    render_dist=0,
                    is_shot=False
                )

            await session.commit()
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
                    if (x_new, y_new) not in board:
                        continue
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
                    column=c + 1,
                    row=r + 1,
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
    ) -> list[TrainPlayer]:
        row_bounds = (1 + RIVER_RING, height - RIVER_RING)
        col_bounds = (1 + RIVER_RING, width - RIVER_RING)
        taken_spaces: list = []

        for player_idx, player in enumerate(players):
            quadrant: str = choice(("Left", "Top"))

            # Generate start locations (NOTE: game.size is (width, height), coordinates are in (col, row)
            attempts: int = 0
            start_loc = None
            while attempts <= 40:
                if quadrant == "Left":
                    start_loc = (randint(col_bounds[0], col_bounds[1]), row_bounds[0])
                else:
                    start_loc = (col_bounds[0], randint(row_bounds[0], row_bounds[1]))

                if (
                    board[start_loc].terrain is None
                    and board[start_loc].resource is None
                    and start_loc not in taken_spaces
                ):
                    player.start_col = start_loc[0]
                    player.start_row = start_loc[1]
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
                    end_loc = (randint(col_bounds[0], col_bounds[1]), row_bounds[1])
                else:
                    end_loc = (col_bounds[1], randint(row_bounds[0], row_bounds[1]))

                if (
                    board[end_loc].terrain is None
                    and board[end_loc].resource is None
                    and end_loc not in taken_spaces
                ):
                    player.end_col = end_loc[0]
                    player.end_row = end_loc[1]
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
    async def save_shot(
        game: TrainGame, player: TrainPlayer, shot: TrainShot, session: AsyncSession
    ):
        board = {tile.position: tile for tile in game.tiles}
        inventory: list[TrainItem] = player.items
        telescope_count = len(
            [item for item in inventory if item.emoji == GameEmoji.TELESCOPE.name]
        )

        # Update DB Objects (Add player tiles, update stats)
        await GameService.add_vis_tiles(
            player=player,
            root_position=shot.coords,
            board_size=game.size,
            board=board,
            session=session,
            telescope_count=telescope_count,
        )

        GameService.update_stats_after_shot(game, player, shot)
        await session.flush()
        return False

    @staticmethod
    async def add_vis_tiles(
        player: TrainPlayer,
        root_position: tuple[int, int],
        board_size: tuple[int, int],
        board: dict[tuple[int, int], TrainTile],
        session: AsyncSession,
        telescope_count: int = 0,
        render_dist: int = 4,
        is_shot: bool = True
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
                elif GameService.in_bounds(col, row, size=board_size):
                    new_vis_tiles.append(
                        TrainPlayerTile(
                            tile_id=board[(col, row)].id,
                            column=col,
                            row=row,
                            player_id=player.id,
                            has_rail=shot_col == col and shot_row == row and is_shot,
                        )
                    )

        session.add_all(new_vis_tiles)

    @staticmethod
    def in_bounds(col: int, row: int, size: tuple[int, int]) -> bool:
        if row < 1 or col < 1 or row > size[1] or col > size[0]:
            return False
        else:
            return True

    @staticmethod
    def is_done(game: TrainGame) -> bool:
        done = True
        for player in game.players:
            if not player.done:
                done = False
                break
        return done

    @staticmethod
    def is_valid_shot(
        game: TrainGame, player: TrainPlayer, shot_col: int, shot_row: int
    ) -> bool:
        board: dict[tuple[int, int], TrainTile] = {
            (tile.column, tile.row): tile for tile in game.tiles
        }
        if player is None:  # Player not in game
            return False

        if player.done:
            return False

        if player.shots:
            last_shot: TrainShot = player.shots[-1]
            base_coords = last_shot.coords
        else:
            if (shot_col, shot_row) == (player.start_col, player.start_row):
                return True
            else:
                return False

        if not GameService.in_bounds(
            shot_col, shot_row, game.size
        ):  # Out of bounds shots
            return False

        shot_pos_player_tiles: list[TrainPlayerTile] = [
            pt for pt in board[(shot_col, shot_row)].player_tiles if pt.has_rail
        ]

        if len(shot_pos_player_tiles) >= 2:  # Tiles with too many players on them
            return False

        # Shots not adjacent to player's rail endpoint
        if abs(shot_col - base_coords[0]) + abs(shot_row - base_coords[1]) != 1:
            return False

        base_intersecting_player_id = None
        base_pos_player_tiles: list[TrainPlayerTile] = [
            pt for pt in board[base_coords].player_tiles if pt.has_rail
        ]

        for tile in (
            base_pos_player_tiles
        ):  # Shots that move along someone else's rails for more than 1 tile
            if tile.player_id != player.id:
                base_intersecting_player_id = tile.player_id

        if any(
            pt.player_id == base_intersecting_player_id for pt in shot_pos_player_tiles
        ):
            return False

        # Tiles that run next to your current rails

        test_coords = (
            (shot_col, shot_row + 1),
            (shot_col, shot_row - 1),
            (shot_col + 1, shot_row),
            (shot_col - 1, shot_row),
        )
        already_shot_coordinates = [
            (pt.column, pt.row) for pt in player.player_tiles if pt.has_rail
        ]

        for coord in test_coords:
            if (
                not GameService.in_bounds(coord[0], coord[1], game.size)
                or coord == base_coords
            ):
                continue
            elif coord in already_shot_coordinates:
                return False

        return True

    @staticmethod
    async def validate_and_cache_anilist_info(link, cache) -> int | None:
        show_id = al.anilist_id_from_url(url=link)
        if show_id is None:
            return None

        anilist_info = cache.get(show_id)
        if anilist_info is None:
            anilist_info = await al.query_media(media_id=show_id)
            cache[show_id] = anilist_info

        return show_id

    @staticmethod
    def update_stats_after_shot(
        game: TrainGame,
        player: TrainPlayer,
        shot: TrainShot,
    ):
        board = {tile.position: tile for tile in game.tiles}
        check_gem_time = False
        if board[shot.coords].resource == GameEmoji.GEMS.name:
            shot_list: list[TrainShot] = player.shots
            if GameEmoji.GEMS.name not in [
                board[shot.coords].resource for shot in shot_list
            ]:
                check_gem_time = True

        shot_player_tile: TrainPlayerTile = next(
            pt for pt in player.player_tiles if pt.position == shot.coords
        )

        shot_player_tile.has_rail = True

        if shot.coords == (player.end_col, player.end_row):
            player.done = True
            player.donetime = datetime.now(timezone.utc)

        if check_gem_time:
            player.score["GemTime"] = int(shot.time.timestamp())

        if board[shot.coords].terrain == "river":
            bridge: TrainItem | None = next(
                item.emoji_name == GameEmoji.BRIDGE.name and item.uses > 0
                for item in player.items
            )
            if bridge:
                rails = 0
                bridge.uses -= 1
            else:
                rails = 2
        else:
            rails = 1

        if board[shot.coords].zone in shot.genres:
            rails *= 0.5

        player.rails += rails

    @staticmethod
    async def get_player_item_counts(guild_id: int, discord_id: int, session: AsyncSession) -> Optional[dict[str, int]]:
        stmt = (
            select(TrainPlayer)
            .join(TrainPlayer.member)
            .join(TrainPlayer.game)
            .where(Member.guild_id == guild_id)
            .where(Member.user_id == discord_id)
            .where(TrainGame.active.is_(True))
            .options(selectinload(TrainPlayer.items))
        )
        result = await session.execute(stmt)
        player: Optional[TrainPlayer] = result.scalars().one_or_none()
        if player is None:
            return None

        inventory: list[TrainItem] = player.items
        item_counts = {}
        for item in inventory:
            item_counts.setdefault(item.emoji_name, 0)
            item_counts[item.emoji_name] += 1

        return item_counts

    @staticmethod
    async def inventory_string(items: dict[str, int]) -> str:
        return "\n".join(f"{GameEmoji[name].value}: x{count}" for name, count in items.items())


    def buy_item(self, itemname: str, showinfo: str, ctx: Interaction) -> bool:
        player_idx, player = self.get_player(ctx.user.id)
        if player is None or self.shop[itemname].amount < 1 or not player.shots:
            return True

        player_loc = (player.shots[-1].row, player.shots[-1].col)

        if self.board[player_loc].resource not in (
            GameEmoji.SHOP.name,
            GameEmoji.CITY.name,
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
                player.donetime = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
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

                if shot_tile.resource == GameEmoji.CITY.name:
                    has_city = True
                    if shot.coords() not in city_coords:
                        city_coords[shot.coords()] = choice(
                            ["SPRING", "SUMMER", "AUTUMN", "WINTER"]
                        )
                    if shot_anime_info["season"] == city_coords[shot.coords()]:
                        add_to_score(p=player, key="city season bonus", val=3)
                elif shot_tile.resource == GameEmoji.WHEAT.name:
                    add_to_score(p=player, key="wheat", val=1)

                elif shot_tile.resource == GameEmoji.WOOD.name:
                    add_to_score(p=player, key="wood", val=2)

                elif shot_tile.resource == GameEmoji.GEMS.name:
                    add_to_score(p=player, key="gems", val=2)

                elif shot_tile.resource == GameEmoji.HOUSE.name:
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


    @staticmethod
    async def delete_train_game(
        game: TrainGame, keep_files: bool, session: AsyncSession
    ) -> None:
        if keep_files:
            game.active = False
            await session.flush()
        else:
            await session.delete(game)