from discord.ui import Modal, Label, TextInput, Checkbox
from brbot.Core.botdata import pass_str
from discord import Interaction
import logging

logger = logging.getLogger(__name__)


class InvalidKeyError(Exception):
    pass


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
            await self.playgroup_service.register_api_key(
                discord_user=interaction.user, key=self.key.component.value
            )
            await interaction.response.send_message(content=pass_str, ephemeral=True)
        except InvalidKeyError:
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
