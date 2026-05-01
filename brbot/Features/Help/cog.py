import brbot.Features.Help.data as hp
from brbot.Core.bot import BrBot
from discord import app_commands, Interaction
from discord.ext import commands


class HelpCog(commands.Cog):
    def __init__(self, bot: BrBot):
        self.bot = bot

    @app_commands.command(
        name="help", description="View information about the bot's commands."
    )
    async def help(self, ctx: Interaction):
        embed = hp.gen_help_embed(category="general")
        await ctx.response.send_message(embed=embed, view=hp.HelpView())


async def setup(bot: BrBot):
    await bot.add_cog(HelpCog(bot))
