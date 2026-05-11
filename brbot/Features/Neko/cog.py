from brbot.Core.bot import BrBot
from discord import app_commands, Interaction, Embed, HTTPException
from brbot.Features.Neko.service import NekoService
from brbot.Features.Neko.data import NEKO_COLORS, NekoRarity, NekoView
from brbot.Core.botdata import DEV_SERVER_ID, fail_str
from discord.ext import commands
from datetime import datetime
import logging
from random import choice

logger = logging.getLogger(__name__)


class NekoCog(commands.GroupCog, name="neko"):
    def __init__(self, bot: BrBot):
        self.neko_service = NekoService()
        self.bot = bot
        self.current_hour = datetime.now().hour

    @app_commands.command(
        name="pic",
        description="Send a picture of a random catgirl",
    )
    async def neko(self, ctx: Interaction):
        await self.run_neko(ctx)

    async def run_neko(self, interaction: Interaction):
        await interaction.response.defer()

        enable_nsfw = self.bot.guild_configs[interaction.guild.id].enable_nsfw
        if enable_nsfw and not interaction.channel.is_nsfw():
            await interaction.followup.send(
                content="⛔Since NSFW content is enabled, this command is restricted to NSFW channels.\n"
                "To turn off NSFW content, a server admin can use `/config set ENABLE_NSFW False`"
            )
            return

        remaining_rolls = await self.neko_service.check_remaining_hourly_rolls(
            interaction.guild.id, interaction.user.id
        )

        if remaining_rolls < 1 and interaction.guild.id != DEV_SERVER_ID:
            embed = Embed(title="⛔⛔ NOT Neko")
            embed.set_image(
                url=choice(
                    [
                        "https://media.tenor.com/mkucT-12lYwAAAAi/clash-royale-king-angry.gif",
                        "https://i.imgur.com/YD1cOub.png",
                    ]
                )
            )
            embed.set_footer(text="NOT Powered by Mr.Garlic. Wait a bit next time.")
            await interaction.followup.send(embed=embed)
            return

        rarity: NekoRarity = self.neko_service.roll_rarity()
        if rarity == NekoRarity.NONE:
            await interaction.followup.send(content=fail_str)
            return

        async with self.bot.session_generator() as session:
            neko_url, source_url = await self.neko_service.roll_and_get_neko_info(
                include_nsfw=enable_nsfw,
                rarity=rarity,
                session=session,
            )

        remaining_rolls -= 1

        rarity_str = (
            "✨🌟✨"
            if rarity == NekoRarity.SS
            else "⭐" * (rarity.value if rarity.value is not None else 0)
        )
        if source_url:
            rarity_str += "  •  Source"

        footer_text = "Powered by Mr.Garlic"
        if remaining_rolls <= 2:
            footer_text += f"  •  {remaining_rolls} remaining."

        embed = Embed(title="Neko🐱🖼️")
        embed.set_author(name=rarity_str, url=source_url)
        embed.colour = NEKO_COLORS[rarity]
        embed.set_image(url=neko_url)
        embed.set_footer(text=footer_text)

        try:
            await interaction.followup.send(embed=embed, view=NekoView(self))
        except HTTPException:
            logger.warning(f"Could not send image: URL {neko_url}")
            await interaction.followup.send(content=fail_str)

        self.neko_service.guild_user_hourly_rolls[interaction.guild.id][
            interaction.user.id
        ] -= 1


async def setup(bot: BrBot):
    await bot.add_cog(NekoCog(bot))
