import logging

import discord
from asyncio import Lock
from discord import Intents, CustomActivity, Status
from discord import Guild as DiscordGuild
from discord.ext import commands
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select
from os import makedirs

from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

from brbot.db.models import Base, GuildConfig, Response, Guild
from brbot.Core.botutils import load_fonts
from brbot.Shared.Responses.models import CachedResponse
from brbot.Shared.GuildConfig.models import CachedGuildConfig
from typing import Sequence
import brbot.Core.botdata as bd

logger = logging.getLogger(__name__)


class BrBot(commands.AutoShardedBot):
    """
    Discord bot class with improved structure and error handling
    """

    def __init__(self) -> None:
        self.session_generator = None
        self.session_generator: async_sessionmaker[AsyncSession]
        self.locks: dict[int, Lock] = {}
        self.responses: dict[int, list[CachedResponse]] = {}
        self.mentions: dict[int, list[CachedResponse]] = {}
        self.guild_configs: dict[int, CachedGuildConfig] = {}
        intents = Intents.default()
        intents.message_content = True
        self.engine = None

        super().__init__(
            command_prefix="asid%%*@@]][}{}{112asd",  # Prefix commands not used
            intents=intents,
            help_command=None,
        )

    async def load_cogs(self) -> None:
        """
        Load all cog extensions from the features directory
        Handles errors for individual cog loading
        """
        if not bd.FEATURES_DIRECTORY.exists():
            logger.error(f"Features directory not found: {bd.FEATURES_DIRECTORY}")
            return

        for feature_dir in bd.FEATURES_DIRECTORY.iterdir():
            if not feature_dir.is_dir():
                continue

            cog_file = feature_dir / "cog.py"
            if not cog_file.exists():
                continue

            try:
                cog_path = f"brbot.Features.{feature_dir.name}.cog"
                await self.load_extension(cog_path)
                logger.info(f"Loaded feature: {feature_dir.name} ({cog_path})")
            except Exception as e:
                logger.error(f"Failed to load feature {feature_dir.name}: {str(e)}")

    async def load_db(self) -> None:
        if not bd.DATA_DIRECTORY.exists():
            logger.warning(
                f"Data directory not found at {bd.DATA_DIRECTORY}, initialized new."
            )
            makedirs(bd.DATA_DIRECTORY, exist_ok=True)

        # IF CHANGED, ALSO CHANGE IN alembic.ini
        self.engine = create_async_engine(
            f"sqlite+aiosqlite:///{bd.DATA_DIRECTORY / 'brb.db'}", echo=False
        )
        self.session_generator = async_sessionmaker(self.engine, expire_on_commit=False)

        async with self.engine.connect() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def init_guilds(self) -> None:
        """
        Validates guilds + configs against DB. Loads guild responses and configs into cache.
        Returns:
            None
        """

        # Validate/guilds + configs
        guild_ids = [guild.id for guild in self.guilds]
        stmt = (
            select(Guild)
            .where(Guild.id.in_(guild_ids))
            .options(selectinload(Guild.config))
        )

        async with self.session_generator() as session:
            result = await session.execute(stmt)

            existing_guilds = {g.id: g for g in result.scalars().all()}
            new_guilds: list[Guild] = []

            for guild in self.guilds:
                if guild.id not in existing_guilds:
                    logger.warning(
                        f"Guild {guild.name} does not exist in DB; creating default"
                    )
                    new_guild = Guild(id=guild.id, config=bd.default_config(guild.id))
                    session.add(new_guild)
                    new_guilds.append(new_guild)
                    existing_guilds[new_guild.id] = new_guild

            await session.commit()

        # Validate and cache configs

        async with self.session_generator() as session:
            new_configs: list[GuildConfig] = []
            for g_id, guild in existing_guilds.items():
                if guild.config is None:
                    logger.warning(
                        f"Guild config missing for guild {guild.id}; using default config"
                    )
                    new_config = bd.default_config(guild.id)
                    session.add(new_config)
                    new_configs.append(new_config)
                    self.guild_configs[guild.id] = CachedGuildConfig(
                        allow_phrases=new_config.allow_phrases,
                        limit_user_responses=new_config.limit_user_responses,
                        restrict_response_deletion=new_config.restrict_response_deletion,
                        max_user_responses=new_config.max_user_responses,
                    )
                else:
                    self.guild_configs[guild.id] = CachedGuildConfig(
                        allow_phrases=guild.config.allow_phrases,
                        limit_user_responses=guild.config.limit_user_responses,
                        restrict_response_deletion=guild.config.restrict_response_deletion,
                        max_user_responses=guild.config.max_user_responses,
                    )

            if new_guilds or new_configs:
                await session.commit()

        # Load responses

        for guild_id in guild_ids:
            self.responses.setdefault(guild_id, [])
            self.mentions.setdefault(guild_id, [])

        stmt = select(Response).where(Response.guild_id.in_(guild_ids))
        async with self.session_generator() as session:
            result = await session.execute(stmt)

        response_list: Sequence[Response] = result.scalars().all()
        for response in response_list:
            if response.is_exact:
                self.responses.setdefault(response.guild_id, []).append(
                    CachedResponse(
                        trigger=response.trigger,
                        text=response.text,
                        exact=response.is_exact,
                        member_id=response.member_id,
                    )
                )
            else:
                self.mentions.setdefault(response.guild_id, []).append(
                    CachedResponse(
                        trigger=response.trigger,
                        text=response.text,
                        exact=response.is_exact,
                        member_id=response.member_id,
                    )
                )

        logger.info(f"Loaded {len(response_list)} responses")

    async def setup_new_guild(self, discord_guild: DiscordGuild) -> None:
        """
        Creates default guild and corresponding config when a guild is joined
        Args:
            discord_guild: Guild that has been joined
        Returns:
            None
        """

        stmt = (
            select(Guild)
            .where(Guild.id == discord_guild.id)
            .options(selectinload(Guild.config))
        )

        async with await self.session_generator() as session:
            result = await session.execute(stmt)
            guild = result.scalar_one_or_none()
            modified = False

            if not guild:
                guild = Guild(id=discord_guild.id)
                session.add(guild)
                modified = True

            if not guild.config:
                new_config = bd.default_config(discord_guild.id)
                session.add(new_config)
                modified = True

            if modified:
                try:
                    await session.commit()
                except IntegrityError as e:
                    logger.warning(
                        f"Error when registering new guild, changes rolled back: {e}"
                    )
                    await session.rollback()

        return None

    async def setup_hook(self) -> None:
        """
        Setup hook called before the bot starts
        """
        await self.load_db()
        await self.load_cogs()

    async def on_ready(self) -> None:
        """
        Called when the bot has successfully connected to Discord
        """
        try:
            assert self.session_generator is not None
        except AssertionError:
            await self.load_db()

        logger.info(f"Logged in as {self.user.name}")
        logger.info(f"Bot is in {len(self.guilds)} guilds")

        for guild in self.guilds:
            self.locks[guild.id] = Lock()

        if self.user.avatar:
            bd.bot_avatar_url = self.user.avatar.url
        else:
            logger.warning("No bot avatar found, using default")
            bd.bot_avatar_url = "https://i.imgur.com/4CW85RL.png"
        bd.bot_id = self.user.id
        # await self.tree.sync()

        load_fonts(f"{bd.parent}/Shared")

        await self.init_guilds()

        await self.change_presence(
            status=Status.online, activity=CustomActivity(name="Responding since 2020")
        )

    async def on_guild_join(self, guild: discord.Guild) -> None:
        try:
            assert self.session_generator is not None
        except AssertionError:
            await self.load_db()

        await self.setup_new_guild(guild)

    async def on_error(self, event: str, *args, **kwargs) -> None:
        """
        Global error handler for the bot

        Args:
            event: The name of the event that raised the error
            args: Positional arguments that were passed to the event
            kwargs: Keyword arguments that were passed to the event
        """
        logger.error(f"Error in event {event}")
        if args:
            logger.error(f"Event args: {args}")
        if kwargs:
            logger.error(f"Event kwargs: {kwargs}")
        logger.error("Full traceback:", exc_info=True)
