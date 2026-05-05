import brbot.Shared.Anilist.anilist as al
import brbot.Core.botdata as bd
from datetime import datetime
from discord import Interaction, Message
from brbot.Features.Bingo.data import ShotType
from brbot.Features.Bingo.data import (
    character_tags,
    season_tags,
    bingo_tags,
    episode_tags,
    BingoMode,
    BOARD_SIZE,
)
from brbot.Shared.Users.repository import get_or_create_users
from brbot.Shared.Members.repository import get_or_create_members
from brbot.db.models import BingoTile, BingoPlayer, BingoGame, BingoShot
from random import sample
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from typing import Sequence
import logging

logger = logging.getLogger(__name__)


class BingoGameService:
    def __init__(self):
        pass

    ## SHOT METHODS

    @staticmethod
    def get_shot_type(shot_tag: str) -> ShotType:
        if shot_tag in character_tags:
            return ShotType.CHARACTER
        elif shot_tag in episode_tags:
            return ShotType.EPISODE
        elif shot_tag == "Source Not Manga":
            return ShotType.SOURCE
        elif shot_tag in season_tags:
            return ShotType.SEASON
        elif shot_tag == "Gloppy":
            return ShotType.FREE
        elif shot_tag == "Rewatch an Anime":
            return ShotType.REWATCH
        elif shot_tag == "Not TV":
            return ShotType.NOT_TV
        elif shot_tag == "95%":
            return ShotType.NINETY_FIVE_PERCENT
        elif shot_tag in bingo_tags:
            return ShotType.TAG
        else:
            return ShotType.OTHER

    @staticmethod
    async def is_shot_valid(
        shot_anilist_id,
        shot_tag,
        player_starting_anilist: dict,
        shot_anilist_info: dict,
        poll_msg: Message = None,
    ) -> bool:
        shot_type = BingoGameService.get_shot_type(shot_tag)
        if shot_type == "not_tv":
            return shot_anilist_info["format"] != "TV"
        if shot_type == "free":
            return True
        if shot_type == "source":
            return shot_anilist_info["source"] != "MANGA"
        if shot_type == "season":
            return shot_tag.upper() == shot_anilist_info["season"]
        if shot_type == "95%":
            return any(tag["rank"] > 95 for tag in shot_anilist_info["tags"])
        if shot_type == "tag":
            return any(
                tag["name"].upper() == shot_tag.upper() and tag["rank"] > 40
                for tag in shot_anilist_info["tags"]
            ) or any(
                genre.upper() == shot_tag.upper()
                for genre in shot_anilist_info["genres"]
            )
        if shot_type == "character":
            yes_votes = 1
            no_votes = 1
            for reaction in poll_msg.reactions:
                if reaction.emoji == bd.upvote_emoji:
                    yes_votes = reaction.count
                elif reaction.emoji == bd.downvote_emoji:
                    no_votes = reaction.count

            return yes_votes / (no_votes + yes_votes) > 0.5
        if shot_type == "rewatch":
            for show in player_starting_anilist:
                if show["mediaId"] != shot_anilist_id:
                    continue
                if show["status"] in ("REWATCHING", "COMPLETED"):
                    return True
            return False
        if shot_type == "episode":
            return (
                episode_tags[shot_tag][0]
                <= shot_anilist_info["episodes"]
                <= episode_tags[shot_tag][1]
            )
        return False

    # GAME METHODS

    @staticmethod
    async def create_bingo_game(
        guild_id: int,
        name: str,
        discord_ids: list[int],
        discord_usernames: list[str],
        session_generator: async_sessionmaker,
        mode: BingoMode = BingoMode.STANDARD,
    ) -> str | None:
        async with session_generator() as session:
            users = await get_or_create_users(discord_ids, discord_usernames, session)

            for u in users:
                if u.anilist_id is None:
                    return f"Could not create game, {u.mention_str} must link their anilist profile! (/animanga link)"

            members = await get_or_create_members(discord_ids, guild_id, session)
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
                f"Could not find anilist information for players(s) in guild {guild_id}, aborting game creation: {e}"
            )
            return "Error connecting to anilist, please try again later."

        async with session_generator() as session:
            game = BingoGame(
                name=name,
                active=True,
                guild_id=guild_id,
                date=datetime.now(),
                mode=mode,
            )
            session.add(game)
            await session.flush()

            for discord_id in anilist_id_by_discord_id.keys():
                player = BingoPlayer(
                    game_id=game.id,
                    member_id=member_ids_by_discord_id[discord_id],
                    starting_anilist=anilist_info_by_discord_id[discord_id],
                    done=False,
                )
                await BingoGameService.generate_player_tiles(player, game.id)
                game.players.append(player)

            await session.commit()

        return None

    @staticmethod
    def game_is_done(game: BingoGame) -> bool:
        done = False
        for player in game.players:
            if player.done:
                done = True
                break
        return done

    @staticmethod
    def update_game_after_shot(
        game: BingoGame,
        ctx: Interaction,
        shot: BingoShot,
        player_idx: int,
        hit_tile: tuple[int, int] = None,
    ) -> None:
        # Push updates to player boards, check if game is finished
        """
        if self.active:
            bd.active_bingos[ctx.guild_id] = self
        else:
            del bd.active_bingos[ctx.guild_id]

        self.players[player_idx].shots.append(shot)
        if hit_tile:
            self.players[player_idx].board[hit_tile].hit = True

        self.save_game(f"{bd.parent}/Guilds/{ctx.guild_id}/Bingo/{self.name}")
        """
        return None

    @staticmethod
    async def generate_player_tiles(player: BingoPlayer, game_id: int) -> None:
        selected_tags = sample(bingo_tags, k=BOARD_SIZE**2)

        for col in range(1, BOARD_SIZE + 1):
            for row in range(1, BOARD_SIZE + 1):
                tile = BingoTile(
                    game_id=game_id,
                    row=row,
                    column=col,
                    tag=selected_tags[0],
                    hit=False,
                )
                player.tiles.append(tile)
                del selected_tags[0]
        return None

    @staticmethod
    def has_bingo(player_board: list[BingoTile], mode: BingoMode) -> bool:
        tiles_by_coordinate = {tile.coordinates: tile for tile in player_board}

        row_bingos = {i: [] for i in range(1, BOARD_SIZE + 1)}

        for col in range(1, BOARD_SIZE + 1):
            col_bingo = []
            for row in range(1, BOARD_SIZE + 1):
                if tiles_by_coordinate[(col, row)].hit:
                    col_bingo.append((col, row))
                    row_bingos[row].append((col, row))
                    if (
                        len(row_bingos[row]) == BOARD_SIZE
                        or len(col_bingo) == BOARD_SIZE
                    ):
                        return True

        # Check diagonal bingos
        diagonal_tiles_hit = [
            tiles_by_coordinate[i, i].hit for i in range(1, BOARD_SIZE + 1)
        ]
        if all(diagonal_tiles_hit):
            return True
        diagonal_tiles_hit = [
            tiles_by_coordinate[i, BOARD_SIZE + 1 - i].hit
            for i in range(1, BOARD_SIZE + 1)
        ]
        if all(diagonal_tiles_hit):
            return True
        return False

    # PLAYER METHODS

    @staticmethod
    async def find_tag_in_board(
        game_id: int, player_id: int, tag, session: AsyncSession
    ) -> int | None:
        """
        Finds a tag within a player's bingo tiles for a given game.
        Args:
            game_id: bingo game id
            player_id: bingo player id
            tag: bingo tile tag
            session: sqlalchemy async session
        Returns:
            Tile ID of hit tile, or None if tag is not on the board.
        """
        stmt = (
            select(BingoTile)
            .where(BingoTile.game_id == game_id)
            .where(BingoTile.player_id == player_id)
        )
        result = await session.execute(stmt)
        player_tiles: Sequence[BingoTile] = result.scalars().all()

        for tile in player_tiles:
            if tile.tag == tag:
                return tile.id
        return None
