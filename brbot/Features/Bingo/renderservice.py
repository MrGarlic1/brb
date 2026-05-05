import brbot.Core.botdata as bd
from io import BytesIO
from discord import File, Embed, Member as DiscordMember
from brbot.Features.Bingo.data import FrozenBingoPlayer
from brbot.Features.Bingo.data import BOARD_SIZE
from PIL import Image, ImageFont, ImageDraw
import logging

logger = logging.getLogger(__name__)


class BingoRenderService:
    def __init__(self):
        pass

    @staticmethod
    def draw_board_img(
        player: FrozenBingoPlayer,
        draw_tags: bool = False,
    ) -> BytesIO:
        # Generate board image. If player's own board: only generate tiles which are rendered.
        # Grey out other tiles.

        # Adjustments
        label_offset: int = 1
        label_font_size: int = 72
        font = ImageFont.truetype(
            f"{bd.parent}/Shared/ggsans/ggsans-Bold.ttf", label_font_size
        )
        tile_pixels: int = 150
        border_color: tuple[int, int, int] = (190, 190, 190)
        font_color: tuple[int, int, int] = (0, 0, 0)
        empty_color: tuple[int, int, int] = (255, 255, 255)
        hit_color: tuple[int, int, int] = (0, 255, 0)

        board_img = Image.new(
            mode="RGB",
            size=(
                (BOARD_SIZE + label_offset) * tile_pixels,
                (BOARD_SIZE + label_offset) * tile_pixels,
            ),
            color=0xFFFFFF,
        )
        draw: ImageDraw.ImageDraw = ImageDraw.Draw(board_img)

        base_col_labels = (
            ("B", "E", "N", "G", "O")
            if player.discord_user_id == 302266697488924672
            else ("B", "I", "N", "G", "O")
        )
        col_labels: list[str] = []
        for i in range(BOARD_SIZE):
            try:
                col_labels.append(base_col_labels[i])
            except IndexError:
                col_labels.append(str(i + 1))

        # Draw column labels/tile borders
        for label_x in range(1, BOARD_SIZE + 1):
            draw.rectangle(
                xy=(
                    (label_x * tile_pixels, 1),
                    ((label_x + 1) * tile_pixels, tile_pixels),
                ),
                fill=empty_color,
                outline=border_color,
                width=1,
            )
            draw.text(
                xy=(label_x * tile_pixels + tile_pixels / 2, tile_pixels / 2),
                text=col_labels[label_x - 1],
                font=font,
                anchor="mm",
                fill=font_color,
            )

        # Draw row labels/tile borders
        for label_y in range(1, BOARD_SIZE + 1):
            draw.rectangle(
                xy=(
                    (1, label_y * tile_pixels),
                    (tile_pixels, (label_y + 1) * tile_pixels),
                ),
                fill=empty_color,
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
        font = ImageFont.truetype(
            f"{bd.parent}/Shared/ggsans/ggsans-Bold.ttf", font_size
        )
        board = {tile.coordinates: tile for tile in player.tiles}

        for coordinates, tile in board.items():
            (col, row) = coordinates
            # Fill tiles with correct color, if empty, skip to next
            if tile.hit:
                draw.rectangle(
                    xy=(
                        (col * tile_pixels, row * tile_pixels),
                        ((col + 1) * tile_pixels, (row + 1) * tile_pixels),
                    ),
                    fill=hit_color,
                    outline=border_color,
                    width=1,
                )
            else:
                draw.rectangle(
                    xy=(
                        (col * tile_pixels, row * tile_pixels),
                        ((col + 1) * tile_pixels, (row + 1) * tile_pixels),
                    ),
                    fill=empty_color,
                    outline=border_color,
                    width=1,
                )

            text_pixels = draw.textlength(text=tile.tag, font=font)
            if tile.hit or draw_tags:
                while text_pixels > 0.8 * tile_pixels and font_size > 6:
                    font_size -= 2
                    font = ImageFont.truetype(
                        f"{bd.parent}/Shared/ggsans/ggsans-Bold.ttf", font_size
                    )
                    text_pixels = draw.textlength(text=tile.tag, font=font)

                # Draw tile resource and rails

                draw.text(
                    xy=(
                        col * tile_pixels + round(tile_pixels / 2),
                        row * tile_pixels + round(tile_pixels / 2),
                    ),
                    text=tile.tag,
                    anchor="mm",
                    fill=font_color,
                    font=font,
                )

                if font_size != default_font_size:
                    font_size = default_font_size
                    font = ImageFont.truetype(
                        f"{bd.parent}/Shared/ggsans/ggsans-Bold.ttf", font_size
                    )

        buffer = BytesIO()
        board_img.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    @staticmethod
    def gen_board_embed(
        players: list[FrozenBingoPlayer], discord_member: DiscordMember, page: int = 0
    ) -> tuple[Embed, File]:
        embed: Embed = Embed()
        embed.set_author(name="Anime Bingo", icon_url=bd.bot_avatar_url)

        player = players[page]

        page: int = 1 + (page % len(players))  # Loop back through pages both ways
        embed.set_footer(text=f"Page {page}/{len(players)}")

        # Player stats page
        if player.discord_user_id == discord_member.id:
            draw_tags = False
        else:
            draw_tags = True

        img_bytes: BytesIO = BingoRenderService.draw_board_img(
            player=player,
            draw_tags=draw_tags,
        )

        embed.set_thumbnail(url=discord_member.avatar.url)
        embed.description = f"### Board for {discord_member.mention}"

        if player.total_shots > 0:
            embed.add_field(
                name="\u200b",
                value=f"**Total Shots:** {player.total_shots}",
                inline=True,
            )
            embed.add_field(
                name="\u200b",
                value=f"**Accuracy:** {round(100 * player.total_hit_shots / player.total_shots, 2)}%",
                inline=True,
            )
        else:
            embed.add_field(name="\u200b", value="\u200b", inline=False)

        image = File(img_bytes, filename="bingo_board.png")

        embed.set_image(url="attachment://bingo_board.png")
        return embed, image
