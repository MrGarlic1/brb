import logging
from pathlib import Path

from discord import Intents, CustomActivity, Status
from discord.ext import commands
from brbot.Core.botutils import init_guilds, load_fonts, load_anilist_caches
import brbot.Core.botdata as bd

logger = logging.getLogger(__name__)


class BrBot(commands.AutoShardedBot):
    """
    Discord bot class with improved structure and error handling
    """

    FEATURES_DIRECTORY = Path("brbot/Features")

    def __init__(self) -> None:
        intents = Intents.default()
        intents.message_content = True
        intents.members = True

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
        if not self.FEATURES_DIRECTORY.exists():
            logger.error(f"Features directory not found: {self.FEATURES_DIRECTORY}")
            return

        for feature_dir in self.FEATURES_DIRECTORY.iterdir():
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

    async def setup_hook(self) -> None:
        """
        Setup hook called before the bot starts
        """
        await self.load_cogs()

    async def on_ready(self) -> None:
        """
        Called when the bot has successfully connected to Discord
        """
        logger.info(f"Logged in as {self.user.name}")
        logger.info(f"Bot is in {len(self.guilds)} guilds")
        if bd.bot_avatar_url:
            bd.bot_avatar_url = self.user.avatar.url
        else:
            bd.bot_avatar_url = "https://i.imgur.com/4CW85RL.png"
        bd.bot_id = self.user.id
        # await self.tree.sync()

        load_anilist_caches()
        load_fonts(f"{bd.parent}/Shared")

        await init_guilds(guilds=self.guilds)
        await self.change_presence(
            status=Status.online, activity=CustomActivity(name="Responding since 2020")
        )

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
