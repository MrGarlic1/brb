import brbot.Features.Help.data as hp
from discord import app_commands, Interaction
from discord.ext import commands


class HelpCog(commands.Cog):
    @app_commands.command(
        name="help", description="View information about the bot's commands."
    )
    async def help(self, ctx: Interaction):
        embed = hp.gen_help_embed(category="general")
        await ctx.response.send_message(embed=embed, view=hp.HelpView())


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
