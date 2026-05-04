from discord import app_commands, Interaction
from brbot.Features.Config.service import ConfigService
from brbot.Features.Config.data import ConfigKeys
from brbot.Core.botdata import fail_str, pass_str
from discord.ext import commands
import logging

from brbot.Core.bot import BrBot

logger = logging.getLogger(__name__)


class ConfigCog(commands.GroupCog, name="config"):
    def __init__(self, bot: BrBot):
        self.config_service = ConfigService(bot.guild_configs)
        self.bot = bot

    @app_commands.command(
        name="set", description="Configure the bot's server settings (admin only)"
    )
    @app_commands.choices(
        setting=[
            app_commands.Choice(name=config_key.value, value=config_key.value)
            for config_key in ConfigKeys
        ]
    )
    async def set(self, ctx: Interaction, setting: ConfigKeys, value: str) -> None:
        try:
            if value == "true":
                value = 1
            elif value == "false":
                value = 0
            else:
                value = int(value)
        except ValueError:
            await ctx.response.send_message(content=fail_str)
            return

        if not ctx.user.guild_permissions.administrator:
            await ctx.response.send_message(
                content="You must be an administrator to use this command!",
                ephemeral=True,
            )
            return
        if setting not in ConfigKeys:
            await ctx.response.send_message(content=fail_str)
            return

        async with self.bot.locks[ctx.guild.id]:
            async with self.bot.session_generator() as session:
                await self.config_service.set_config(
                    ctx.guild.id, setting, value, session
                )

        await ctx.response.send_message(content=pass_str)
        return

    @set.autocomplete("value")
    async def value_autocomplete(self, ctx: Interaction, _: str):
        setting = ctx.namespace["setting"]

        if setting not in [k.value for k in ConfigKeys.__members__.values()]:
            choices = []
        elif setting == ConfigKeys.MAX_USER_RESPONSES.value:
            choices = [
                app_commands.Choice(
                    name="Please enter a positive integer", value="false"
                )
            ]
        else:
            choices = [
                app_commands.Choice(name="True", value="true"),
                app_commands.Choice(name="False", value="false"),
            ]
        return choices

    @app_commands.command(
        name="wipe", description="Resets ALL server settings to default. (admin only)"
    )
    async def wipe(self, ctx: Interaction):
        if not ctx.user.guild_permissions.administrator:
            await ctx.response.send_message(
                content="You must be an administrator to use this command!",
                ephemeral=True,
            )
            return
        async with self.bot.locks[ctx.guild_id]:
            async with self.bot.session_generator() as session:
                error = await self.config_service.wipe_config(ctx.guild_id, session)

        if error:
            await ctx.response.send_message(
                content=fail_str,
                ephemeral=True,
            )
        else:
            await ctx.response.send_message(content=pass_str)

    @app_commands.command(name="view", description="Views the current server settings.")
    async def view(self, ctx: Interaction):
        await ctx.response.send_message(
            content=f"Allow Phrases: {self.bot.guild_configs[ctx.guild_id].allow_phrases}\n"
            f"Limit Responses: {self.bot.guild_configs[ctx.guild_id].limit_user_responses}\n"
            f"Response Limit # (Only if Limit Responses is True): "
            f"{self.bot.guild_configs[ctx.guild_id].max_user_responses}\n"
            f"Restrict User Response Deleting: {self.bot.guild_configs[ctx.guild_id].restrict_response_deletion}\n"
        )


async def setup(bot: BrBot):
    await bot.add_cog(ConfigCog(bot))
