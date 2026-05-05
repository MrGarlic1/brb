from brbot.Core.bot import BrBot
from discord import app_commands, Interaction, Embed
from brbot.Features.Neko.data import neko_urls
from discord.ext import commands
from random import choice
import logging

logger = logging.getLogger(__name__)


## Nuke this entire class later; temp feature
class NekoCog(commands.GroupCog, name="neko"):
    def __init__(self, bot: BrBot):
        # self.neko_service = NekoService()
        self.bot = bot
        self.last_userid_by_guild: dict[int, int] = {}

    @app_commands.command(
        name="pic",
        description="Send a picture of a random catgirl",
    )
    async def neko(self, ctx: Interaction):
        if (
            self.bot.guild_configs[ctx.guild.id].enable_nsfw
            and not ctx.channel.is_nsfw()
        ):
            await ctx.response.send_message(
                content="⛔Since NSFW content is enabled, this command is restricted to NSFW channels.\n"
                "To turn off NSFW content, a server admin can use `/config set ENABLE_NSFW False`"
            )
            return
        if ctx.user.id == self.last_userid_by_guild.get(ctx.guild.id):
            embed = Embed(title="⛔⛔ NOT Neko")
            embed.set_image(url="https://i.imgur.com/YD1cOub.png")
            embed.set_footer(
                text="NOT Provided by Mr.Garlic. Wait your turn next time."
            )
        else:
            embed = Embed(title="🖼️🐱Neko")
            embed.set_image(url=choice(neko_urls))
            self.last_userid_by_guild[ctx.guild.id] = ctx.user.id
            embed.set_footer(text="Provided by Mr.Garlic")

        await ctx.response.send_message(embed=embed)


async def setup(bot: BrBot):
    await bot.add_cog(NekoCog(bot))
