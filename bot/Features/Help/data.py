import interactions
from emoji import emojize, demojize
import Core.botdata as bd


def gen_help_message(cagegory: str, expired: bool, page: int = 1) -> interactions.Embed:
    embed: interactions.Embed = interactions.Embed()
    embed.set_author(name=f"Anime Trains", icon_url=bd.bot_avatar_url)
    footer_end: str = ' | This message is inactive.' if expired else ' | This message deactivates after 5 minutes.'
    embed.set_footer(text=f'Page {page}/5 {footer_end}')
    return embed
