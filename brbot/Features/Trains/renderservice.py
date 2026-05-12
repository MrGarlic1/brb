import asyncio
import io
from datetime import datetime, timedelta, timezone
from math import log
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
    Guild as DiscordGuild,
    Member as DiscordMember,
)
from typing import Optional
from brbot.db.models import (
    TrainTile,
    TrainPlayer,
    TrainGame,
)
import brbot.Core.botdata as bd
from brbot.Features.Trains.data import GameEmoji, genre_colors

logger = logging.getLogger(__name__)


class RenderService:
    def __init__(self):
        pass

    @staticmethod
    async def push_player_update(guild: DiscordGuild, game: TrainGame, p: TrainPlayer):
        if p.dmchannel is None:
            member = await guild.fetch_member(p.member.user_id)
            dm = await member.create_dm()
            p.dmchannel = dm

        board = {(tile.column, tile.row): tile for tile in game.tiles}
        img = RenderService.draw_board_img(
            game_width=game.board_width,
            game_height=game.board_height,
            board=board,
            player=p,
        )
        await p.dmchannel.send(
            file=File(img, filename="train_board.png"),
            content=f'## Train board update for "{game.name}" in {guild.name}!',
        )

    @staticmethod
    async def send_updates_after_shot(
        game: TrainGame, guild: DiscordGuild, column: int, row: int
    ) -> None:
        # Push updates to player boards
        tasks: list = []
        for player_idx, player in enumerate(game.players):
            vis_tiles = [pt.position for pt in player.player_tiles]
            if (column, row) in vis_tiles:
                logger.debug(
                    f"Sending board update with shot ({row}, {column}) to "
                    f"{player.member.user_id} for game {game.name} in {guild.name}"
                )
                tasks.append(
                    asyncio.create_task(
                        RenderService.push_player_update(guild, game, player)
                    )
                )
        await asyncio.gather(*tasks)
        return None

    @staticmethod
    async def send_updates_after_create(game: TrainGame, guild: DiscordGuild) -> None:
        tasks: list = []
        for player in game.players:
            logger.debug(
                f"Sending initial board to "
                f"{player.member.user_id} for game {game.name} in {guild.name}"
            )
            tasks.append(
                asyncio.create_task(
                    RenderService.push_player_update(guild, game, player)
                )
            )
        await asyncio.gather(*tasks)
        return None

    @staticmethod
    async def gen_stats_embed(
        game: TrainGame, ctx: Interaction, page: int = 0, game_done: bool = False
    ) -> tuple[Embed, Union[None, File]]:
        embed: Embed = Embed()
        embed.set_author(name="Anime Trains", icon_url=bd.bot_avatar_url)

        max_pages: int = len(game.players) + 1
        page: int = 1 + (page % max_pages)  # Loop back through pages both ways
        embed.set_footer(text=f"Page {page}/{max_pages}")

        # Game stats page
        if page == 1:
            return RenderService._render_game_stats(embed, game, ctx, game_done)
        # Player stats page
        player_idx: int = page - 2
        player_discord_member = await ctx.guild.fetch_member(game.players[player_idx].member.user_id)
        return RenderService._render_player_stats(embed, game, player_idx, player_discord_member)


    @staticmethod
    def _render_game_stats(embed: Embed, game: TrainGame, ctx: Interaction, game_done: bool):
        resource_count: dict = {}
        claimed_resource_count: dict = {}
        rail_count: int = 0
        intersection_count: int = 0
        board = {tile.position: tile for tile in game.tiles}

        player_tile_board = {}
        for tile in game.tiles:
            tile_rails = [pt for pt in tile.player_tiles if pt.has_rail]
            player_tile_board[tile.position] = tile_rails

        for coord, tile in board.items():
            if tile.resource:
                try:
                    resource_count[tile.resource] += 1
                except KeyError:
                    resource_count[tile.resource] = 1

            if player_tile_board[coord]:
                rail_count += len(player_tile_board[coord])
                if tile.resource:
                    try:
                        claimed_resource_count[tile.resource] += 1
                    except KeyError:
                        claimed_resource_count[tile.resource] = 1
                if len(player_tile_board[coord]) > 1:
                    intersection_count += 1

        embed.title = "Game Stats"
        embed.description = f"*{game.name}*\n\u200b"
        embed.set_thumbnail(url=ctx.guild.icon.url)
        embed.add_field(
            name="🚂 Active?", value="✅" if game.active else "❌", inline=True
        )

        embed.add_field(
            name="🚂 Complete?", value="✅" if game_done else "❌", inline=True
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

        if game_done:
            img_bytes = RenderService.draw_board_img(
                game_width=game.board_width,
                game_height=game.board_height,
                board=board,
            )
            image = File(img_bytes, filename="bingo_board.png")

            embed.set_image(url="attachment://bingo_board.png")
            return embed, image
        else:
            return embed, None


    @staticmethod
    def _render_player_stats(embed: Embed, game: TrainGame, player_idx: int, discord_member: DiscordMember):
        player: TrainPlayer = game.players[player_idx]
        board = {tile.position: tile for tile in game.tiles}

        embed.set_thumbnail(url=discord_member.avatar.url)
        embed.description = f"### Stats for {discord_member.mention}"
        embed.add_field(name="\u200b", value="\u200b", inline=False)

        if len(player.shots) == 0:
            embed.description = (
                f"### {discord_member.mention} has not placed any rails yet!"
            )
            return embed, None

        # Total shots/in-zone shots
        total_shots: int = len(player.shots)
        in_zone_shots: int = 0
        prev_shot_time = game.date
        time_between_shots_list = []
        weights = []

        # Get time deltas for all previous shots and current time, take weighted average
        for shot_idx, shot in enumerate(player.shots):
            if board[shot.coords()].zone in shot.genres:
                in_zone_shots += 1
            time_between_shots_list.append((shot.time - prev_shot_time).total_seconds())
            # Weight based on seconds elapsed since shot. Time delta minimum is 300
            weights.append(
                log(
                    0.01
                    * max(
                        (datetime.now(timezone.utc) - prev_shot_time).total_seconds(),
                        300,
                    )
                )
                ** -0.9
            )
            prev_shot_time = shot.time

        time_between_shots_list.append(
            (datetime.now(timezone.utc) - prev_shot_time).total_seconds()
        )
        weights.append(
            log((datetime.now(timezone.utc) - prev_shot_time).total_seconds()) ** -1
        )
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
            projected_time = (
                player.donetime
                if player.donetime is not None
                else datetime.now(timezone.utc)
            )
            projected_time = projected_time.strftime("%Y/%m/%d at %H:%M:%S")
        else:
            last_shot = player.shots[-1]
            dist_left = abs(last_shot.col - player.end_col) + abs(
                last_shot.row - player.end_row
            )
            weighted_time_deltas = [
                t * w for t, w in zip(time_between_shots_list, weights)
            ]
            weighted_avg_secs_between_shots = sum(weighted_time_deltas) / sum(weights)
            projected_time = datetime.now(timezone.utc) + timedelta(
                seconds=round(dist_left * 1.5) * weighted_avg_secs_between_shots
            )
            projected_time = projected_time.strftime("%Y/%m/%d at %H:%M:%S")

        embed.add_field(
            name="🗓️ Projected Completion Date", value=projected_time, inline=False
        )

        # Shot genre pie chart

        genre_counts: dict[str, int] = {}
        for shot in game.players[player_idx].shots:
            for genre in shot.genres:
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
        buff = io.BytesIO()
        plt.savefig(buff, transparent=True)
        plt.close(fig)
        buff.seek(0)
        image = File(buff, filename="stats_img.png")

        embed.set_image(url="attachment://stats_img.png")
        return embed, image

    @staticmethod
    def draw_board_img(
        game_width: int,
        game_height: int,
        board: dict[tuple[int, int], TrainTile],
        player: Optional[TrainPlayer] = None,
    ) -> BytesIO:
        # Generate board image. If player board: only generate tiles which are rendered.
        # Grey out other tiles.
        if player:
            player_start = (player.start_col, player.start_row)
            player_end = (player.end_col, player.end_row)
            vis_tiles = {(tile.column, tile.row): tile for tile in player.player_tiles}
            hide_hidden_tiles = True
        else:
            player_start = None
            player_end = None
            vis_tiles = []
            hide_hidden_tiles = False

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
        draw = ImageDraw.Draw(board_img)
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
            (col, row) = coords

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

            resource_text = (
                GameEmoji[board[coords].resource].value
                if board[coords].resource
                else ""
            )

            # Draw start/end text
            if coords == player_start and not vis_tiles[coords].has_rail:
                rail_text = "Start"
            elif coords == player_end and not vis_tiles[coords].has_rail:
                rail_text = "End"
            else:
                rail_text = (
                    vis_tiles[coords].rail_text if vis_tiles[coords].rail_text else ""
                )
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
                        f"{bd.STATIC_DIRECTORY}/ggsans/ggsans-Bold.ttf", font_size
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
                        f"{bd.STATIC_DIRECTORY}/ggsans/ggsans-Bold.ttf", font_size
                    )

        buffer = BytesIO()
        board_img.save(buffer, format="png")
        buffer.seek(0)
        return buffer

    @staticmethod
    def gen_score_embed(
        game: TrainGame, page: int = 0
    ) -> tuple[Embed, Union[None, File]]:
        embed = Embed()

        max_pages: int = len(game.players) + 1
        page: int = 1 + (page % max_pages)  # Loop back through pages both ways
        embed.set_footer(text=f"Page {page}/{max_pages}")
        embed.set_author(name="Anime Trains", icon_url=bd.bot_avatar_url)
        embed.colour = 0xFF9C2C

        players = game.players.sort(key=lambda p: p.score["total"], reverse=True)

        if page == 1:
            embed.title = "Game Complete!"
            embed.description = "*Scoring results are as follows...*"
            for idx, player in enumerate(players):
                place_emojis = {
                    0: GameEmoji.FIRST.value,
                    1: GameEmoji.SECOND.value,
                    2: GameEmoji.THIRD.value,
                }
                place_emoji = place_emojis.get(idx, "")
                embed.add_field(
                    name="\u200b",
                    value=f"{place_emoji} {player.member.mention}'s score is **{player.score['total']}**",
                    inline=False,
                )

            img_bytes = RenderService.draw_board_img(
                game_width=game.board_width,
                game_height=game.board_height,
                board={tile.position: tile for tile in game.tiles},
            )

            image = File(img_bytes, filename="MASTER.png")
            embed.set_image(url="attachment://MASTER.png")
            return embed, image

        player_idx: int = page - 2
        embed.set_thumbnail(url=players[player_idx].member.avatar.url)
        embed.title = f"{players[player_idx].member.name}"
        for category, score in players[player_idx].score.items():
            embed.add_field(name=category.title(), value=score)

        return embed, None
