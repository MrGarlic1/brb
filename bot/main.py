"""
Ben Samans
main.py
"""

from time import sleep
from time import strftime

import interactions
import logging

import Core.botdata as bd
import Core.botutils as bu

bot = interactions.Client(
    token=bd.token,
    intents=interactions.Intents.DEFAULT | interactions.Intents.MESSAGE_CONTENT | interactions.Intents.GUILDS,
    sync_interactions=True,
    delete_unused_application_cmds=True,
)

logger = logging.getLogger(__name__)
logging.basicConfig(
    format='%(asctime)s %(levelname)s:%(name)s: %(message)8s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)


@interactions.listen()
async def on_guild_join(event: interactions.api.events.GuildJoin):
    guild = event.guild
    bu.setup_guild(guild)
    logger.info(
        f"Added to guild {guild.id}"
    )


@interactions.listen()
async def on_ready():
    guilds = bot.guilds
    bd.bot_avatar_url = bot.user.avatar_url
    assert guilds, "Error connecting to Discord, no guilds listed."

    bu.load_anilist_caches()

    bu.load_fonts(f"{bd.parent}/Data")
    logger.info(
        f'Connected to the following guilds: {", ".join(guild.name for guild in guilds)}'
    )

    # Load command modules; sleep to avoid rate limit
    bot.load_extension("Features.Animanga.cog")
    sleep(.25)
    bot.load_extension("Features.Trains.cog")
    sleep(.25)
    bot.load_extension("Features.Responses.cog")
    sleep(.25)
    bot.load_extension("Features.Config.cog")
    sleep(.25)
    bot.load_extension("Features.Bingo.cog")
    sleep(.25)
    bot.load_extension("Features.Help.cog")
    sleep(.25)

    await bu.init_guilds(guilds=guilds)
    await bot.change_presence(status=interactions.Status.ONLINE, activity="/response")
    sleep(.25)


@interactions.listen()
async def on_message_create(event: interactions.api.events.MessageCreate):
    message = event.message
    response = bu.generate_response(message)

    if response is None:
        return False

    await message.reply(response)
    return False


@interactions.listen(interactions.api.events.Component)
async def on_component(event: interactions.api.events.Component):
    ctx = event.ctx
    await ctx.defer(edit_origin=True)

    embed, components, image = bu.handle_page_change(ctx=ctx)
    await ctx.edit_origin(
        embeds=embed,
        components=components,
        file=image,
    )
    return False


def main():
    try:
        bot.start()
    except exception as e:
        logger.critical(f'Failed to start bot: {e}')


if __name__ == "__main__":
    main()
