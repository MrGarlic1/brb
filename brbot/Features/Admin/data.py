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


class SSRarityButton(Button):
    def __init__(self):
        super().__init__(
            style=ButtonStyle.secondary, label=NekoRarity.SS.name, custom_id="ss_rank"
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
        original_neko: NekoClassificationInfo,
        remaining_count: int,
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
        self.add_item(SSRarityButton())
        self.add_item(ConfirmButton())
        self.neko = neko
        self.original_neko = original_neko
        self.offset = 0
        self.remaining_count = remaining_count

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.data["custom_id"] == "ss_rank":
            self.neko.rarity = NekoRarity.SS
        if interaction.data["custom_id"] == "s_rank":
            self.neko.rarity = NekoRarity.S
        elif interaction.data["custom_id"] == "a_rank":
            self.neko.rarity = NekoRarity.A
        elif interaction.data["custom_id"] == "b_rank":
            self.neko.rarity = NekoRarity.B
        elif interaction.data["custom_id"] == "toggle_nsfw":
            self.neko.nsfw = True if self.neko.nsfw is None else not self.neko.nsfw
        elif interaction.data["custom_id"] == "delete_neko":
            async with self.session_generator() as session:
                await self.admin_service.delete_neko(self.neko, session)
                self.neko = await self.admin_service.get_neko_classification_info(
                    rarity=self.original_neko.rarity,
                    nsfw=self.original_neko.nsfw,
                    session=session,
                    offset=self.offset,
                )
                self.remaining_count -= 1

        elif interaction.data["custom_id"] == "confirm_changes":
            async with self.session_generator() as session:
                await self.admin_service.update_neko(self.neko, session)
                # Increment offset to get the next from DB if classification does not change
                if (
                    self.neko.rarity == self.original_neko.rarity
                    and self.neko.nsfw == self.original_neko.nsfw
                ):
                    self.offset += 1

                self.remaining_count -= 1

                # Fetch new entry with the same classification as the original request
                self.neko = await self.admin_service.get_neko_classification_info(
                    self.original_neko.rarity,
                    session,
                    self.original_neko.nsfw,
                    self.offset,
                )

        embed = await self.admin_service.gen_neko_classification_embed(
            self.neko, self.remaining_count
        )

        await interaction.response.edit_message(embed=embed, view=self)
        return False
