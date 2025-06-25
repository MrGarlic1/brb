from discord import ButtonStyle
from discord.ui import Button


class NextPgButton(Button):
    def __init__(self):
        super().__init__(
            style=ButtonStyle.success,
            label="Next",
            custom_id="next_page",
        )


class PrevPgButton(Button):
    def __init__(self):
        super().__init__(
            style=ButtonStyle.danger,
            label="Prev",
            custom_id="prev_page",
        )
