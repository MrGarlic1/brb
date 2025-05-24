import interactions
from emoji import emojize, demojize
import Core.botdata as bd


help_pages = {
    "general": 0,
    "response": 1,
    "trains": 2,
    "bingo": 3,
    "config": 4,
    "animanga": 5
}

help_msgs = [
    "General Commands here",
    "**/response add [trigger] [response] <exact>**\n"
    "/response remove [trigger] <response> <exact>\n"
    "/listresponses",
    "placeholder",
    "placeholder",
    "placeholder",
    "placeholder"
]


def gen_help_embed(page: int, expired: bool = False) -> (interactions.Embed, interactions.StringSelectMenu):
    embed: interactions.Embed = interactions.Embed()
    embed.set_author(name=f"Response Bot Help", icon_url=bd.bot_avatar_url)
    footer_end: str = ' | This message is inactive.' if expired else ' | This message deactivates after 5 minutes.'
    embed.set_footer(text=footer_end)
    embed.add_field(
        name=f"{[category for category, pagenum in help_pages.items() if pagenum == category][0].title()} Commands",
        value=help_msgs[page]
    )
    return embed, help_category_menu


help_category_menu = interactions.StringSelectMenu(
    interactions.StringSelectOption(value="general", label="General", default=True, emoji="🌎"),
    interactions.StringSelectOption(value="responses", label="Responses", emoji="📣"),
    interactions.StringSelectOption(value="trains", label="Trains", emoji="🚅"),
    interactions.StringSelectOption(value="bingo", label="Bingo", emoji="🎱"),
    interactions.StringSelectOption(value="config", label="Config", emoji="⚙"),
    interactions.StringSelectOption(value="animanga", label="Animanga", emoji="🌸"),
    custom_id="help_category",
    placeholder="Select a category...",
    min_values=1,
    max_values=1,
)
