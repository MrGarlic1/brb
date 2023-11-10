"""
Ben Samans
BRBot version 3.0.1
Updated 11/6/2023
"""

from termcolor import colored
from time import strftime
from colorama import init
from random import choice
import botdata as bd
import botutils as bu
import asyncio
import interactions
import yaml


bot = interactions.Client(
    token=bd.token,
    intents=interactions.Intents.DEFAULT | interactions.Intents.MESSAGE_CONTENT
)


@interactions.slash_command(
    name="response",
    sub_cmd_name="add",
    sub_cmd_description="Add a response",
)
@interactions.slash_option(
    name="trigger",
    description="Message to respond to",
    required=True,
    opt_type=interactions.OptionType.STRING
)
@interactions.slash_option(
    name="response",
    description="What to respond with",
    required=True,
    opt_type=interactions.OptionType.STRING,
)
@interactions.slash_option(
    name="exact",
    description="Only respond if the message is exactly the trigger phrase (default true)",
    required=False,
    opt_type=interactions.OptionType.BOOLEAN,
)
async def add_response(ctx: interactions.SlashContext, trigger: str = "", response: str = "", exact: bool = True):
    guild_id = int(ctx.guild.id)

    # Config permission checks
    if not bd.config[guild_id]["ALLOW_PHRASES"] and not exact:
        await ctx.send(
            content=f"The server does not allow for phrase-based responses.",
            ephemeral=True
        )
        return True
    if bd.config[guild_id]["LIMIT_USER_RESPONSES"]:
        user_rsps = 0
        for rsp in bd.responses[guild_id]:
            if rsp.user_id == int(ctx.author.id):
                user_rsps += 1
        for rsp in bd.mentions[guild_id]:
            if rsp.user_id == int(ctx.author.id):
                user_rsps += 1
        if user_rsps >= bd.config[guild_id]["MAX_USER_RESPONSES"]:
            await ctx.send(
                content=f"You currently have the maximum of {bd.config[guild_id]['MAX_USER_RESPONSES']} responses.",
                ephemeral=True
            )
            return True

    error = bu.add_response(guild_id, bu.Response(exact, trigger.lower(), response, int(ctx.author.id)))
    if not error:
        await ctx.send(content=bd.pass_str)
    else:
        await ctx.send(content=bd.fail_str)
        return True

    # Update responses
    if exact:
        bd.responses[guild_id] = bu.load_responses(f"{bd.parent}/Guilds/{guild_id}/responses.txt")
    else:
        bd.mentions[guild_id] = bu.load_responses(f"{bd.parent}/Guilds/{guild_id}/mentions.txt")


@interactions.slash_command(
    name="response",
    sub_cmd_name="remove",
    sub_cmd_description="Remove a response",
)
@interactions.slash_option(
    name="trigger",
    description="Message trigger to remove",
    required=True,
    opt_type=interactions.OptionType.STRING
)
@interactions.slash_option(
    name="exact",
    description="If the trigger to remove is an exact trigger (default true)",
    required=False,
    opt_type=interactions.OptionType.BOOLEAN,
)
@interactions.slash_option(
    name="response",
    description="Response text to remove if multiple exist on the same trigger, defaults to the first response",
    required=False,
    opt_type=interactions.OptionType.STRING
)
async def remove_response(ctx: interactions.SlashContext, trigger: str = "", response: str = "", exact: bool = True):
    # Config permission checks
    guild_id = int(ctx.guild.id)
    if bd.config[guild_id]["USER_ONLY_DELETE"] and \
            bu.get_resp(guild_id, trigger, response, exact).user_id != ctx.author.id:
        await ctx.send(
            content=f"The server settings do not allow you to delete other people\'s responses.",
            ephemeral=True
        )
        return True

    error = bu.rmv_response(guild_id, bu.Response(exact, trigger.lower(), response, "_"))
    if not error:
        await ctx.send(content=bd.pass_str)
    else:
        await ctx.send(content=bd.fail_str)
        return True

    # Update responses
    if exact:
        bd.responses[guild_id] = bu.load_responses(f"{bd.parent}/Guilds/{guild_id}/responses.txt")
    else:
        bd.mentions[guild_id] = bu.load_responses(f"{bd.parent}/Guilds/{guild_id}/mentions.txt")


@interactions.slash_command(
    name="listresponses",
    description="Show list of all responses for the server",
)
async def listrsps(ctx: interactions.SlashContext):
    resp_msg = await ctx.send(
        embeds=bu.gen_resp_list(ctx.guild, 0, False),
        components=[bu.prevpg_button(), bu.nextpg_button()]
    )
    channel = ctx.channel
    sent = bu.ListMsg(resp_msg.id, 0, ctx.guild, channel)
    bd.active_msgs.append(sent)
    asyncio.create_task(
        bu.close_msg(sent, 300, ctx, resp_msg)
    )
    return False


@interactions.slash_command(
    name="mod",
    sub_cmd_name="deletedata",
    sub_cmd_description="Deletes ALL response data from the server",
    default_member_permissions=interactions.Permissions.ADMINISTRATOR,
)
async def delete_data(ctx: interactions.SlashContext):
    guild_id = int(ctx.guild.id)
    open(f"{bd.parent}/Guilds/{guild_id}/responses.txt", "w")
    f = open(f"{bd.parent}/Guilds/{guild_id}/mentions.txt", "w")
    f.close()
    bd.responses[guild_id], bd.mentions[guild_id] = [], []
    await ctx.send(content=bd.pass_str)


@interactions.slash_command(
    name="mod",
    sub_cmd_name="add",
    sub_cmd_description="Adds a response (ignores restrictions)",
    default_member_permissions=interactions.Permissions.ADMINISTRATOR,
)
@interactions.slash_option(
    name="trigger",
    description="Message to respond to",
    required=True,
    opt_type=interactions.OptionType.STRING
)
@interactions.slash_option(
    name="response",
    description="What to respond with",
    required=True,
    opt_type=interactions.OptionType.STRING,
)
@interactions.slash_option(
    name="exact",
    description="Only respond if the message is exactly the trigger phrase (default true)",
    required=False,
    opt_type=interactions.OptionType.BOOLEAN,
)
async def mod_add(ctx: interactions.SlashContext, trigger: str = "", response: str = "", exact: bool = True):
    guild_id = int(ctx.guild.id)

    error = bu.add_response(guild_id, bu.Response(exact, trigger.lower(), response, int(ctx.author.id)))
    if not error:
        await ctx.send(content=bd.pass_str)
    else:
        await ctx.send(content=bd.fail_str)
        return True

    # Update responses
    if exact:
        bd.responses[guild_id] = bu.load_responses(f"{bd.parent}/Guilds/{guild_id}/responses.txt")
    else:
        bd.mentions[guild_id] = bu.load_responses(f"{bd.parent}/Guilds/{guild_id}/mentions.txt")


@interactions.slash_command(
    name="mod",
    sub_cmd_name="remove",
    sub_cmd_description="Remove a response (ignores restrictions)",
    default_member_permissions=interactions.Permissions.ADMINISTRATOR,
)
@interactions.slash_option(
    name="trigger",
    description="Message trigger to remove",
    required=True,
    opt_type=interactions.OptionType.STRING
)
@interactions.slash_option(
    name="exact",
    description="If the trigger to remove is an exact trigger (default true)",
    required=False,
    opt_type=interactions.OptionType.BOOLEAN,
)
@interactions.slash_option(
    name="response",
    description="Response text to remove if multiple exist on the same trigger, defaults to the first response",
    required=False,
    opt_type=interactions.OptionType.STRING
)
async def mod_remove(ctx: interactions.SlashContext, trigger: str = "", response: str = "", exact: bool = True):
    guild_id = int(ctx.guild.id)
    error = bu.rmv_response(guild_id, bu.Response(exact, trigger.lower(), response, "_"))
    if not error:
        await ctx.send(content=bd.pass_str)
    else:
        await ctx.send(content=bd.fail_str)
        return True

    # Update responses
    if exact:
        bd.responses[guild_id] = bu.load_responses(f"{bd.parent}/Guilds/{guild_id}/responses.txt")
    else:
        bd.mentions[guild_id] = bu.load_responses(f"{bd.parent}/Guilds/{guild_id}/mentions.txt")


@interactions.slash_command(
    name="config",
    sub_cmd_name="reset",
    sub_cmd_description="Resets ALL server settings to default.",
    default_member_permissions=interactions.Permissions.ADMINISTRATOR,
)
async def cfg_reset(ctx: interactions.SlashContext):
    guild_id = int(ctx.guild.id)
    with open(f"{bd.parent}/Guilds/{guild_id}/config.yaml", "w") as f:
        yaml.dump(bd.default_config, f, Dumper=yaml.Dumper)
    bd.config[guild_id] = yaml.load(
        open(f"{bd.parent}/Guilds/{guild_id}/config.yaml"), Loader=yaml.Loader
    )
    await ctx.send(content=bd.pass_str)


@interactions.slash_command(
    name="config",
    sub_cmd_name="view",
    sub_cmd_description="Views the current server settings.",
    default_member_permissions=interactions.Permissions.ADMINISTRATOR,
)
async def cfg_view(ctx: interactions.SlashContext):
    guild_id = int(ctx.guild.id)
    await ctx.send(
        content=f"Allow Phrases: {bd.config[guild_id]['ALLOW_PHRASES']}\n"
                f"Limit Responses: {bd.config[guild_id]['LIMIT_USER_RESPONSES']}\n"
                f"Response Limit # (Only if Limit Responses is True): {bd.config[guild_id]['MAX_USER_RESPONSES']}\n"
                f"Restrict User Response Deleting: {bd.config[guild_id]['USER_ONLY_DELETE']}\n"
    )


@interactions.slash_command(
    name="config",
    sub_cmd_name="userperms",
    sub_cmd_description="Enables/disables user\'s ability to delete other people\'s responses.",
    default_member_permissions=interactions.Permissions.ADMINISTRATOR,
)
@interactions.slash_option(
    name="enable",
    description="True = Can delete, False = Can not delete",
    opt_type=interactions.OptionType.BOOLEAN,
    required=True
)
async def cfg_user_perms(ctx: interactions.SlashContext, enable: bool = True):
    guild_id = int(ctx.guild.id)
    bd.config[guild_id]["USER_ONLY_DELETE"] = not enable
    with open(f"{bd.parent}/Guilds/{guild_id}/config.yaml", "w") as f:
        yaml.dump(bd.config[guild_id], f, Dumper=yaml.Dumper)
    await ctx.send(content=bd.pass_str)


@interactions.slash_command(
    name="config",
    sub_cmd_name="limitresponses",
    sub_cmd_description="Sets (or disables) the number of responses each user can have.",
    default_member_permissions=interactions.Permissions.ADMINISTRATOR,
)
@interactions.slash_option(
    name="enable",
    description="True = Responses are limited, False = No limit",
    opt_type=interactions.OptionType.BOOLEAN,
    required=True
)
@interactions.slash_option(
    name="limit",
    description="Maximum number of responses per user (limit 10)",
    opt_type=interactions.OptionType.INTEGER,
    required=False
)
async def cfg_set_limit(ctx: interactions.SlashContext, enable: bool = True, limit: int = 10):
    guild_id = int(ctx.guild.id)
    if limit < 1:
        limit = 1
    bd.config[guild_id]["LIMIT_USER_RESPONSES"] = enable
    bd.config[guild_id]["MAX_USER_RESPONSES"] = limit
    with open(f"{bd.parent}/Guilds/{guild_id}/config.yaml", "w") as f:
        yaml.dump(bd.config[guild_id], f, Dumper=yaml.Dumper)
    await ctx.send(content=bd.pass_str)


@interactions.slash_command(
    name="config",
    sub_cmd_name="allowphrases",
    sub_cmd_description="Enables/disables responses based on phrases rather than whole messages",
    default_member_permissions=interactions.Permissions.ADMINISTRATOR,
)
@interactions.slash_option(
    name="enable",
    description="True = Responses are limited, False = No limit",
    opt_type=interactions.OptionType.BOOLEAN,
    required=True
)
async def cfg_allow_phrases(ctx: interactions.SlashContext, enable: bool = True):
    guild_id = int(ctx.guild.id)
    bd.config[guild_id]["ALLOW_PHRASES"] = enable
    with open(f"{bd.parent}/Guilds/{guild_id}/config.yaml", "w") as f:
        yaml.dump(bd.config[guild_id], f, Dumper=yaml.Dumper)
    await ctx.send(content=bd.pass_str)


@interactions.listen()
async def on_guild_join(event: interactions.api.events.GuildJoin):
    guild = event.guild
    bu.guild_add(guild)
    print(
        colored(f"{strftime('%Y-%m-%d %H:%M:%S')} :  ", "white") + f"Added to guild {guild.id}."
    )


@interactions.listen()
async def on_ready():
    guilds = bot.guilds
    assert guilds, "Error connecting to Discord, no guilds listed."
    print(
        colored(strftime("%Y-%m-%d %H:%M:%S") + " :  ", "white") + "Connected to the following guilds: " +
        colored(", ".join(guild.name for guild in guilds), "cyan")
    )
    for guild in guilds:

        bu.load_config(guild)

        # Load guild responses
        guild_id = int(guild.id)
        bd.mentions[guild_id] = bu.load_responses(f"{bd.parent}/Guilds/{guild_id}/mentions.txt")
        bd.responses[guild_id] = bu.load_responses(f"{bd.parent}/Guilds/{guild_id}/responses.txt")
        print(
            colored(f"{strftime('%Y-%m-%d %H:%M:%S')} :  ", "white") +
            colored(f"Responses loaded for {guild.name}", "green")
        )
    await bot.change_presence(status=interactions.Status.ONLINE, activity="/response")


@interactions.listen()
async def on_message_create(event: interactions.api.events.MessageCreate):
    message = event.message
    if message.author.bot:
        return False

    channel = message.channel
    if channel.type == 1:  # Ignore DMs
        return False

    guild_id = int(message.guild.id)

    to_send = []
    done = False

    for i in bd.responses[guild_id]:
        if i.trig == message.content.lower():
            to_send.append(i.text)
            done = True
    if done:
        to_send = choice(to_send) if len(to_send) > 1 else to_send[0]
        await message.reply(to_send)
        return False

    if not bd.config[guild_id]["ALLOW_PHRASES"]:
        return False

    for i in bd.mentions[guild_id]:
        if i.trig in message.content.lower():
            to_send.append(i.text)
            done = True
    if done:
        to_send = choice(to_send) if len(to_send) > 1 else to_send[0]
        await message.reply(to_send)

    return False


@interactions.listen(interactions.api.events.Component)
async def on_component(event: interactions.api.events.Component):
    ctx = event.ctx
    for msg in bd.active_msgs:  # Search active messages for correct one
        if msg.num == int(ctx.message.id):
            idx = bd.active_msgs.index(msg)

            # Update page num
            if ctx.custom_id == "prev page":
                bd.active_msgs[idx].page -= 1
            elif ctx.custom_id == "next page":
                bd.active_msgs[idx].page += 1

            await ctx.edit_origin(
                embeds=bu.gen_resp_list(ctx.guild, bd.active_msgs[idx].page, False),
                components=[bu.prevpg_button(), bu.nextpg_button()]
            )
            break


def main():
    init()
    bot.start()


if __name__ == "__main__":
    main()
