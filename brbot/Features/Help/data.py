import brbot.Core.botdata as bd
from discord.ui import View, Select
from discord import Interaction, Embed, SelectOption
import logging

logger = logging.getLogger(__name__)

help_msgs = {
    "general": "General Commands here",
    "response": "**/response add [trigger] [response] <exact>**\n",
    "trains": "/response remove [trigger] <response> <exact>\n",
    "bingo": "/listresponses",
    "config": "placeholder",
    "animanga": "placeholder",
}


def gen_help_embed(category: str) -> Embed:
    embed: Embed = Embed()
    embed.set_author(name="Response Bot Help", icon_url=bd.bot_avatar_url)
    embed.set_footer(text="")
    embed.add_field(name=f"{category} Commands", value=help_msgs[category])
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
    placeholder="Select a category...",
)


class HelpView(View):
    """
    Discord UI View for handling help interactions.
    """

    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(help_category_menu)
        self.category = "general"

    async def interaction_check(self, interaction: Interaction) -> bool:
        category = interaction.data["values"][0]

        logger.debug(
            f"Generating help embed with category {category} from {interaction.data}"
        )
        embed = gen_help_embed(category)
        await interaction.response.edit_message(embed=embed, view=self)
        return True
