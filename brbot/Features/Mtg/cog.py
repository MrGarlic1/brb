from brbot.Core.bot import BrBot
from brbot.Core.botdata import pass_str, DAILY_UPDATE_HOUR_UTC
from brbot.Features.Mtg.data import PlaygroupKeyModal
from brbot.Features.Mtg.service import PlaygroupService
from datetime import time, timezone
from discord import app_commands, Interaction
from discord.ext import commands, tasks
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

    @app_commands.command(
        name="unlink", description="Unlink your discord profile from playgroup"
    )
    async def unlink(self, ctx: Interaction):
        await self.playgroup_service.remove_api_key(ctx.user)
        await ctx.response.send_message(content=pass_str)

    @tasks.loop(time=time(hour=DAILY_UPDATE_HOUR_UTC, tzinfo=timezone.utc))
    async def send_daily_stat_update(self):
        logger.info(
            f"Sending daily mtg playgroup updates to {len(self.bot.guilds)} guilds."
        )
        for guild in self.bot.guilds:
            if self.bot.guild_configs[guild.id].mtg_channel is None:
                continue
            if self.bot.guild_configs[guild.id].tracked_playgroup_id is None:
                continue
            channel = self.bot.get_channel(self.bot.guild_configs[guild.id].mtg_channel)
            if channel is None:
                logger.warning(f"Update channel not found for guild {guild.id}")
                continue
            try:
                # daily_stats = await self.playgroup_service.get_daily_playgroup_games(
                #   guild_id=guild.id
                # )
                pass
                # leaderboard_embed = await self.stat_service.create_leaderboard_embed(
                #    guild, datetime.now(timezone.utc), daily_stats
                # )
                # await channel.send(embed=leaderboard_embed)
            except Exception as e:
                logger.exception(
                    f"Failed to send daily stats leaderboard in guild {guild.id}: {e}"
                )


async def setup(bot: BrBot):
    await bot.add_cog(MtgCog(bot))
