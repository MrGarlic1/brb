from discord import ButtonStyle, Interaction
from discord.ui import Button


class NextPgButton(Button):
    def __init__(self):
        super().__init__(
            style=ButtonStyle.success,
            label="Next",
            custom_id="next_page",
        )

    async def callback(self, interaction: Interaction):
        self.view.page += 1
        await self.view.render(interaction)


class PrevPgButton(Button):
    def __init__(self):
        super().__init__(
            style=ButtonStyle.danger,
            label="Prev",
            custom_id="prev_page",
        )

    async def callback(self, interaction: Interaction):
        self.view.page -= 1
        await self.view.render(interaction)
