"""
Ben Samans
main.py
"""

from time import strftime
from colorama import init, Fore
from random import choice
import botdata as bd
import botutils as bu
import interactions
import json
from os import path, makedirs
from time import sleep

bot = interactions.Client(
    token=bd.token,
    intents=interactions.Intents.DEFAULT | interactions.Intents.MESSAGE_CONTENT | interactions.Intents.GUILDS,
    sync_interactions=True,
    delete_unused_application_cmds=False,
    debug_scope=895549687417958410
)


@interactions.listen()
async def on_guild_join(event: interactions.api.events.GuildJoin):
    guild = event.guild
    if not path.exists(f'{bd.parent}/Guilds/{guild.id}'):
        makedirs(f'{bd.parent}/Guilds/{guild.id}/Trains')
        print(
            Fore.WHITE + '("%Y-{strftime(%m-%d %H:%M:%S")}:  ' +
            Fore.GREEN + f'Guild folder for guild {guild.id} created successfully.' + Fore.RESET
        )
        with open(f'{bd.parent}/Guilds/{int(guild.id)}/config.json', 'w') as f:
            json.dump(bd.default_config, f, indent=4)
        bd.config[int(guild.id)] = bd.default_config
        bd.responses[int(guild.id)] = []
    print(
        Fore.WHITE + f"{strftime(bd.date_format)}:  " + Fore.RESET + f"Added to guild {guild.id}."
    )


@interactions.listen()
async def on_ready():
    guilds = bot.guilds
    assert guilds, "Error connecting to Discord, no guilds listed."
    if not path.exists(f"{bd.parent}/Data/linked_profiles.json"):
        with open(f"{bd.parent}/Data/linked_profiles.json", "w") as f:
            json.dump({}, f, separators=(",", ":"))
    with open(f"{bd.parent}/Data/linked_profiles.json", "r") as f:
        bd.linked_profiles = {int(key): int(val) for key, val in json.load(f).items()}

    bu.load_fonts(f"{bd.parent}/Data")
    print(
        Fore.WHITE + f'{strftime(bd.date_format)} :  Connected to the following guilds: ' +
        Fore.CYAN + ", ".join(guild.name for guild in guilds) + Fore.RESET
    )

    # Load command modules; sleep to avoid rate limit
    bot.load_extension("Features.Trains.cog")
    sleep(.25)
    bot.load_extension("Features.Responses.cog")
    sleep(.25)
    bot.load_extension("Features.Config.cog")
    sleep(.25)

    await bu.init_guilds(guilds=guilds, bot=bot)
    await bot.change_presence(status=interactions.Status.ONLINE, activity="/response")
    sleep(.25)


@interactions.listen()
async def on_message_create(event: interactions.api.events.MessageCreate):
    message = event.message
    if message.author.bot:
        return False
    channel = message.channel
    if channel.type == 1:  # Ignore DMs
        return False

    guild_id = int(message.guild.id)

    to_send = [
        response.text for response in bd.responses[guild_id]
        if response.trig == message.content.lower() and response.exact
    ]
    if to_send:
        to_send = choice(to_send)
        await message.reply(to_send)
        return False

    if not bd.config[guild_id]["ALLOW_PHRASES"]:
        return False

    to_send = [
        response.text for response in bd.responses[guild_id]
        if response.trig in message.content.lower() and not response.exact
    ]

    if to_send:
        to_send = choice(to_send)
        await message.reply(to_send)

    return False


@interactions.listen(interactions.api.events.Component)
async def on_component(event: interactions.api.events.Component):
    ctx = event.ctx
    for idx, msg in enumerate(bd.active_msgs):  # Search active messages for correct one
        if msg.num == int(ctx.message.id):
            game = msg.payload

            # Update page num
            image = None
            embed = None
            if ctx.custom_id == "prevpg":
                bd.active_msgs[idx].page -= 1
            elif ctx.custom_id == "nextpg":
                bd.active_msgs[idx].page += 1

            if msg.msg_type == "trainstats":
                await ctx.defer(edit_origin=True)
                embed, image = game.gen_stats_embed(
                    ctx=ctx, page=bd.active_msgs[idx].page, expired=False
                )
            elif msg.msg_type == "trainscores":
                await ctx.defer(edit_origin=True)
                embed, image = game.gen_score_embed(
                    ctx=ctx, page=bd.active_msgs[idx].page, expired=False
                )

            elif msg.msg_type == "trainrules":
                embed = bu.gen_rules_embed(bd.active_msgs[idx].page, False)
            elif msg.msg_type == "rsplist":
                embed = bu.gen_resp_list(ctx.guild, bd.active_msgs[idx].page, False)

            components = [bu.nextpg_button(), bu.prevpg_button()]

            await ctx.edit_origin(
                embeds=embed,
                components=components,
                file=image,
            )
            break


def main():
    init()
    bot.start()


if __name__ == "__main__":
    main()
