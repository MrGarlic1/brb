import bot.Core.botdata as bd
from discord.ui import View, Select
from discord import Interaction, Embed, SelectOption

help_msgs = {
    "general": "General Commands here",
    "response": "**/response add [trigger] [response] <exact>**\n",
    "trains": "/response remove [trigger] <response> <exact>\n",
    "bingo": "/listresponses",
    "config": "placeholder",
    "animanga": "placeholder",
}


def gen_help_embed(category: str) -> (Embed, Select):
    embed: Embed = Embed()
    embed.set_author(name=f"Response Bot Help", icon_url=bd.bot_avatar_url)
    embed.set_footer(text="")
    embed.add_field(
        name=f"{category} Commands",
        value=help_msgs[category]
    )
    return embed


help_category_menu = Select(
    options=[
        SelectOption(value="general", label="General", emoji="🌎"),
        SelectOption(value="response", label="Response", emoji="📣"),
        SelectOption(value="trains", label="Trains", emoji="🚅"),
        SelectOption(value="bingo", label="Bingo", emoji="🎱"),
        SelectOption(value="config", label="Config", emoji="⚙"),
        SelectOption(value="animanga", label="Animanga", emoji="🌸"),
    ],
    custom_id="help_category",
    placeholder="Select a category..."
)


class HelpView(View):
    """
    Discord UI View for handling help interactions.

    Attributes:
        anilist_id (str): Anilist id to recommend for
        username (str): Discord username
        media_type (str): Specify to recommend manga/anime
        genre (str): Limit recommendations to specified genre
        page (int): Which recommendation in user's rec list to display
    """

    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(help_category_menu)
        self.category = 'general'

    async def interaction_check(self, interaction: Interaction) -> bool:
        category = interaction.data['values'][0]

        embed = gen_help_embed(category)

        await interaction.response.edit_message(
            embed=embed, view=self
        )
        return True
