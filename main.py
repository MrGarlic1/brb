"""
Ben Samans
BRBot version 3.2.1
Updated 3/19/2024
"""

from termcolor import colored
from time import strftime, sleep
from colorama import init
from random import choice
import botdata as bd
import botutils as bu
import asyncio
import interactions
import yaml
from datetime import datetime
from os import listdir, mkdir, path
from shutil import rmtree
import io
from socket import gaierror

bot = interactions.Client(
    token=bd.token,
    intents=interactions.Intents.DEFAULT | interactions.Intents.MESSAGE_CONTENT,
)


@interactions.slash_command(
    name="trains",
    sub_cmd_name="newgame",
    sub_cmd_description="Create a new trains game",
    dm_permission=False
)
@interactions.slash_option(
    name="players",
    description="@ the participating players",
    required=True,
    opt_type=interactions.OptionType.STRING
)
@interactions.slash_option(
    name="name",
    description="Bingo game name",
    required=True,
    opt_type=interactions.OptionType.STRING
)
@interactions.slash_option(
    name="width",
    description="Play area width, must be divisible by 4. Default 16",
    required=False,
    opt_type=interactions.OptionType.INTEGER
)
@interactions.slash_option(
    name="height",
    description="Play area height, must be divisible by 4. Default 16",
    required=False,
    opt_type=interactions.OptionType.INTEGER
)
async def create_trains(
        ctx: interactions.SlashContext, name: str, players: str, width: int = 16, height: int = 16
):
    await ctx.defer()
    river_ring = 1
    guild_id = int(ctx.guild_id)

    # Return errors if game is active or invalid name/width/height
    if guild_id in bd.active_trains:
        await ctx.send(content=f"There is already an active game ({bd.active_trains[guild_id].name}) in this server.")
        return True
    if width % 4 != 0 or height % 4 != 0:
        await ctx.send(content="Width and height must be divisible by 4.")
        return True
    if path.exists(f"{bd.parent}/Guilds/{guild_id}/Trains/{name}"):
        await ctx.send(content="Name already exists!")
        return True

    # Create player list and tags
    members = await bu.get_members_from_str(ctx.guild, players)
    players = []
    tags = bu.get_player_tags(members)

    for member, tag in zip(members, tags):
        dm = await member.fetch_dm(force=False)
        players.append(
            bu.TrainPlayer(member=member, tag=tag, dmchannel=dm)
        )
    # Return error if player list is empty
    if not players:
        await ctx.send(content="No valid players specified.")
        return True

    try:
        mkdir(f"{bd.parent}/Guilds/{guild_id}/Trains/{name}")
    except OSError:
        await ctx.send(content="Invalid name! Game must not contain the following characters: / \\ : * ? < > |")
        return True

    # Create game object and set parameters
    date = datetime.now().strftime(bd.date_format)
    gameid = int(datetime.now().strftime("%Y%m%d%H%M%S"))

    game = bu.TrainGame(
        name=name,
        date=date,
        players=players,
        board=None,
        gameid=gameid,
        active=True,
        size=(width + 2*river_ring, height + 2*river_ring)  # Add space on board for river border
    )
    game.gen_trains_board(
        board_size=(width, height), river_ring=river_ring
    )
    if type(game.board) is str:
        await ctx.send(content=game.board)
        return True

    # Add player start locations
    game.gen_player_locations(river_ring=river_ring)

    # Unsuccessful board generation
    if game is True:
        await ctx.send(content="Unsuccessful board generation. Try making the size larger?")
        return True
    # Push updates to player boards
    await game.update_boards_after_create(ctx=ctx)
    await ctx.send(embed=bu.train_game_embed(ctx=ctx, game=game))
    return False


@interactions.slash_command(
    name="trains",
    sub_cmd_name="shot",
    sub_cmd_description="Make a trains shot",
    dm_permission=False
)
@interactions.slash_option(
    name="row",
    description="Shot row",
    required=True,
    opt_type=interactions.OptionType.INTEGER
)
@interactions.slash_option(
    name="column",
    description="Shot column",
    required=True,
    opt_type=interactions.OptionType.INTEGER
)
@interactions.slash_option(
    name="genre",
    description="Genre of show used for shot",
    required=True,
    opt_type=interactions.OptionType.STRING,
    choices=bu.dict_to_choices(bu.genre_colors)
)
@interactions.slash_option(
    name="info",
    description="Show/stock information",
    required=True,
    opt_type=interactions.OptionType.STRING
)
async def record_shot(ctx: interactions.SlashContext, row: int, column: int, genre: str, info: str):
    await ctx.defer(ephemeral=True)
    try:
        game = bd.active_trains[ctx.guild_id]
    except KeyError:
        await ctx.send(content="There is no active game! To make one, use /trains newgame", ephemeral=True)
        return True

    # Get player, validate shot
    sender_idx, player = game.get_player(int(ctx.author_id))
    valid = game.valid_shot(player, row, column)
    if not valid:
        await ctx.send(content=bd.fail_str)
        return True

    # Update board, player rails
    game.board[(row, column)]["rails"].append(player.tag)
    game.players[sender_idx].shots.append(
        bu.TrainShot(location=(row, column), genre=genre, info=info, time=datetime.now().strftime(bd.date_format))
    )
    game.add_visible_tiles(sender_idx, row, column)

    if game.board[(row, column)]["resource"] == "gems" and game.bonus["first_to_gems"] is None:
        game.bonus["first_to_gems"] = ctx.author_id

    if game.board[(row, column)]["terrain"] == "river":
        rails = 2
    else:
        rails = 1
    if game.board[(row, column)]["zone"] == genre:
        rails = rails*0.5
    game.players[sender_idx].rails += rails
    if (row, column) == player.end:
        game.players[sender_idx].done = True
        game.players[sender_idx].donetime = datetime.now().strftime("%Y%m%d%H%M%S")

    # Save/update games
    await game.update_boards_after_shot(
        ctx=ctx, row=row, column=column
    )


@interactions.slash_command(
    name="trains",
    sub_cmd_name="undo",
    sub_cmd_description="Undo your last shot.",
    dm_permission=False
)
async def undo_shot(ctx: interactions.SlashContext):
    await ctx.defer(ephemeral=True)

    # Determine if undo is valid
    try:
        game = bd.active_trains[ctx.guild_id]
    except KeyError:
        await ctx.send(content="There is no active game! To make one, use /trains newgame", ephemeral=True)
        return True

    sender_idx, player = game.get_player(int(ctx.author_id))
    if not player.shots:
        await ctx.send(content="You have not taken any shots yet!", ephemeral=True)
        return True

    row = game.players[sender_idx].shots[-1].location[0]
    column = game.players[sender_idx].shots[-1].location[1]
    genre = game.players[sender_idx].shots[-1]

    # Delete last shot from record, re-render visible tiles
    game.board[(row, column)]["rails"].remove(player.tag)
    del game.players[sender_idx].shots[-1]
    game.players[sender_idx].vis_tiles = []
    if game.players[sender_idx].done:
        game.players[sender_idx].done = False
        game.players[sender_idx].donetime = None

    for shot in player.shots:
        game.add_visible_tiles(
            player_idx=sender_idx, shot_row=shot.location[0], shot_col=shot.location[1]
        )

    # Update player rails
    if game.board[(row, column)]["terrain"] == "river":
        rails = 2
    else:
        rails = 1
    if game.board[(row, column)]["zone"] == genre:
        rails = rails*0.5
    game.players[sender_idx].rails -= rails

    # Save/update games
    await game.update_boards_after_shot(
        ctx=ctx, row=row, column=column
    )


@interactions.slash_command(
    name="trains",
    sub_cmd_name="stats",
    sub_cmd_description="View limited/full stats for an in-progress/completed game.",
    dm_permission=False
)
@interactions.slash_option(
    name="name",
    description="Name of game to get stats of (defaults to active game)",
    required=False,
    opt_type=interactions.OptionType.STRING,
    choices=[]
)
async def trains_stats(ctx: interactions.SlashContext, name: str = None):
    # Logic to get game or return error if no game found
    if name is None:
        try:
            game = bd.active_trains[ctx.guild_id]
        except KeyError:
            await ctx.send(content="No active game found, please specify a game name.")
            return True
    else:
        try:
            game = await bu.load_game(
                filepath=f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{name}", bot=bot, guild=ctx.guild
            )
        except FileNotFoundError:
            await ctx.send(content="Game name does not exist.")
            return True
    await ctx.defer()

    # Send stats
    embed, image = game.gen_stats_embed(ctx=ctx, page=0, expired=False)

    stats_msg = await ctx.send(embed=embed, file=image, components=[bu.prevpg_trainstats(), bu.nextpg_trainstats()])
    sent = bu.ListMsg(
        num=stats_msg.id, page=0, guild=ctx.guild, channel=ctx.channel, msg_type="trainstats", payload=game
    )
    bd.active_msgs.append(sent)
    _ = asyncio.create_task(
        bu.close_msg(sent, 300, ctx, stats_msg)
    )


@trains_stats.autocomplete("name")
async def autocomplete(ctx: interactions.AutocompleteContext):
    games = listdir(f"{bd.parent}/Guilds/{ctx.guild_id}/Trains")
    choices = []
    for game in games:
        choices.append({"name": game, "value": game})
    await ctx.send(
        choices=choices
    )


@interactions.slash_command(
    name="trains",
    sub_cmd_name="board",
    sub_cmd_description="View your train board for the active game.",
    dm_permission=False,
    scopes=[895549687417958410]
)
async def show_trains_board(ctx: interactions.SlashContext):
    try:
        game = bd.active_trains[ctx.guild_id]
    except KeyError:
        await ctx.send(content="No active game found.", ephemeral=True)
        return True

    player_idx, player = game.get_player(ctx.author_id)
    if not player:
        await ctx.send(content="You are not a player in this game.", ephemeral=True)
        return True

    try:
        with open(f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{game.name}/{ctx.author_id}.png", "rb") as f:
            file = io.BytesIO(f.read())
    except FileNotFoundError:
        await ctx.send(bd.fail_str, ephemeral=True)
        return True

    await ctx.send(file=interactions.File(file, file_name="board_img.png"), ephemeral=True)
    return False


@interactions.slash_command(
    name="mod",
    sub_cmd_name="deletetrain",
    sub_cmd_description="Remove the active trains game. (ADMIN ONLY)",
    default_member_permissions=interactions.Permissions.ADMINISTRATOR,
    dm_permission=False
)
@interactions.slash_option(
    name="keep_files",
    description="Choose whether to archive or completely delete the active game's files",
    required=True,
    opt_type=interactions.OptionType.BOOLEAN,
)
async def delete_trains_game(ctx: interactions.SlashContext, keep_files: bool):
    await ctx.defer()
    try:
        game = bd.active_trains[ctx.guild_id]
    except KeyError:
        await ctx.send(content="There is no active game! To make one, use /trains newgame", ephemeral=True)
        return True

    if keep_files:
        game.active = False
        game.save_game(f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{game.name}")
    else:
        try:
            rmtree(f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{game.name}")
        except PermissionError:
            await ctx.send(content="Could not delete files. Try again in a couple of minutes.")
            return True
    del bd.active_trains[ctx.guild_id]
    await ctx.send(content=bd.pass_str)
    return False


@interactions.slash_command(
    name="mod",
    sub_cmd_name="restoretrain",
    sub_cmd_description="Restore an incomplete, archived game to active status. (ADMIN ONLY)",
    default_member_permissions=interactions.Permissions.ADMINISTRATOR,
    dm_permission=False
)
@interactions.slash_option(
    name="name",
    description="Name of game to be restored",
    required=True,
    opt_type=interactions.OptionType.STRING,
    autocomplete=True
)
async def restore_train(ctx: interactions.SlashContext, name: str):
    guild_id = ctx.guild_id
    if guild_id in bd.active_trains:
        await ctx.send("There is already an active game in this server!")
        return True
    try:
        test_game = await bu.load_game(
            filepath=f"{bd.parent}/Guilds/{guild_id}/Trains/{name}", bot=bot, guild=ctx.guild
        )
    except FileNotFoundError:
        await ctx.send(content="Game name does not exist.")
        return True
    if not any(player.done is False for player in test_game.players):
        await ctx.send("You can not restore a completed game to active status.")
        return True

    test_game.active = True
    test_game.save_game(f"{bd.parent}/Guilds/{guild_id}/Trains/{test_game.name}")
    bd.active_trains[guild_id] = test_game
    await ctx.send(content=bd.pass_str)
    return False


@restore_train.autocomplete("name")
async def autocomplete(ctx: interactions.AutocompleteContext):
    games = listdir(f"{bd.parent}/Guilds/{ctx.guild_id}/Trains")
    choices = []
    for game in games:
        choices.append({"name": game, "value": game})
    await ctx.send(
        choices=choices
    )


@interactions.slash_command(
    name="train",
    sub_cmd_name="rules",
    sub_cmd_description="Display the rules for playing trains",
)
async def send_rules(ctx: interactions.SlashContext):
    rules_msg = await ctx.send(
        embeds=bu.gen_rules_embed(page=0, expired=False),
        components=[bu.prevpg_trainrules(), bu.nextpg_trainrules()]
    )
    channel = ctx.channel
    sent = bu.ListMsg(rules_msg.id, 0, ctx.guild, channel, "trainrules")
    bd.active_msgs.append(sent)
    _ = asyncio.create_task(
        bu.close_msg(sent, 300, ctx, rules_msg)
    )
    return False


@interactions.slash_command(
    name="response",
    sub_cmd_name="add",
    sub_cmd_description="Add a response",
    dm_permission=False
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
    description="Only respond if the message exactly matches the trigger (default true)",
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

    # Update responses
    if exact:
        bd.responses[guild_id] = bu.load_responses(f"{bd.parent}/Guilds/{guild_id}/responses.txt")
    else:
        bd.mentions[guild_id] = bu.load_responses(f"{bd.parent}/Guilds/{guild_id}/mentions.txt")

    if not error:
        await ctx.send(content=bd.pass_str)
    else:
        await ctx.send(content=bd.fail_str)
        return True


@interactions.slash_command(
    name="response",
    sub_cmd_name="remove",
    sub_cmd_description="Remove a response",
    dm_permission=False
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
    dm_permission=False
)
async def listrsps(ctx: interactions.SlashContext):
    resp_msg = await ctx.send(
        embeds=bu.gen_resp_list(ctx.guild, 0, False),
        components=[bu.prevpg_rsp(), bu.nextpg_rsp()]
    )
    channel = ctx.channel
    sent = bu.ListMsg(resp_msg.id, 0, ctx.guild, channel, "rsplist")
    bd.active_msgs.append(sent)
    _ = asyncio.create_task(
        bu.close_msg(sent, 300, ctx, resp_msg)
    )
    return False


@interactions.slash_command(
    name="mod",
    sub_cmd_name="deleterspdata",
    sub_cmd_description="Deletes ALL response data from the server",
    default_member_permissions=interactions.Permissions.ADMINISTRATOR,
    dm_permission=False
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
    dm_permission=False
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
    dm_permission=False
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
    dm_permission=False
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
    dm_permission=False
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
    dm_permission=False
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
    dm_permission=False
)
@interactions.slash_option(
    name="enable",
    description="True = Responses are limited, False = No limit",
    opt_type=interactions.OptionType.BOOLEAN,
    required=True
)
@interactions.slash_option(
    name="limit",
    description="Maximum number of responses per user (default 10)",
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
    dm_permission=False
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
    if not path.exists(f'{bd.parent}/Guilds/{guild.id}'):
        mkdir(f'{bd.parent}/Guilds/{guild.id}')
        mkdir(f'{bd.parent}/Guilds/{guild.id}/Trains')
        print(
            colored(f'{strftime("%Y-%m-%d %H:%M:%S")}:  ', 'white') +
            colored(f'Guild folder for guild {guild.id} created successfully.', 'green')
        )
        with open(f'{bd.parent}/Guilds/{int(guild.id)}/config.yaml', 'w') as f:
            yaml.dump(bd.default_config, f, Dumper=yaml.Dumper)
        bd.config[int(guild.id)] = bd.default_config
        bd.responses[int(guild.id)] = []
        bd.mentions[int(guild.id)] = []
    print(
        colored(f"{strftime(bd.date_format)}:  ", "white") + f"Added to guild {guild.id}."
    )


@interactions.listen()
async def on_ready():
    guilds = bot.guilds
    assert guilds, "Error connecting to Discord, no guilds listed."
    bu.load_fonts(f"{bd.parent}/Data")
    print(
        colored(strftime(bd.date_format) + " :  ", "white") + "Connected to the following guilds: " +
        colored(", ".join(guild.name for guild in guilds), "cyan")
    )
    for guild in guilds:
        bu.load_config(guild)

        # Load guild responses
        guild_id = int(guild.id)
        bd.mentions[guild_id] = bu.load_responses(f"{bd.parent}/Guilds/{guild_id}/mentions.txt")
        bd.responses[guild_id] = bu.load_responses(f"{bd.parent}/Guilds/{guild_id}/responses.txt")
        print(
            colored(f"{strftime(bd.date_format)}:  ", "white") +
            colored(f"Responses loaded for {guild.name}", "green")
        )

        # Load trains games
        for name in listdir(f"{bd.parent}/Guilds/{guild_id}/Trains"):
            try:
                game = await bu.load_game(
                    filepath=f"{bd.parent}/Guilds/{guild_id}/Trains/{name}", bot=bot, guild=guild, active_only=True
                )
                if game.active:
                    bd.active_trains[guild_id] = game
                    break
            except FileNotFoundError:
                try:
                    rmtree(f"{bd.parent}/Guilds/{guild_id}/Trains/{name}")
                except PermissionError:
                    pass
                print(
                    colored(strftime(bd.date_format) + " :  ", "white") +
                    colored(f"Invalid game \"{name}\" in guild {guild_id}, attempted delete.", "yellow")
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

    to_send = []
    done = False

    for i in bd.responses[message.guild.id]:
        if i.trig == message.content.lower():
            to_send.append(i.text)
            done = True
    if done:
        to_send = choice(to_send) if len(to_send) > 1 else to_send[0]
        await message.reply(to_send)
        return False

    if not bd.config[message.guild.id]["ALLOW_PHRASES"]:
        return False

    for i in bd.mentions[message.guild.id]:
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
        if msg.num != int(ctx.message.id):
            continue

        idx = bd.active_msgs.index(msg)
        game = msg.payload

        # Update page num
        image = None
        if ctx.custom_id == "prevpg_rsp":
            bd.active_msgs[idx].page -= 1
            embed = bu.gen_resp_list(ctx.guild, bd.active_msgs[idx].page, False)
            components = [bu.prevpg_rsp(), bu.nextpg_rsp()]
        elif ctx.custom_id == "nextpg_rsp":
            bd.active_msgs[idx].page += 1
            embed = bu.gen_resp_list(ctx.guild, bd.active_msgs[idx].page, False)
            components = [bu.prevpg_rsp(), bu.nextpg_rsp()]
        elif ctx.custom_id == "prevpg_trainrules":
            bd.active_msgs[idx].page -= 1
            embed = bu.gen_rules_embed(bd.active_msgs[idx].page, False)
            components = [bu.prevpg_trainrules(), bu.nextpg_trainrules()]
        elif ctx.custom_id == "nextpg_trainrules":
            bd.active_msgs[idx].page += 1
            embed = bu.gen_rules_embed(bd.active_msgs[idx].page, False)
            components = [bu.prevpg_trainrules(), bu.nextpg_trainrules()]
        elif ctx.custom_id == "prevpg_trainstats":
            await ctx.defer(edit_origin=True)
            bd.active_msgs[idx].page -= 1
            embed, image = game.gen_stats_embed(
                ctx=ctx, page=bd.active_msgs[idx].page, expired=False
            )
            components = [bu.prevpg_trainstats(), bu.nextpg_trainstats()]
        elif ctx.custom_id == "nextpg_trainstats":
            await ctx.defer(edit_origin=True)
            bd.active_msgs[idx].page += 1
            embed, image = game.gen_stats_embed(
                ctx=ctx, page=bd.active_msgs[idx].page, expired=False
            )
            components = [bu.prevpg_trainstats(), bu.nextpg_trainstats()]
        else:
            embed = None
            components = None
        await ctx.edit_origin(
            embeds=embed,
            components=components,
            file=image,
        )
        break


def main():
    init()
    disconnects = 0
    while disconnects < 3:
        try:
            bot.start()
        except gaierror:
            print(colored("Bot disconnected. Attempting reconnect in 10 seconds.", color="yellow"))
            sleep(10)
            disconnects += 1


if __name__ == "__main__":
    main()
