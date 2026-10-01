from brbot.Core.bot import BrBot
from brbot.Features.Mtg.data import PlaygroupKeyModal
from brbot.Features.Mtg.service import PlaygroupService
from discord import app_commands, Interaction
from discord.ext import commands
import logging

logger = logging.getLogger(__name__)


class MtgCog(commands.GroupCog, name="playgroup"):
    def __init__(self, bot: BrBot):
        self.bot = bot
        self.playgroup_service = PlaygroupService(
            async_session_generator=self.bot.session_generator
        )

    @app_commands.command(
        name="link", description="Link your discord profile to a playgroup account"
    )
    async def link(self, ctx: Interaction):
        await ctx.response.send_modal(PlaygroupKeyModal(self.playgroup_service))


async def setup(bot: BrBot):
    await bot.add_cog(MtgCog(bot))
