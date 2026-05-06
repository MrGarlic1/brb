from brbot.Core.bot import BrBot
from discord import app_commands, Interaction, Embed
from brbot.Features.Neko.service import NekoService
from brbot.Features.Neko.data import NEKO_COLORS, NekoRarity
from discord.ext import commands
import logging

logger = logging.getLogger(__name__)


class NekoCog(commands.GroupCog, name="neko"):
    def __init__(self, bot: BrBot):
        self.neko_service = NekoService()
        self.bot = bot
        self.last_userid_by_guild: dict[int, int] = {}

    @app_commands.command(
        name="pic",
        description="Send a picture of a random catgirl",
    )
    async def neko(self, ctx: Interaction):
        await ctx.defer()
        enable_nsfw = self.bot.guild_configs[ctx.guild.id].enable_nsfw
        if enable_nsfw and not ctx.channel.is_nsfw():
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
            rarity = self.neko_service.roll_rarity()
            rarity_int: int = rarity.value

            async with self.bot.session_generator() as session:
                neko_url, source_url = await self.neko_service.roll_and_get_neko_info(
                    include_nsfw=enable_nsfw, rarity=rarity, session=session
                )
            rarity_str = "✨🌟✨" if rarity == NekoRarity.SS else "⭐" * rarity_int

            embed = Embed(title="Neko🐱🖼️")
            embed.set_author(name=rarity_str)
            embed.colour = NEKO_COLORS[rarity]
            embed.set_image(url=neko_url)
            self.last_userid_by_guild[ctx.guild.id] = ctx.user.id
            source_link = f" | ([Source]({source_url}))" if source_url else ""
            embed.set_footer(text=f"Provided by Mr.Garlic{source_link}")

        await ctx.followup.send_message(embed=embed)


async def setup(bot: BrBot):
    await bot.add_cog(NekoCog(bot))
