"""
Ben Samans
main.py
"""

from time import sleep
from time import strftime

import interactions
from colorama import init, Fore

import Core.botdata as bd
import Core.botutils as bu

bot = interactions.Client(
    token=bd.token,
    intents=interactions.Intents.DEFAULT | interactions.Intents.MESSAGE_CONTENT | interactions.Intents.GUILDS,
    sync_interactions=True,
    delete_unused_application_cmds=False
)


@interactions.listen()
async def on_guild_join(event: interactions.api.events.GuildJoin):
    guild = event.guild
    bu.setup_guild(guild)
    print(
        Fore.WHITE + f"{strftime(bd.date_format)}:  " + Fore.RESET + f"Added to guild {guild.id}."
    )


@interactions.listen()
async def on_ready():
    guilds = bot.guilds
    assert guilds, "Error connecting to Discord, no guilds listed."

    bu.load_anilist_caches()

    bu.load_fonts(f"{bd.parent}/Data")
    print(
        Fore.WHITE + f'{strftime(bd.date_format)} :  Connected to the following guilds: ' +
        Fore.CYAN + ", ".join(guild.name for guild in guilds) + Fore.RESET
    )

    # Load command modules; sleep to avoid rate limit
    bot.load_extension("Features.Anime.cog")
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
    init()
    bot.start()


if __name__ == "__main__":
    main()
