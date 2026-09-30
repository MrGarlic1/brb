import logging
from discord.ui import View, Button
from discord import Interaction, ButtonStyle
from brbot.Shared.Neko.models import NekoRarity
from sqlalchemy.ext.asyncio import async_sessionmaker
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from brbot.Features.Admin.service import AdminService


logger = logging.getLogger(__name__)


class NekoClassificationInfo:
    def __init__(
        self,
        neko_id: int,
        image_url: str,
        rarity: NekoRarity,
        nsfw: Optional[bool] = None,
    ):
        self.neko_id = neko_id
        self.image_url = image_url
        self.rarity = rarity
        self.nsfw = nsfw


class ConfirmButton(Button):
    def __init__(self):
        super().__init__(
            style=ButtonStyle.success,
            label="Confirm",
            custom_id="confirm_changes",
        )

    async def callback(self, ctx: Interaction):
        view: NekoAdminView = self.view

        async with view.session_generator() as session:
            await view.admin_service.update_neko(view.neko, session)

            if (
                view.neko.rarity == view.original_neko.rarity
                and view.neko.nsfw == view.original_neko.nsfw
            ):
                view.offset += 1

            view.remaining_count -= 1

            view.neko = await view.admin_service.get_neko_classification_info(
                rarity=view.original_neko.rarity,
                nsfw=view.original_neko.nsfw,
                session=session,
                offset=view.offset,
            )
        await view.render(ctx)


class SetRarityButton(Button):
    def __init__(self, rarity: NekoRarity):
        super().__init__(style=ButtonStyle.secondary, label=rarity.name)
        self.rarity = rarity

    async def callback(self, ctx: Interaction):
        view: NekoAdminView = self.view
        view.neko.rarity = self.rarity
        await view.render(ctx)


class ToggleNsfwButton(Button):
    def __init__(self):
        super().__init__(
            style=ButtonStyle.secondary,
            emoji="⛔",
            label="Toggle NSFW",
            custom_id="toggle_nsfw",
        )

    async def callback(self, ctx: Interaction):
        view: NekoAdminView = self.view
        view.neko.nsfw = True if view.neko.nsfw is None else not view.neko.nsfw
        await view.render(ctx)


class NotNekoButton(Button):
    def __init__(self):
        super().__init__(
            style=ButtonStyle.danger, label="Delete", custom_id="delete_neko"
        )

    async def callback(self, ctx: Interaction):
        view: NekoAdminView = self.view
        async with view.session_generator() as session:
            await view.admin_service.delete_neko(view.neko, session)

            view.neko = await view.admin_service.get_neko_classification_info(
                rarity=view.original_neko.rarity,
                nsfw=view.original_neko.nsfw,
                session=session,
                offset=view.offset,
            )
        view.remaining_count -= 1
        await view.render(ctx)


class NekoAdminView(View):
    """
    Discord UI View for handling animanga recommendation interactions.

    Attributes:
        admin_service (AdminService): Admin service
        neko (NekoClassificationInfo): DB-decoupled Classification information object for neko
        session_generator (async_sessionmaker): bot DB session factory
    """

    def __init__(
        self,
        admin_service: AdminService,
        neko: NekoClassificationInfo,
        original_neko: NekoClassificationInfo,
        remaining_count: int,
        session_generator: async_sessionmaker,
    ):
        super().__init__(timeout=300)
        self.admin_service = admin_service
        self.session_generator = session_generator
        self.add_item(NotNekoButton())
        self.add_item(ToggleNsfwButton())
        self.add_item(SetRarityButton(rarity=NekoRarity.B))
        self.add_item(SetRarityButton(rarity=NekoRarity.A))
        self.add_item(SetRarityButton(rarity=NekoRarity.S))
        self.add_item(SetRarityButton(rarity=NekoRarity.SS))
        self.add_item(ConfirmButton())
        self.neko = neko
        self.original_neko = original_neko
        self.offset = 0
        self.remaining_count = remaining_count

    async def render(self, interaction: Interaction):
        embed = await self.admin_service.gen_neko_classification_embed(
            self.neko,
            self.remaining_count,
        )
        await interaction.response.edit_message(embed=embed, view=self)
