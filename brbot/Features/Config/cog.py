import brbot.Core.botdata as bd
import json
from discord import app_commands, Interaction
from discord.ext import commands
import logging

logger = logging.getLogger(__name__)

config_keys = {
    "Allow Phrase-Based Responses": "ALLOW_PHRASES",
    "Limit # of User Responses": "LIMIT_USER_RESPONSES",
    "Maximum # of User Responses": "MAX_USER_RESPONSES",
    "Restrict Response Deletion": "USER_ONLY_DELETE",
}


class ConfigCog(commands.GroupCog, name='config'):
    @app_commands.command(
        name='set',
        description='Configure the bot\'s server settings (admin only)'
    )
    @app_commands.choices(
        setting=[
            app_commands.Choice(name=config_key, value=config_key) for config_key in config_keys.keys()
        ]
    )
    async def set(self, ctx: Interaction, setting: str, value: str):
        if not ctx.user.guild_permissions.administrator:
            await ctx.response.send_message(content="You must be an administrator to use this command!", ephemeral=True)
            return True

        if setting not in config_keys:
            await ctx.response.send_message(content=bd.fail_str)
            return True

        config_key = config_keys[setting]
        try:
            if config_key == "MAX_USER_RESPONSES":
                value = int(value)
                if value < 1 or value > 999999:
                    raise ValueError
            else:
                value = bool(value)
        except ValueError:
            await ctx.response.send_message(content=bd.fail_str)
            return True

        logger.info(f"Set key {config_key} to {value} for guild {ctx.guild.name}")
        bd.config[ctx.guild_id][config_key] = value
        with open(f"{bd.parent}/Guilds/{ctx.guild_id}/config.json", "w") as f:
            json.dump(bd.config[ctx.guild_id], f, indent=4)
        await ctx.response.send_message(content=bd.pass_str)
        return False

    @set.autocomplete("value")
    async def value_autocomplete(self, ctx: Interaction, _: str):
        setting = ctx.namespace["setting"]
        if setting not in config_keys:
            choices = []
        elif config_keys[setting] == "MAX_USER_RESPONSES":
            choices = [app_commands.Choice(name="Please enter a positive integer", value="None")]
        else:
            choices = [app_commands.Choice(name="True", value="True"), app_commands.Choice(name="False", value="")]
        return choices

    @app_commands.command(
        name='wipe',
        description='Resets ALL server settings to default. (admin only)'
    )
    async def wipe(self, ctx: Interaction):
        if not ctx.user.guild_permissions.administrator:
            await ctx.response.send_message(content="You must be an administrator to use this command!", ephemeral=True)
            return True
        with open(f"{bd.parent}/Guilds/{ctx.guild_id}/config.json", "w") as f:
            json.dump(bd.default_config, f, indent=4)
        bd.config[ctx.guild_id] = bd.default_config
        logger.info(f"Reset config for guild {ctx.guild.name}")
        await ctx.response.send_message(content=bd.pass_str)
        return False

    @app_commands.command(
        name='view',
        description='Views the current server settings.'
    )
    async def view(self, ctx: Interaction):
        await ctx.response.send_message(
            content=f"Allow Phrases: {bd.config[ctx.guild_id]['ALLOW_PHRASES']}\n"
                    f"Limit Responses: {bd.config[ctx.guild_id]['LIMIT_USER_RESPONSES']}\n"
                    f"Response Limit # (Only if Limit Responses is True): "
                    f"{bd.config[ctx.guild_id]['MAX_USER_RESPONSES']}\n"
                    f"Restrict User Response Deleting: {bd.config[ctx.guild_id]['USER_ONLY_DELETE']}\n"
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ConfigCog(bot))
