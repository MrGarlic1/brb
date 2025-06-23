import bot.Features.Help.data as hp
from discord import app_commands, Interaction
from discord.ext import commands


class Help(commands.Cog):
    @app_commands.command(
        name='help',
        description='View information about the bot\'s commands.'
    )
    async def help(self, ctx: Interaction):
        embed, components = hp.gen_help_embed(page=0)
        await ctx.response.send_message(embed=embed, view=hp.HelpView())
