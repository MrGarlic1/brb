import logging
from discord.ui import View, Button
from discord import Interaction, ButtonStyle
from enum import Enum
from sqlalchemy.ext.asyncio import async_sessionmaker
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from brbot.Features.Admin.service import AdminService


logger = logging.getLogger(__name__)


class NekoRarity(Enum):
    S = 5  # 0xFFF27A
    A = 4  # 0xC666E3
    B = 3  # 0x3B49D1


class NekoClassificationInfo:
    def __init__(self, neko_id: int, image_url: str, rarity: NekoRarity, is_nsfw: bool):
        self.neko_id = neko_id
        self.image_url = image_url
        self.rarity = rarity
        self.is_nsfw = is_nsfw


class ConfirmButton(Button):
    def __init__(self):
        super().__init__(
            style=ButtonStyle.success,
            label="Confirm",
            custom_id="confirm_changes",
        )


class SRarityButton(Button):
    def __init__(self):
        super().__init__(
            style=ButtonStyle.secondary, label=NekoRarity.S.name, custom_id="s_rank"
        )


class ARarityButton(Button):
    def __init__(self):
        super().__init__(
            style=ButtonStyle.secondary, label=NekoRarity.A.name, custom_id="a_rank"
        )


class BRarityButton(Button):
    def __init__(self):
        super().__init__(
            style=ButtonStyle.secondary, label=NekoRarity.B.name, custom_id="b_rank"
        )


class ToggleNsfwButton(Button):
    def __init__(self):
        super().__init__(
            style=ButtonStyle.secondary,
            emoji="⛔",
            label="Toggle NSFW",
            custom_id="toggle_nsfw",
        )


class NotNekoButton(Button):
    def __init__(self):
        super().__init__(
            style=ButtonStyle.danger, label="Delete", custom_id="delete_neko"
        )


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
        session_generator: async_sessionmaker,
    ):
        super().__init__(timeout=300)
        self.admin_service = admin_service
        self.session_generator = session_generator
        self.add_item(NotNekoButton())
        self.add_item(ToggleNsfwButton())
        self.add_item(BRarityButton())
        self.add_item(ARarityButton())
        self.add_item(SRarityButton())
        self.add_item(ConfirmButton())
        self.session_generator = session_generator
        self.neko = neko

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.data["custom_id"] == "s_rank":
            self.neko.rarity = NekoRarity.S
        elif interaction.data["custom_id"] == "a_rank":
            self.neko.rarity = NekoRarity.A
        elif interaction.data["custom_id"] == "b_rank":
            self.neko.rarity = NekoRarity.B
        elif interaction.data["custom_id"] == "toggle_nsfw":
            self.neko.is_nsfw = not self.neko.is_nsfw
        elif interaction.data["custom_id"] == "delete_neko":
            async with self.session_generator() as session:
                await self.admin_service.delete_neko(self.neko, session)
                self.neko = await self.admin_service.get_neko_classification_info(
                    session
                )

        elif interaction.data["custom_id"] == "confirm_changes":
            async with self.session_generator() as session:
                await self.admin_service.delete_neko(self.neko, session)
                self.neko = await self.admin_service.get_neko_classification_info(
                    session
                )

        embed = await self.admin_service.gen_neko_classification_embed(self.neko)

        await interaction.response.edit_message(embed=embed, view=self)
        return False
