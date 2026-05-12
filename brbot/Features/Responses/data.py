import logging
from brbot.Shared.Discord.buttons import NextPgButton, PrevPgButton
from discord.ui import View
from discord import Interaction
from enum import Enum

logger = logging.getLogger(__name__)


class RspView(View):
    """
    Discord UI View for handling response view interactions.

    Attributes:
        page (int): Which response page in server's response list to display
    """

    def __init__(self, response_service, page: int):
        super().__init__(timeout=60)
        self.response_service = response_service
        self.add_item(PrevPgButton())
        self.add_item(NextPgButton())
        self.page = page

    async def render(self, interaction: Interaction):
        embed = self.response_service.gen_resp_list(interaction.guild, self.page)

        await interaction.response.edit_message(embed=embed, view=self)
        return False


class ResponseType(Enum):
    Phrase = 0
    Exact = 1
    Correction = 2

    def __eq__(self, other):
        if isinstance(other, ResponseType):
            return self.value == other.value
        elif isinstance(other, int):
            return self.value == other
        return NotImplemented
