"""
Ben Samans
main.py
"""

from time import strftime
from colorama import init, Fore
from random import choice
import botdata as bd
import botutils as bu
import trains as tr
import anilist as al
import responses as rsp
import asyncio
import interactions
import json
from datetime import datetime
from os import listdir, mkdir, path, makedirs
import io
from shutil import copytree, ignore_patterns


bot = interactions.Client(
    token=bd.token,
    intents=interactions.Intents.DEFAULT | interactions.Intents.MESSAGE_CONTENT | interactions.Intents.GUILDS,
    sync_interactions=True,
    delete_unused_application_cmds=True,
    debug_scope=895549687417958410
)


@interactions.slash_command(
    name="anilist",
    sub_cmd_name="link",
    sub_cmd_description="Link your discord profile to an anilist profile",
    dm_permission=True
)
@interactions.slash_option(
    name="url",
    description="Anilist profile link (e.g. https://anilist.co/User/[name]",
    required=True,
    opt_type=interactions.OptionType.STRING
)
async def link_anilist(ctx: interactions.SlashContext, url: str):
    username = al.username_from_url(url)
    if username is None:
        await ctx.send(content="Could not find anilist profile, please check URL!")
        return True
    anilist_user_id = al.query_user_id(username)
    if anilist_user_id is None:
        await ctx.send(content="Could not find anilist profile, please check URL!")
        return True

    bd.linked_profiles[ctx.author_id] = anilist_user_id
    with open(f"{bd.parent}/Data/linked_profiles.json", "w") as f:
        json.dump(bd.linked_profiles, f, separators=(",", ":"))
    await ctx.send(content=bd.pass_str)
    return False


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
    description="Trains game name",
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
    river_ring: int = 1

    # Return errors if game is active or invalid name/width/height
    if ctx.guild_id in bd.active_trains:
        await ctx.send(content=f"The game \"{bd.active_trains[ctx.guild_id].name}\" is already active in this server.")
        return True
    if path.exists(f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{name}"):
        await ctx.send(content="Name already exists!")
        return True

    async def add_trains_player(m: interactions.Member, t: str):
        dm = await m.fetch_dm(force=False)
        starting_anilist = await al.query_user_animelist(bd.linked_profiles[m.id])
        least_watched_genre = await al.query_user_genres(bd.linked_profiles[m.id])
        players.append(tr.TrainPlayer(
            member=m, tag=t, dmchannel=dm, starting_anilist=starting_anilist,
            least_watched_genre=least_watched_genre)
        )

    # Create player list and tags
    members = await bu.get_members_from_str(ctx.guild, players)
    players: list = []
    tags: list = bu.get_player_tags(members)

    tasks: list = []
    for member, tag in zip(members, tags):
        if member.id not in bd.linked_profiles:
            await ctx.send(
                content=f"Could not create game, <@{member.id}> must link their anilist profile! (/anilist link)"
            )
            return True

        tasks.append(asyncio.create_task(
            add_trains_player(m=member, t=tag)
        ))
    await asyncio.gather(*tasks)

    # Return error if player list is empty
    if not players:
        await ctx.send(content="No valid players specified.")
        return True

    # Create game object and set parameters
    date = datetime.now().strftime(bd.date_format)
    gameid = int(datetime.now().strftime("%Y%m%d%H%M%S"))

    game = tr.TrainGame(
        name=name,
        date=date,
        players=players,
        board=None,
        gameid=gameid,
        active=True,
        size=(width + 2*river_ring, height + 2*river_ring)  # Add space on board for river border
    )
    try:
        game.gen_trains_board(
            play_area_size=(width, height), river_ring=river_ring
        )
        game.gen_player_locations(river_ring=river_ring)
    except game.BoardGenError as e:
        await ctx.send(content=str(e))
        return True

    try:
        mkdir(f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{name}")
    except OSError:
        await ctx.send(content="Invalid name! Game must not contain the following characters: / \\ : * ? < > |")
        return True

    # Push updates to player boards
    await ctx.send(embed=tr.train_game_embed(ctx=ctx, game=game))
    await game.update_boards_after_create(ctx=ctx)
    return False


@interactions.slash_command(
    name="trains",
    sub_cmd_name="viewshop",
    sub_cmd_description="View the shop for the active trains game.",
    dm_permission=False
)
async def view_trains_shop(ctx: interactions.SlashContext):
    if ctx.guild_id not in bd.active_trains:
        await ctx.send(content="There is no active game! To make one, use /trains newgame", ephemeral=True)
        return True

    game = bd.active_trains[ctx.guild_id]
    await ctx.send(content="\n".join([item.shop_entry() for item in game.shop.values()]))


@interactions.slash_command(
    name="trains",
    sub_cmd_name="buy",
    sub_cmd_description="Buy an item from a shop/city.",
    dm_permission=False
)
@interactions.slash_option(
    name="name",
    description="Name of the item to purchase.",
    required=True,
    opt_type=interactions.OptionType.STRING,
    choices=[interactions.SlashCommandChoice(name=itemname, value=itemname) for itemname in tr.default_shop()]
)
@interactions.slash_option(
    name="showinfo",
    description="Information about stock used for purchase.",
    required=True,
    opt_type=interactions.OptionType.STRING,
)
async def buy_shop_item(ctx: interactions.SlashContext, name: str, showinfo: str):
    if ctx.guild_id not in bd.active_trains:
        await ctx.send(content="There is no active game! To make one, use /trains newgame", ephemeral=True)
        return True

    game = bd.active_trains[ctx.guild_id]

    err = game.buy_item(itemname=name, showinfo=showinfo, ctx=ctx)
    if err:
        await ctx.send(content=bd.fail_str)
        return True

    await ctx.send(content=bd.pass_str)


@interactions.slash_command(
    name="trains",
    sub_cmd_name="inventory",
    sub_cmd_description="View your inventory for the active trains game.",
    dm_permission=False
)
async def view_trains_inventory(ctx: interactions.SlashContext):
    if ctx.guild_id not in bd.active_trains:
        await ctx.send(content="There is no active game! To make one, use /trains newgame", ephemeral=True)
        return True

    game = bd.active_trains[ctx.guild_id]

    player_idx, player = game.get_player(ctx.author_id)
    if player is None:
        await ctx.send(content="You are not a player in this game.", ephemeral=True)

    inv_str = "\n".join([item.inv_entry() for item in player.inventory.values()])
    if inv_str:
        await ctx.send(content=inv_str, ephemeral=True)
    else:
        await ctx.send(content="Your inventory is empty!", ephemeral=True)
    return False


@interactions.slash_command(
    name="trains",
    sub_cmd_name="use",
    sub_cmd_description="Use a item in your inventory.",
    dm_permission=False
)
@interactions.slash_option(
    name="item",
    description="Specify which item to use",
    required=True,
    opt_type=interactions.OptionType.STRING,
    choices=[interactions.SlashCommandChoice(name="Bucket", value="Bucket")]
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
async def trains_use_bucket(ctx: interactions.SlashContext, item: str, row: int, column: int):
    if ctx.guild_id not in bd.active_trains:
        await ctx.send(content="There is no active game! To make one, use /trains newgame", ephemeral=True)
        return True

    game = bd.active_trains[ctx.guild_id]

    if item == "Bucket":
        err = game.use_bucket(ctx=ctx, row=row, col=column)
        if err:
            await ctx.send(content=bd.fail_str)
            return True
        await game.update_boards_after_shot(
            ctx=ctx, row=row, column=column
        )


@interactions.slash_command(
    name="trains",
    sub_cmd_name="end",
    sub_cmd_description="Command for testing. Shows score screen.",
    dm_permission=False,
)
async def end_trains(ctx: interactions.SlashContext):
    await ctx.defer()
    game: tr.TrainGame = bd.active_trains[ctx.guild_id]
    await game.calculate_player_scores(ctx=ctx)
    embed, image = game.gen_score_embed(ctx=ctx, page=0, expired=False)
    score_msg = await ctx.send(
        embed=embed,
        file=image,
        components=[bu.nextpg_button(), bu.prevpg_button()]
    )
    sent = bu.ListMsg(
        num=score_msg.id, page=0, guild=ctx.guild, channel=ctx.channel, msg_type="trainscores", payload=game
    )
    bd.active_msgs.append(sent)
    _ = asyncio.create_task(
        bu.close_msg(sent, 300, ctx, score_msg)
    )


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
    name="link",
    description="Anilist link of show",
    required=True,
    opt_type=interactions.OptionType.STRING,
)
@interactions.slash_option(
    name="info",
    description="Time/stock information",
    required=True,
    opt_type=interactions.OptionType.STRING
)
async def record_shot(ctx: interactions.SlashContext, row: int, column: int, link: str, info: str):
    await ctx.defer(ephemeral=False)
    if ctx.guild_id not in bd.active_trains:
        await ctx.send(content="There is no active game! To make one, use /trains newgame", ephemeral=True)
        return True

    game = bd.active_trains[ctx.guild_id]

    # This is bad and needs to be reworked
    copytree(
        f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{game.name}",
        f"{bd.parent}/Guilds/{ctx.guild_id}/TrainBackups/[BACKUP] {game.name}",
        dirs_exist_ok=True,
        ignore=ignore_patterns("*.png")
    )
    # Get player, validate shot
    show_id = al.anime_id_from_url(url=link)
    if show_id is None:
        await ctx.send(content="Could not find show, please check anilist URL!")
        return True

    sender_idx, player = game.get_player(int(ctx.author_id))
    if not game.is_valid_shot(player, row, column):
        await ctx.send(content=bd.fail_str)
        return True

    # Fetch anilist show information if it isn't already cached
    if show_id not in game.known_shows:
        show_info = al.query_media(media_id=show_id)
        if show_info is None:
            await ctx.send(content="Error connecting to anilist, please check URL and try again.")
            return True
        game.known_shows[show_id] = show_info

    # Update board, player rails
    shot = tr.TrainShot(row=row, col=column, show_id=show_id, info=info, time=datetime.now().strftime(bd.date_format))
    game.update_player_stats_after_shot(sender_idx=sender_idx, player=player, shot=shot)

    # Save/update games
    await ctx.send(content=bd.pass_str)
    await game.update_boards_after_shot(
        ctx=ctx, row=row, column=column
    )
    if not game.active:
        await game.calculate_player_scores(ctx=ctx)
        embed, image = game.gen_score_embed(ctx=ctx, page=0, expired=False)
        score_msg = await ctx.send(
            embed=embed,
            file=image,
            components=[bu.nextpg_button(), bu.prevpg_button()]
        )
        sent = bu.ListMsg(
            num=score_msg.id, page=0, guild=ctx.guild, channel=ctx.channel, msg_type="trainscores", payload=game
        )
        bd.active_msgs.append(sent)
        _ = asyncio.create_task(
            bu.close_msg(sent, 300, ctx, score_msg)
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
    if ctx.guild_id not in bd.active_trains:
        await ctx.send(content="There is no active game! To make one, use /trains newgame", ephemeral=True)
        return True

    game = bd.active_trains[ctx.guild_id]

    # This is bad and needs to be reworked
    copytree(
        f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{game.name}",
        f"{bd.parent}/Guilds/{ctx.guild_id}/TrainBackups/[BACKUP] {game.name}",
        dirs_exist_ok=True,
        ignore=ignore_patterns("*.png")
    )

    sender_idx, player = game.get_player(ctx.author_id)
    if not player.shots:
        await ctx.send(content="You have not taken any shots yet!", ephemeral=True)
        return True

    # Delete last shot from record, update active player status
    shot = game.players[sender_idx].shots[-1]

    if (shot.row, shot.col) in player.shops_used:
        await ctx.send(content="You have bought an item at this shop, can not undo shot.")
        return True

    game.update_player_stats_after_shot(sender_idx=sender_idx, player=player, undo=True, shot=shot)

    await ctx.send(content=bd.pass_str)
    # Save/update games
    await game.update_boards_after_shot(
        ctx=ctx, row=shot.row, column=shot.col
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
        if ctx.guild_id not in bd.active_trains:
            await ctx.send(content="No active game found, please specify a game name.")
            return True
        game = bd.active_trains[ctx.guild_id]

    else:
        try:
            game = await tr.load_game(
                filepath=f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{name}", bot=bot, guild=ctx.guild
            )
        except FileNotFoundError:
            await ctx.send(content="Game name does not exist.")
            return True
        except TypeError or ValueError:
            return True
    await ctx.defer()

    # Send stats
    embed, image = game.gen_stats_embed(ctx=ctx, page=0, expired=False)

    stats_msg = await ctx.send(embed=embed, file=image, components=[bu.nextpg_button(), bu.prevpg_button()])
    sent = bu.ListMsg(
        num=stats_msg.id, page=0, guild=ctx.guild, channel=ctx.channel, msg_type="trainstats", payload=game
    )
    bd.active_msgs.append(sent)
    _ = asyncio.create_task(
        bu.close_msg(sent, 300, ctx, stats_msg)
    )


@trains_stats.autocomplete("name")
async def autocomplete(ctx: interactions.AutocompleteContext):
    games: list = listdir(f"{bd.parent}/Guilds/{ctx.guild_id}/Trains")
    games = [gamename for gamename in games if ctx.input_text in gamename]
    choices = list(map(bu.autocomplete_filter, games))
    if len(choices) > 25:
        choices = choices[:24]
    await ctx.send(choices=choices)


@interactions.slash_command(
    name="trains",
    sub_cmd_name="board",
    sub_cmd_description="View your train board for the active game.",
    dm_permission=False,
)
async def show_trains_board(ctx: interactions.SlashContext):
    if ctx.guild_id not in bd.active_trains:
        await ctx.send(content="No active game found.", ephemeral=True)
        return True

    game = bd.active_trains[ctx.guild_id]
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
    if ctx.guild_id not in bd.active_trains:
        await ctx.send(content="There is no active game! To make one, use /trains newgame", ephemeral=True)
        return True

    game = bd.active_trains[ctx.guild_id]

    if keep_files:
        game.active = False
        game.save_game(f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{game.name}")
    else:
        tr.del_game_files(guild_id=ctx.guild_id, game_name=game.name)
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
    if ctx.guild_id in bd.active_trains:
        await ctx.send("There is already an active game in this server!")
        return True
    try:
        test_game = await tr.load_game(
            filepath=f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{name}", bot=bot, guild=ctx.guild
        )
    except FileNotFoundError:
        await ctx.send(content="Game name does not exist.")
        return True
    if not any(player.done is False for player in test_game.players):
        await ctx.send("You can not restore a completed game to active status.")
        return True

    test_game.active = True
    test_game.save_game(f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{test_game.name}")
    bd.active_trains[ctx.guild_id] = test_game
    await ctx.send(content=bd.pass_str)
    return False


@restore_train.autocomplete("name")
async def autocomplete(ctx: interactions.AutocompleteContext) -> None:
    games = listdir(f"{bd.parent}/Guilds/{ctx.guild_id}/Trains")
    games = [gamename for gamename in games if ctx.input_text in gamename]
    choices = list(map(bu.autocomplete_filter, games))
    if len(choices) > 25:
        choices = choices[:24]
    await ctx.send(choices=choices)


@interactions.slash_command(
    name="train",
    sub_cmd_name="rules",
    sub_cmd_description="Display the rules for playing trains",
)
@interactions.slash_option(
    name="page",
    description="Specify which page of the rules to view.",
    opt_type=interactions.OptionType.INTEGER,
    required=False
)
async def send_rules(ctx: interactions.SlashContext, page: int = 1):
    rules_msg = await ctx.send(
        embeds=bu.gen_rules_embed(page=page, expired=False),
        components=[bu.nextpg_button(), bu.prevpg_button()]
    )
    channel = ctx.channel
    sent = bu.ListMsg(rules_msg.id, page, ctx.guild, channel, "trainrules")
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
    description="Only respond if the message is exactly the trigger phrase",
    required=True,
    opt_type=interactions.OptionType.BOOLEAN,
)
async def add_response(ctx: interactions.SlashContext, trigger: str, response: str, exact: bool):

    # Config permission checks
    if not bd.config[ctx.guild_id]["ALLOW_PHRASES"] and not exact:
        await ctx.send(
            content=f"The server does not allow for phrase-based responses.",
            ephemeral=True
        )
        return True
    if bd.config[ctx.guild_id]["LIMIT_USER_RESPONSES"]:
        user_rsps = 0
        for existing_response in bd.responses[ctx.guild_id]:
            if existing_response.user_id == int(ctx.author.id):
                user_rsps += 1
        if user_rsps >= bd.config[ctx.guild_id]["MAX_USER_RESPONSES"]:
            await ctx.send(
                content=f"You currently have the maximum of {bd.config[ctx.guild_id]['MAX_USER_RESPONSES']} responses.",
                ephemeral=True
            )
            return True

    error = rsp.add_response(ctx.guild_id, rsp.Response(exact, trigger.lower(), response, int(ctx.author.id)))

    # Update responses
    bd.responses[ctx.guild_id] = rsp.load_responses(f"{bd.parent}/Guilds/{ctx.guild_id}/responses.json")

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
    opt_type=interactions.OptionType.STRING,
    autocomplete=True
)
@interactions.slash_option(
    name="response",
    description="Response text to remove if multiple exist on the same trigger, defaults to the first response",
    required=False,
    opt_type=interactions.OptionType.STRING,
    autocomplete=True
)
@interactions.slash_option(
    name="exact",
    description="If the trigger to remove is an exact trigger (default true)",
    required=False,
    opt_type=interactions.OptionType.BOOLEAN,
)
async def remove_response(ctx: interactions.SlashContext, trigger: str = "", response: str = "", exact: bool = None):
    # Config permission checks
    
    if bd.config[ctx.guild_id]["USER_ONLY_DELETE"] and \
            rsp.get_resp(ctx.guild_id, trigger, response, exact).user_id != ctx.author.id:
        await ctx.send(
            content=f"The server settings do not allow you to delete other people\'s responses.",
            ephemeral=True
        )
        return True

    error = rsp.rmv_response(ctx.guild_id, rsp.Response(exact=exact, trig=trigger.lower(), text=response))
    if not error:
        await ctx.send(content=bd.pass_str)
    else:
        await ctx.send(content=bd.fail_str)
        return True

    # Update responses
    bd.responses[ctx.guild_id] = rsp.load_responses(f"{bd.parent}/Guilds/{ctx.guild_id}/responses.json")


@remove_response.autocomplete("trigger")
async def autocomplete(ctx: interactions.AutocompleteContext):
    trigs: list = []
    # Add autocomplete options if they match input text, remove duplicates. 25 maximum values (discord limit)
    for response in bd.responses[ctx.guild_id]:
        if response.trig not in trigs and ctx.input_text in response.trig:
            trigs.append(response.trig)
    choices = list(map(bu.autocomplete_filter, trigs))
    if len(choices) > 25:
        choices = choices[0:24]
    await ctx.send(choices=choices)


@remove_response.autocomplete("response")
async def autocomplete(ctx: interactions.AutocompleteContext):
    # Add autocomplete response options for the specified trigger.
    responses = [
        response.text for response in bd.responses[ctx.guild_id]
        if response.trig == ctx.kwargs.get("trigger")
        ]
    choices = list(map(bu.autocomplete_filter, responses))
    if len(choices) > 25:
        choices = choices[0:24]
    await ctx.send(choices=choices)


@interactions.slash_command(
    name="listresponses",
    description="Show list of all responses for the server",
    dm_permission=False
)
@interactions.slash_option(
    name="page",
    description="Specify which page to view.",
    opt_type=interactions.OptionType.INTEGER,
    required=False
)
async def listrsps(ctx: interactions.SlashContext, page: int = 1):
    resp_msg = await ctx.send(
        embeds=rsp.gen_resp_list(ctx.guild, page, False),
        components=[bu.nextpg_button(), bu.prevpg_button()]
    )
    channel = ctx.channel
    sent = bu.ListMsg(resp_msg.id, page, ctx.guild, channel, "rsplist")
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
    
    f = open(f"{bd.parent}/Guilds/{ctx.guild_id}/responses.json", "w")
    f.close()
    bd.responses[ctx.guild_id] = []
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
    description="Only respond if the message is exactly the trigger phrase",
    required=True,
    opt_type=interactions.OptionType.BOOLEAN,
)
async def mod_add(ctx: interactions.SlashContext, trigger: str, response: str, exact: bool):

    error = rsp.add_response(ctx.guild_id, rsp.Response(exact, trigger.lower(), response, int(ctx.author.id)))
    if not error:
        await ctx.send(content=bd.pass_str)
    else:
        await ctx.send(content=bd.fail_str)
        return True

    # Update responses
    bd.responses[ctx.guild_id] = rsp.load_responses(f"{bd.parent}/Guilds/{ctx.guild_id}/responses.json")


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
    opt_type=interactions.OptionType.STRING,
    autocomplete=True
)
@interactions.slash_option(
    name="response",
    description="Response text to remove if multiple exist on the same trigger, defaults to the first response",
    required=False,
    opt_type=interactions.OptionType.STRING,
    autocomplete=True
)
@interactions.slash_option(
    name="exact",
    description="If the trigger to remove is an exact trigger (default true)",
    required=False,
    opt_type=interactions.OptionType.BOOLEAN,
)
async def mod_remove(ctx: interactions.SlashContext, trigger: str = "", response: str = "", exact: bool = True):
    
    error = rsp.rmv_response(ctx.guild_id, rsp.Response(exact, trigger.lower(), response))
    if not error:
        await ctx.send(content=bd.pass_str)
    else:
        await ctx.send(content=bd.fail_str)
        return True

    # Update responses
    bd.responses[ctx.guild_id] = rsp.load_responses(f"{bd.parent}/Guilds/{ctx.guild_id}/responses.json")


@mod_remove.autocomplete("trigger")
async def autocomplete(ctx: interactions.AutocompleteContext):
    trigs: list = []
    # Add autocomplete options if they match input text, remove duplicates. 25 maximum values (discord limit)
    for response in bd.responses[ctx.guild_id]:
        if response.trig not in trigs and ctx.input_text in response.trig:
            trigs.append(response.trig)
    choices = list(map(bu.autocomplete_filter, trigs))
    if len(choices) > 25:
        choices = choices[0:24]
    await ctx.send(choices=choices)


@mod_remove.autocomplete("response")
async def autocomplete(ctx: interactions.AutocompleteContext):
    # Add autocomplete response options for the specified trigger.
    responses = [
        response.text for response in bd.responses[ctx.guild_id]
        if response.trig == ctx.kwargs.get("trigger")
        ]
    choices = list(map(bu.autocomplete_filter, responses))
    if len(choices) > 25:
        choices = choices[0:24]
    await ctx.send(choices=choices)


@interactions.slash_command(
    name="config",
    sub_cmd_name="reset",
    sub_cmd_description="Resets ALL server settings to default.",
    default_member_permissions=interactions.Permissions.ADMINISTRATOR,
    dm_permission=False
)
async def cfg_reset(ctx: interactions.SlashContext):
    
    with open(f"{bd.parent}/Guilds/{ctx.guild_id}/config.json", "w") as f:
        json.dump(bd.default_config, f, indent=4)
    bd.config[ctx.guild_id] = bd.default_config
    await ctx.send(content=bd.pass_str)


@interactions.slash_command(
    name="config",
    sub_cmd_name="view",
    sub_cmd_description="Views the current server settings.",
    default_member_permissions=interactions.Permissions.ADMINISTRATOR,
    dm_permission=False
)
async def cfg_view(ctx: interactions.SlashContext):
    
    await ctx.send(
        content=f"Allow Phrases: {bd.config[ctx.guild_id]['ALLOW_PHRASES']}\n"
        f"Limit Responses: {bd.config[ctx.guild_id]['LIMIT_USER_RESPONSES']}\n"
        f"Response Limit # (Only if Limit Responses is True): {bd.config[ctx.guild_id]['MAX_USER_RESPONSES']}\n"
        f"Restrict User Response Deleting: {bd.config[ctx.guild_id]['USER_ONLY_DELETE']}\n"
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
    
    bd.config[ctx.guild_id]["USER_ONLY_DELETE"] = not enable
    with open(f"{bd.parent}/Guilds/{ctx.guild_id}/config.json", "w") as f:
        json.dump(bd.config[ctx.guild_id], f, indent=4)
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
    
    if limit < 1:
        limit = 1
    bd.config[ctx.guild_id]["LIMIT_USER_RESPONSES"] = enable
    bd.config[ctx.guild_id]["MAX_USER_RESPONSES"] = limit
    with open(f"{bd.parent}/Guilds/{ctx.guild_id}/config.json", "w") as f:
        json.dump(bd.config[ctx.guild_id], f, indent=4)
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
    
    bd.config[ctx.guild_id]["ALLOW_PHRASES"] = enable
    with open(f"{bd.parent}/Guilds/{ctx.guild_id}/config.json", "w") as f:
        json.dump(bd.config[ctx.guild_id], f, indent=4)
    await ctx.send(content=bd.pass_str)


@interactions.listen()
async def on_guild_join(event: interactions.api.events.GuildJoin):
    guild = event.guild
    if not path.exists(f'{bd.parent}/Guilds/{guild.id}'):
        makedirs(f'{bd.parent}/Guilds/{guild.id}/Trains')
        print(
            Fore.WHITE + '{strftime("%Y-%m-%d %H:%M:%S")}:  ' +
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
    await bu.init_guilds(guilds=guilds, bot=bot)
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
                embed = rsp.gen_resp_list(ctx.guild, bd.active_msgs[idx].page, False)

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
