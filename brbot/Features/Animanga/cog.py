import brbot.Core.botdata as bd
from brbot.Features.Animanga.recservice import RecommendationService
from brbot.Features.Animanga.statservice import AnimangaStatService
from brbot.Features.Animanga.data import (
    RecView,
    IgnoredRecView,
    MediaType,
    DAILY_UPDATE_HOUR_UTC,
)
from brbot.Shared.Anilist.anilist import query_user_id
from brbot.Core.bot import BrBot
from brbot.Shared.Members.repository import get_or_create_member
from brbot.db.models import User, Member, AnimangaListEntry
from brbot.Shared.Users.repository import get_or_create_user
from httpx import RequestError
from datetime import datetime, timezone, time
from discord import app_commands, Interaction
from discord.ext import commands, tasks
from sqlalchemy.exc import IntegrityError
from sqlalchemy import delete, insert
import logging

logger = logging.getLogger(__name__)


class AnimangaCog(commands.GroupCog, name="animanga"):
    def __init__(self, bot: BrBot):
        self.rec_service = RecommendationService()
        self.stat_service = AnimangaStatService()
        self.bot = bot
        self.send_daily_stat_update.start()

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
                return

            medium: MediaType = (
                MediaType.Anime if medium == MediaType.Anime.name else MediaType.Manga
            )
            await ctx.response.defer()

            try:
                await self.rec_service.check_or_update_recommendation_cache(
                    user=user,
                    media_type=medium,
                    session=session,
                    force_update=force,
                )
            except RequestError:
                await ctx.followup.send(
                    "An error occurred connecting to Anilist. Please try again later."
                )
                return

            embed, media_id = await self.rec_service.gen_rec_embed_page(
                anilist_user_id=user_anilist_id,
                anilist_username=anilist_username,
                media_type=medium,
                genre=genre,
                page=0,
                session=session,
            )
        view = RecView(
            rec_service=self.rec_service,
            user_id=user.user_id,
            anilist_user_id=user_anilist_id,
            anilist_username=anilist_username,
            media_type=medium,
            genre=genre,
            current_media_id=media_id,
            session_generator=self.bot.session_generator,
        )
        await ctx.followup.send(embed=embed, view=view)
        return

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
            ) = await self.rec_service.get_ignored_rec_embed_page(
                username=ctx.user.name,
                user_discord_id=ctx.user.id,
                page=0,
                session=session,
                media_type=medium,
            )
        view = IgnoredRecView(
            rec_service=self.rec_service,
            user_id=ctx.user.id,
            media_type=medium,
            discord_username=ctx.user.name,
            current_media_id=ignored_media_id,
            session_generator=self.bot.session_generator,
        )
        await ctx.followup.send(embed=embed, view=view)
        return False

    @app_commands.command(
        name="track_daily",
        description="Add yourself to Anilist stat tracking for the daily leaderboard.",
    )
    async def add_tracking(self, ctx: Interaction):
        await ctx.response.defer()

        async with self.bot.session_generator() as session:
            user: User = await get_or_create_user(ctx.user.id, ctx.user.name, session)

            if user.anilist_id is None:
                await ctx.followup.send(
                    content="Your anilist profile isn't linked! (/animanga link)"
                )
                return

            user_id = user.user_id
            anilist_id = user.anilist_id

        initial_list_entries = await self.stat_service.get_user_list_entries(
            user_id, anilist_id
        )

        if initial_list_entries is None:
            await ctx.followup.send(
                "An error occurred connecting to Anilist. Please try again later."
            )
            return

        async with self.bot.session_generator() as session:
            stmt = (
                insert(AnimangaListEntry)
                .values(initial_list_entries)
                .prefix_with("OR IGNORE")
            )
            await session.execute(stmt)

            member: Member = await get_or_create_member(
                ctx.user.id, ctx.guild.id, session
            )
            if member.stat_tracking_enabled:
                await ctx.followup.send("Stat tracking is already enabled.")
                return
            member.stat_tracking_enabled = True
            await session.commit()
            logger.info(
                f"Added tracking for user {ctx.user.name} in guild {ctx.guild.id}"
            )

        await ctx.followup.send(content=bd.pass_str)
        if self.bot.guild_configs[ctx.guild.id].update_channel is None:
            await ctx.channel.send(
                content="An update channel currently isn't set! Leaderboards won't be sent. "
                "To set a server update channel, an admin must run /config set update_channel."
            )
        return

    @app_commands.command(
        name="untrack_daily",
        description="Remove yourself from Anilist stat tracking for the daily leaderboard.",
    )
    async def remove_tracking(self, ctx: Interaction):
        async with self.bot.session_generator() as session:
            member: Member = await get_or_create_member(
                ctx.user.id, ctx.guild.id, session
            )

            if not member.stat_tracking_enabled:
                await ctx.response.send_message(
                    content="Stat tracking is already disabled!"
                )
                return
            member.stat_tracking_enabled = False
            stmt = delete(AnimangaListEntry).where(
                AnimangaListEntry.user_id == ctx.user.id
            )
            await session.execute(stmt)
            await session.commit()

        await ctx.response.send_message(content=bd.pass_str)
        return

    @app_commands.command(
        name="get_stats", description="View your historic daily leaderboard statistics."
    )
    async def get_stats(self, ctx: Interaction):
        await ctx.response.defer()

        async with self.bot.session_generator() as session:
            member: Member = await get_or_create_member(
                user_id=ctx.user.id, guild_id=ctx.guild.id, session=session
            )
            guild_leaderboard_stats = await self.stat_service.get_leaderboard_stats(
                member, session
            )

        embed = self.stat_service.create_leaderboard_stats_embed(
            member=ctx.user,
            guild=ctx.guild,
            guild_leaderboard_stats=guild_leaderboard_stats,
        )
        await ctx.followup.send(embed=embed)

    @tasks.loop(time=time(hour=DAILY_UPDATE_HOUR_UTC, tzinfo=timezone.utc))
    async def send_daily_stat_update(self):
        logger.info(f"Sending daily stat updates to {len(self.bot.guilds)} guilds.")
        for guild in self.bot.guilds:
            if self.bot.guild_configs[guild.id].update_channel is None:
                continue
            channel = self.bot.get_channel(
                self.bot.guild_configs[guild.id].update_channel
            )
            if channel is None:
                logger.warning(f"Update channel not found for guild {guild.id}")
                continue
            try:
                daily_stats = await self.stat_service.process_daily_activities(
                    guild_id=guild.id, session_generator=self.bot.session_generator
                )
                if daily_stats is None:
                    continue

                leaderboard_embed = await self.stat_service.create_leaderboard_embed(
                    guild, datetime.now(timezone.utc), daily_stats
                )
                await channel.send(embed=leaderboard_embed)
            except Exception as e:
                logger.warning(
                    f"Failed to send daily stats leaderboard in guild {guild.id}: {e}"
                )


async def setup(bot: BrBot):
    await bot.add_cog(AnimangaCog(bot))
