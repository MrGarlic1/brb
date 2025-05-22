import interactions
from emoji import emojize, demojize
import Core.botdata as bd


def gen_help_embed() -> (interactions.Embed, interactions.StringSelectMenu):
    return base_general_embed, help_category_menu


def base_general_embed(expired: bool = False) -> interactions.Embed:
    embed: interactions.Embed = interactions.Embed()
    embed.set_author(name=f"Bootleg Response Bot Help", icon_url=bd.bot_avatar_url)
    footer_end: str = ' | This message is inactive.' if expired else ' | This message deactivates after 5 minutes.'
    embed.set_footer(text=footer_end)
    return embed


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
