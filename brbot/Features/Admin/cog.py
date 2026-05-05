from discord import app_commands, Interaction, Attachment
from brbot.Core.botdata import pass_str
from brbot.Features.Admin.service import AdminService
from brbot.Features.Admin.data import NekoAdminView
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
        await ctx.response.send_message(content=pass_str)

    @app_commands.command(
        name="classify_nekos",
        description="Categorize un-classified images within the Neko DB.",
    )
    async def classify_neko_images(self, ctx: Interaction):
        async with self.bot.session_generator() as session:
            remaining_count = await self.admin_service.get_remaining_neko_count(session)
            neko_info = await self.admin_service.get_neko_classification_info(session)
            embed = await self.admin_service.gen_neko_classification_embed(
                neko_info, remaining_count
            )
            if neko_info is None:
                await ctx.response.send_message(embed=embed)
                return

        view = NekoAdminView(
            admin_service=self.admin_service,
            neko=neko_info,
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

        await ctx.response.send_message(content=pass_str)


async def setup(bot: BrBot):
    if getenv("DEV_SERVER_ID") is None:
        logger.warning(
            "DEV_SERVER_ID missing/invalid in .env, loading of development cog skipped."
        )
        return
    await bot.add_cog(AdminCog(bot))
