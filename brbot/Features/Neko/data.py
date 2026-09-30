from discord import ButtonStyle, Interaction

from brbot.Shared.Neko.models import NekoRarity
from discord.ui import View, Button

NEKO_ROLL_CHANCES = {
    NekoRarity.SS: 0.005,
    NekoRarity.S: 0.045,
    NekoRarity.A: 0.20,
    NekoRarity.B: 0.75,
}

NEKO_NSFW_LOSS_CHANCES = {
    NekoRarity.SS: 0,
    NekoRarity.S: 0.25,
    NekoRarity.A: 0.5,
    NekoRarity.B: 1,
}

NEKO_COLORS = {
    NekoRarity.SS: 0xFF2462,
    NekoRarity.S: 0xFFF27A,
    NekoRarity.A: 0xC666E3,
    NekoRarity.B: 0x3B49D1,
}

NEKO_HOURLY_ROLLS = 5


class RollAgainButton(Button):
    def __init__(self, neko_cog):
        super().__init__(
            style=ButtonStyle.success,
            label="Roll Again",
            custom_id="roll_again",
            emoji="🎲",
        )
        self.neko_cog = neko_cog

    async def callback(self, interaction: Interaction):
        await self.neko_cog.run_neko(interaction)


class NekoView(View):
    def __init__(self, neko_cog):
        super().__init__(timeout=60)
        self.add_item(RollAgainButton(neko_cog))
