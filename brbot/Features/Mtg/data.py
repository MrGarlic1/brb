from discord.ui import Modal, Label, TextInput, Checkbox
from brbot.Core.botdata import pass_str
from discord import Interaction
import logging

logger = logging.getLogger(__name__)


class PlaygroupKeyModal(Modal, title="Playgroup API Key Input"):
    def __init__(self, playgroup_service):
        super().__init__()
        self.playgroup_service = playgroup_service

    key = Label(
        text="Playgroup API Key",
        description="To obtain your API key, follow the instructions at https://playgroup.gg/api_keys/new",
        component=TextInput(placeholder="123456"),
    )

    disclaimer = Label(
        text="Notice",
        description="This key is used only to generate Playgroup stats.\n"
        "The key is encrypted before storage.",
        component=Checkbox(default=True),
    )

    async def on_submit(self, interaction: Interaction):
        try:
            if await self.playgroup_service.api_key_is_valid(self.key.component.value):
                await self.playgroup_service.encrypt_and_store_api_key(
                    self.key.component.value, interaction.user
                )
                await interaction.response.send_message(
                    content=pass_str, ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    content="Invalid API key!", ephemeral=True
                )

        except Exception as e:
            logger.warning(f"Error validating playgroup API key: {e}")
            await interaction.response.send_message(
                content="An error occurred, please try again.", ephemeral=True
            )


user_agent = "ResponseBot/4.0 (https://github.com/MrGarlic1/Brb)"
base_url = "https://playgroup.gg/api/public/v1"
