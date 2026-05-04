from brbot.Core.bot import BrBot
from discord import app_commands, Interaction, Embed
from brbot.Features.Neko.data import neko_urls
from discord.ext import commands
from random import choice
import logging

logger = logging.getLogger(__name__)


class NekoCog(commands.GroupCog, name="neko"):
    def __init__(self, bot: BrBot):
        # self.neko_service = NekoService()
        self.bot = bot

    @app_commands.command(
        name="pic",
        description="Send a picture of a random catgirl",
    )
    async def neko(self, ctx: Interaction):
        embed = Embed(title="🖼️🐱Neko")
        embed.set_image(url=choice(neko_urls))
        embed.set_footer(text="Provided by Mr.Garlic")

        await ctx.response.send_message(embed=embed)


async def setup(bot: BrBot):
    await bot.add_cog(NekoCog(bot))
