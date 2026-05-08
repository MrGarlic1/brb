import brbot.Features.Help.data as hp
from brbot.Core.bot import BrBot
from brbot.Core.botdata import bot_avatar_url
from discord import app_commands, Interaction, Embed
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

    @app_commands.command(name="about", description="Information about the bot")
    async def about(self, ctx: Interaction):
        embed = Embed(title="Response Bot", description="Statistics")
        embed.set_author(
            name=f"Requested by {ctx.user.mention}", icon_url=ctx.user.avatar.url
        )
        embed.add_field(
            name="\u200b", value=f"Currently in **{len(self.bot.guilds)}** guilds"
        )
        embed.add_field(
            name="\u200b", value=f"Latency: {(1000 * self.bot.latency):.1f} ms"
        )
        embed.set_thumbnail(url=bot_avatar_url)
        embed.set_footer(
            text="Response Bot is open source. View the source code at https://github.com/MrGarlic1/brb"
        )
        await ctx.response.send_message(embed=embed)


async def setup(bot: BrBot):
    await bot.add_cog(HelpCog(bot))
