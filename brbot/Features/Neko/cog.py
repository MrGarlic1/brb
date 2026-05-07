from brbot.Core.bot import BrBot
from discord import app_commands, Interaction, Embed
from brbot.Features.Neko.service import NekoService
from brbot.Features.Neko.data import NEKO_COLORS, NekoRarity
from brbot.Core.botdata import DEV_SERVER_ID
from discord.ext import commands
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class NekoCog(commands.GroupCog, name="neko"):
    def __init__(self, bot: BrBot):
        self.neko_service = NekoService()
        self.bot = bot
        self.last_userid_by_guild: dict[int, int] = {}
        self.current_hour = datetime.now().hour

    @app_commands.command(
        name="pic",
        description="Send a picture of a random catgirl",
    )
    async def neko(self, ctx: Interaction):
        await ctx.response.defer()

        enable_nsfw = self.bot.guild_configs[ctx.guild.id].enable_nsfw
        if enable_nsfw and not ctx.channel.is_nsfw():
            await ctx.followup.send(
                content="⛔Since NSFW content is enabled, this command is restricted to NSFW channels.\n"
                "To turn off NSFW content, a server admin can use `/config set ENABLE_NSFW False`"
            )
            return

        remaining_rolls = await self.neko_service.check_remaining_hourly_rolls(
            ctx.guild.id, ctx.user.id
        )
        if remaining_rolls < 1:
            embed = Embed(title="⛔⛔ NOT Neko")
            embed.set_image(
                url="https://media.tenor.com/mkucT-12lYwAAAAi/clash-royale-king-angry.gif"
            )
            embed.set_footer(
                text="NOT Powered by Mr.Garlic. Wait a bit next time.",
            )
            await ctx.followup.send(embed=embed)
            return

        if (
            ctx.user.id == self.last_userid_by_guild.get(ctx.guild.id)
            and not ctx.guild.id == DEV_SERVER_ID
        ):
            embed = Embed(title="⛔⛔ NOT Neko")
            embed.set_image(url="https://i.imgur.com/YD1cOub.png")
            embed.set_footer(
                text="NOT Powered by Mr.Garlic. Wait your turn next time.",
            )
            await ctx.followup.send(embed=embed)
            return

        rarity = self.neko_service.roll_rarity()
        rarity_int: int = rarity.value

        async with self.bot.session_generator() as session:
            neko_url, source_url = await self.neko_service.roll_and_get_neko_info(
                include_nsfw=enable_nsfw, rarity=rarity, session=session
            )
        self.neko_service.guild_user_hourly_rolls[ctx.guild.id][ctx.user.id] -= 1
        remaining_rolls -= 1

        rarity_str = "✨🌟✨" if rarity == NekoRarity.SS else "⭐" * rarity_int
        if source_url:
            rarity_str += "  •  Source"

        footer_text = "Powered by Mr.Garlic"
        if remaining_rolls <= 2:
            footer_text += f"  •  {remaining_rolls} remaining."

        embed = Embed(title="Neko🐱🖼️")
        embed.set_author(name=f"{rarity_str}", url=source_url)
        embed.colour = NEKO_COLORS[rarity]
        embed.set_image(url=neko_url)
        self.last_userid_by_guild[ctx.guild.id] = ctx.user.id
        embed.set_footer(text=footer_text)

        await ctx.followup.send(embed=embed)


async def setup(bot: BrBot):
    await bot.add_cog(NekoCog(bot))
