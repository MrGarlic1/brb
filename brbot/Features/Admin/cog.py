from discord import app_commands, Interaction, Attachment
from brbot.Core.botdata import pass_str
from brbot.Features.Admin.service import AdminService
from brbot.Features.Admin.data import NekoAdminView
from brbot.Shared.Neko.models import NekoRarity
from copy import deepcopy
from brbot.db.models import Neko
from sqlalchemy import insert
from discord.ext import commands
import logging
from json import loads
from os import getenv

from brbot.Core.bot import BrBot

logger = logging.getLogger(__name__)


@app_commands.guilds(int(getenv("DEV_SERVER_ID")))
class AdminCog(commands.GroupCog, name="admin"):
    def __init__(self, bot: BrBot):
        self.admin_service = AdminService()
        self.bot = bot

    @app_commands.command(name="sync", description="Syncs the bot's command tree.")
    async def tree_sync(self, ctx: Interaction) -> None:
        await self.bot.tree.sync()
        for guild in self.bot.guilds:
            await self.bot.tree.sync(guild=guild)
        await ctx.response.send_message(content=pass_str)

    @app_commands.command(
        name="classify_nekos",
        description="Categorize un-classified images within the Neko DB.",
    )
    @app_commands.choices(
        rarity=[
            app_commands.Choice(name=NekoRarity.SS.name, value=NekoRarity.SS.value),
            app_commands.Choice(name=NekoRarity.S.name, value=NekoRarity.S.value),
            app_commands.Choice(name=NekoRarity.A.name, value=NekoRarity.A.value),
            app_commands.Choice(name=NekoRarity.B.name, value=NekoRarity.B.value),
        ],
    )
    async def classify_neko_images(
        self, ctx: Interaction, rarity: int = None, nsfw: bool = None
    ):
        rarity = NekoRarity(rarity)
        async with self.bot.session_generator() as session:
            remaining_count = await self.admin_service.get_remaining_neko_count(
                rarity, session, nsfw
            )
            neko_info = await self.admin_service.get_neko_classification_info(
                rarity, session, nsfw
            )
            embed = await self.admin_service.gen_neko_classification_embed(
                neko_info, remaining_count
            )
            if neko_info is None:
                await ctx.response.send_message(embed=embed)
                return

        view = NekoAdminView(
            admin_service=self.admin_service,
            neko=neko_info,
            original_neko=deepcopy(neko_info),
            session_generator=self.bot.session_generator,
            remaining_count=remaining_count,
        )
        await ctx.response.send_message(embed=embed, view=view)

    @app_commands.command(
        name="add_nekos",
        description="Add new images to the Neko DB from a json array file.",
    )
    async def add_nekos(self, ctx: Interaction, file: Attachment) -> None:
        try:
            data = await file.read()  # bytes
            json_str = data.decode("utf-8")
            json_payload = loads(json_str)
        except Exception as e:
            logger.warning(f"Failed to decode file: {e}")
            await ctx.response.send_message(f"Failed to decode file: {e}")
            return

        entries = []
        for entry in json_payload:
            if "image_url" not in entry:
                continue
            if "source" not in entry:
                entry["source"] = None
            entries.append({"image_url": entry["image_url"], "source": entry["source"]})

        async with self.bot.session_generator() as session:
            stmt = insert(Neko).values(entries).prefix_with("OR IGNORE")
            await session.execute(stmt)
            await session.commit()

        logger.info(f"Successfully processed {len(entries)} neko entries to add to DB.")

        await ctx.response.send_message(content=pass_str)


async def setup(bot: BrBot):
    if getenv("DEV_SERVER_ID") is None:
        logger.warning(
            "DEV_SERVER_ID missing/invalid in .env, loading of development cog skipped."
        )
        return
    await bot.add_cog(AdminCog(bot))
