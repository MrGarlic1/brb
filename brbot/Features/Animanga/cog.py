import brbot.Core.botdata as bd
from brbot.Features.Animanga.service import AnimangaService
from brbot.Features.Animanga.data import RecView, IgnoredRecView, MediaType
from brbot.Core.anilist import query_user_id
from brbot.Core.bot import BrBot
from brbot.db.models import User
from brbot.Shared.Users.repository import get_or_create_user
from httpx import RequestError
from discord import app_commands, Interaction
from discord.ext import commands
from sqlalchemy.exc import IntegrityError
import logging

logger = logging.getLogger(__name__)


class AnimangaCog(commands.GroupCog, name="animanga"):
    def __init__(self, bot: BrBot):
        self.animanga_service = AnimangaService()
        self.bot = bot

    @app_commands.command(
        name="link", description="Link your discord profile to an anilist profile"
    )
    @app_commands.describe(username="Anilist username")
    async def link(self, ctx: Interaction, username: str):
        async with self.bot.session_generator() as session:
            user: User = await get_or_create_user(ctx.user.id, ctx.user.name, session)

            if username is None:
                await ctx.response.send_message(
                    content="Could not find anilist profile, please check username!"
                )
                return True
            anilist_user_id = await query_user_id(username)
            if anilist_user_id is None:
                await ctx.response.send_message(
                    content="Could not find anilist profile, please check username!"
                )
                return True

            user.anilist_id = anilist_user_id
            user.anilist_username = username
            user.rec_timestamp_manga = None
            user.rec_timestamp_anime = None

            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                await ctx.response.send_message(
                    content="A transient error occurred, please try again!"
                )

        logger.debug(
            f"Linked discord user {ctx.user.name} to anilist profile {username}"
        )
        await ctx.response.send_message(content=bd.pass_str)
        return False

    @app_commands.command(
        name="recommend", description="Have the bot recommend anime/manga for you."
    )
    @app_commands.describe(
        genre="Request recommendation(s) of a specific genre.",
        medium="Choose to recommend anime/manga",
        force="Force updates anilist stats. WILL BE SLOW.",
    )
    @app_commands.choices(
        genre=[
            app_commands.Choice(name="Action", value="Action"),
            app_commands.Choice(name="Adventure", value="Adventure"),
            app_commands.Choice(name="Comedy", value="Comedy"),
            app_commands.Choice(name="Drama", value="Drama"),
            app_commands.Choice(name="Ecchi", value="Ecchi"),
            app_commands.Choice(name="Fantasy", value="Fantasy"),
            app_commands.Choice(name="Horror", value="Horror"),
            app_commands.Choice(name="Mahou Shoujo", value="Mahou Shoujo"),
            app_commands.Choice(name="Mecha", value="Mecha"),
            app_commands.Choice(name="Music", value="Music"),
            app_commands.Choice(name="Mystery", value="Mystery"),
            app_commands.Choice(name="Psychological", value="Psychological"),
            app_commands.Choice(name="Romance", value="Romance"),
            app_commands.Choice(name="Sci-Fi", value="Sci-Fi"),
            app_commands.Choice(name="Slice of Life", value="Slice of Life"),
            app_commands.Choice(name="Sports", value="Sports"),
            app_commands.Choice(name="Supernatural", value="Supernatural"),
            app_commands.Choice(name="Thriller", value="Thriller"),
        ],
        medium=[
            app_commands.Choice(name="Anime", value=MediaType.Anime.name),
            app_commands.Choice(name="Manga", value=MediaType.Manga.name),
        ],
    )
    async def show_animanga_rec(
        self,
        ctx: Interaction,
        genre: str = "",
        medium: str = MediaType.Anime.name,
        force: bool = False,
    ):
        async with self.bot.session_generator() as session:
            user = await get_or_create_user(ctx.user.id, ctx.user.name, session)
            user_anilist_id = user.anilist_id
            anilist_username = user.anilist_username
            if user_anilist_id is None:
                await ctx.response.send_message(
                    content="Your anilist profile isn't linked! (/animanga link)"
                )
                return True

            medium: MediaType = (
                MediaType.Anime if medium == MediaType.Anime.name else MediaType.Manga
            )
            await ctx.response.defer()

            try:
                await self.animanga_service.check_or_update_recommendation_cache(
                    user=user,
                    media_type=medium,
                    session=session,
                    force_update=force,
                )
            except RequestError:
                await ctx.followup.send(
                    "An error occurred connecting to Anilist. Please try again later."
                )
                return True

            embed, media_id = await self.animanga_service.gen_rec_embed_page(
                anilist_user_id=user_anilist_id,
                anilist_username=anilist_username,
                media_type=medium,
                genre=genre,
                page=0,
                session=session,
            )
        view = RecView(
            animanga_service=self.animanga_service,
            user_id=user.user_id,
            anilist_user_id=user_anilist_id,
            anilist_username=anilist_username,
            media_type=medium,
            genre=genre,
            current_media_id=media_id,
            session_generator=self.bot.session_generator,
        )
        await ctx.followup.send(embed=embed, view=view)
        return False

    @app_commands.command(
        name="listignored", description="Show your ignored animanga recommendations."
    )
    @app_commands.describe(
        medium="Specify ignored anime or manga (defaults to anime)",
    )
    @app_commands.choices(
        medium=[
            app_commands.Choice(name="Anime", value=MediaType.Anime.name),
            app_commands.Choice(name="Manga", value=MediaType.Manga.name),
        ],
    )
    async def list_ignored(self, ctx: Interaction, medium: str = MediaType.Anime.name):
        async with self.bot.session_generator() as session:
            user = await get_or_create_user(ctx.user.id, ctx.user.name, session)
            if user.anilist_id is None:
                await ctx.response.send_message(
                    content="Your anilist profile isn't linked! (/animanga link)"
                )
                return True

        medium: MediaType = (
            MediaType.Anime if medium == MediaType.Anime.name else MediaType.Manga
        )

        await ctx.response.defer()
        async with self.bot.session_generator() as session:
            (
                embed,
                ignored_media_id,
            ) = await self.animanga_service.get_ignored_rec_embed_page(
                username=ctx.user.name,
                user_discord_id=ctx.user.id,
                page=0,
                session=session,
                media_type=medium,
            )
        view = IgnoredRecView(
            animanga_service=self.animanga_service,
            user_id=ctx.user.id,
            media_type=medium,
            discord_username=ctx.user.name,
            current_media_id=ignored_media_id,
            session_generator=self.bot.session_generator,
        )
        await ctx.followup.send(embed=embed, view=view)
        return False


async def setup(bot: BrBot):
    await bot.add_cog(AnimangaCog(bot))
