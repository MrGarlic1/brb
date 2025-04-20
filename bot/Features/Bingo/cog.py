import interactions
import Features.Bingo.data as bi
import Core.anilist as al
import Core.botdata as bd
import asyncio
from os import path, listdir, mkdir
import Core.botutils as bu
from shutil import copytree, ignore_patterns
from datetime import datetime


class Bingo(interactions.Extension):
    @interactions.slash_command(
        name="bingo",
        sub_cmd_name="newgame",
        sub_cmd_description="Create a new bingo game",
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
    async def create_bingo(
            self, ctx: interactions.SlashContext, name: str, players: str
    ):
        await ctx.defer()

        # Return errors if game is active or invalid name
        if ctx.guild_id in bd.active_bingos:
            await ctx.send(
                content=f"The game \"{bd.active_bingos[ctx.guild_id].name}\" is already active in this server."
            )
            return True
        if path.exists(f"{bd.parent}/Guilds/{ctx.guild_id}/Bingo/{name}"):
            await ctx.send(content="Name already exists!")
            return True

        async def add_bingo_player(m: interactions.Member):
            dm = await m.fetch_dm(force=False)
            starting_anilist = await al.query_user_animelist(bd.linked_profiles[m.id])

            players.append(bi.BingoPlayer(
                member=m, dmchannel=dm, starting_anilist=starting_anilist,
                )
            )

        # Create player list and tags
        members = await bu.get_members_from_str(ctx.guild, players)
        players: list = []

        tasks: list = []
        for member in members:
            if member.id not in bd.linked_profiles:
                await ctx.send(
                    content=f"Could not create game, <@{member.id}> must link their anilist profile! (/anilist link)"
                )
                return True

            tasks.append(asyncio.create_task(
                add_bingo_player(m=member)
            ))
        await asyncio.gather(*tasks)

        # Return error if player list is empty
        if not players:
            await ctx.send(content="No valid players specified.")
            return True

        # Create game object and set parameters
        date = datetime.now().strftime(bd.date_format)
        gameid = int(datetime.now().strftime("%Y%m%d%H%M%S"))

        game = bi.BingoGame(
            name=name,
            date=date,
            players=players,
            gameid=gameid,
            active=True,
        )

        try:
            mkdir(f"{bd.parent}/Guilds/{ctx.guild_id}/Bingo/{name}")
        except OSError:
            await ctx.send(content="Invalid name! Game must not contain the following characters: / \\ : * ? < > |")
            return True

        # Push updates to player boards
        await ctx.send(embed=bi.bingo_game_embed(ctx=ctx, game=game))
        game.update_boards_after_create(ctx=ctx)
        return False

    @interactions.slash_command(
        name="bingo",
        sub_cmd_name="end",
        sub_cmd_description="Command for testing. Shows score screen.",
        dm_permission=False,
    )
    async def end_bingo(self, ctx: interactions.SlashContext):
        await ctx.defer()
        await ctx.send(content=bd.pass_str)

    @interactions.slash_command(
        name="bingo",
        sub_cmd_name="shot",
        sub_cmd_description="Make a bingo shot",
        dm_permission=False
    )
    @interactions.slash_option(
        name="link",
        description="Anilist link of show/character",
        required=True,
        opt_type=interactions.OptionType.STRING,
    )
    @interactions.slash_option(
        name="tag",
        description="Bingo tag to shoot for",
        required=True,
        opt_type=interactions.OptionType.STRING
    )
    @interactions.slash_option(
        name="info",
        description="Time/stock information",
        required=True,
        opt_type=interactions.OptionType.STRING
    )
    async def record_shot(self, ctx: interactions.SlashContext, link: str, info: str, tag: str):
        await ctx.defer(ephemeral=False)
        if ctx.guild_id not in bd.active_bingos:
            await ctx.send(content="There is no active game! To make one, use /bingo newgame", ephemeral=True)
            return True

        game = bd.active_bingos[ctx.guild_id]

        # This is bad and needs to be reworked
        copytree(
            f"{bd.parent}/Guilds/{ctx.guild_id}/Bingo/{game.name}",
            f"{bd.parent}/Guilds/{ctx.guild_id}/BingoBackups/[BACKUP] {game.name}",
            dirs_exist_ok=True,
            ignore=ignore_patterns("*.png")
        )
        # Get player, validate shot

        sender_idx, player = game.get_player(int(ctx.author_id))

        if player is None:
            await ctx.send("You are not in this bingo game!")
            return True

        if any(shot.tag == tag for shot in player.shots):
            await ctx.send("You have already shot for this tag. Please select a different tag and try again.")
            return True

        shot = bi.BingoShot(
            anilist_id=0, tag=tag, time=datetime.now().strftime(bd.date_format), info=info
        )
        shot_type = shot.get_shot_type()
        if not shot_type:
            await ctx.send(content="Invalid tag specified. Please check the tag and try again.")
            return True

        if shot_type == "character":
            anilist_id = al.anilist_id_from_url(url=link, is_character=True)
        else:
            anilist_id = al.anilist_id_from_url(url=link)
        if anilist_id is None:
            await ctx.send(content="Could not find show, please check anilist URL!")
            return True

        # Fetch anilist information if it isn't already cached
        if anilist_id not in game.known_entries:
            if shot_type == "character":
                anilist_info = al.query_character(character_id=anilist_id)
            else:
                anilist_info = al.query_media(media_id=anilist_id)

            if anilist_info is None:
                await ctx.send(content="Error connecting to anilist, please check URL and try again.")
                return True
            game.known_entries[anilist_id] = anilist_info

        poll_msg = None

        if shot_type == "character":
            await ctx.send(content="Sending poll.", ephemeral=True)
            poll_msg = await ctx.channel.send(
                content=f"Does this character fill the tag [{shot.tag}]?\n\n*(Poll open for 2 hours)*"
            )
            await poll_msg.add_reaction(emoji="🔺")
            await poll_msg.add_reaction(emoji="🔻")
            await asyncio.sleep(7200)

        valid = await shot.is_valid(
            anilist_info=game.known_entries[anilist_id],
            starting_anilist=player.starting_anilist,
            poll_msg=poll_msg
        )

        if not valid:
            await ctx.send(
                "Show/Character does not meet requirements! Please choose a different tag.", ephemeral=True
            )
            return True

        # Update board, player rails

        hit_tile = player.find_tag(tag)

        if hit_tile:
            shot.hit = True
            player.board[hit_tile].hit = True
            await ctx.send(content=f"🟩{bi.col_emojis[hit_tile[0] - 1]}{bi.row_emojis[hit_tile[1] - 1]}")
            if player.has_bingo():
                player.done = True
                game.active = False
        else:
            await ctx.send(content="🟥")

        game.update_game_after_shot(ctx=ctx, shot=shot, player_idx=sender_idx, hit_tile=hit_tile)

        if not game.active:
            embed, image = game.gen_score_embed(ctx=ctx, page=0, expired=False)
            score_msg = await ctx.send(
                embed=embed,
                file=image,
                components=[bu.nextpg_button(), bu.prevpg_button()]
            )
            sent = bu.ListMsg(
                num=score_msg.id, page=0, guild=ctx.guild, channel=ctx.channel, msg_type="bingoscores", payload=game
            )
            bd.active_msgs.append(sent)
            _ = asyncio.create_task(
                bu.close_msg(sent, 300, ctx)
            )

    @record_shot.autocomplete("tag")
    async def autocomplete(self, ctx: interactions.AutocompleteContext):
        tags = bi.bingo_tags + bi.character_tags + bi.season_tags + bi.episode_tags
        tags = [tag for tag in tags if ctx.input_text.lower() in tag.lower()]
        choices = list(map(bu.autocomplete_filter, tags))
        if len(choices) > 25:
            choices = choices[:24]
        await ctx.send(choices=choices)

    @interactions.slash_command(
        name="bingo",
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
    async def bingo_stats(self, ctx: interactions.SlashContext, name: str = None):
        # Logic to get game or return error if no game found
        if name is None:
            if ctx.guild_id not in bd.active_bingos:
                await ctx.send(content="No active game found, please specify a game name.")
                return True
            game = bd.active_bingos[ctx.guild_id]

        else:
            try:
                game = await bi.load_bingo_game(
                    filepath=f"{bd.parent}/Guilds/{ctx.guild_id}/Bingo/{name}", guild=ctx.guild
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
            num=stats_msg.id, page=0, guild=ctx.guild, channel=ctx.channel, msg_type="bingostats", payload=game
        )
        bd.active_msgs.append(sent)
        _ = asyncio.create_task(
            bu.close_msg(sent, 300, ctx)
        )

    @bingo_stats.autocomplete("name")
    async def autocomplete(self, ctx: interactions.AutocompleteContext):
        games: list = listdir(f"{bd.parent}/Guilds/{ctx.guild_id}/Bingo")
        games = [gamename for gamename in games if ctx.input_text in gamename]
        choices = list(map(bu.autocomplete_filter, games))
        if len(choices) > 25:
            choices = choices[:24]
        await ctx.send(choices=choices)

    @interactions.slash_command(
        name="bingo",
        sub_cmd_name="board",
        sub_cmd_description="View the bingo boards for the active game.",
        dm_permission=False,
    )
    async def show_bingo_board(self, ctx: interactions.SlashContext):
        if ctx.guild_id not in bd.active_bingos:
            await ctx.send(content="No active game found.", ephemeral=True)
            return True

        game = bd.active_bingos[ctx.guild_id]
        player_idx, player = game.get_player(ctx.author_id)

        if not player:
            await ctx.send(content="You are not a player in this game.", ephemeral=True)
            return True

        embed, image = game.gen_board_embed(page=0, sender_idx=player_idx, expired=False)

        board_msg = await ctx.send(
            embed=embed,
            file=image,
            components=[bu.nextpg_button(), bu.prevpg_button()],
            ephemeral=True
        )
        sent = bu.ListMsg(
            num=board_msg.id, page=0, guild=ctx.guild, channel=ctx.channel, msg_type="bingoboard",
            payload=game
        )
        bd.active_msgs.append(sent)
        _ = asyncio.create_task(
            bu.close_msg(sent, 300, ctx)
        )
        return False

    @interactions.slash_command(
        name="mod",
        sub_cmd_name="deletebingo",
        sub_cmd_description="Remove the active bingo game. (ADMIN ONLY)",
        default_member_permissions=interactions.Permissions.ADMINISTRATOR,
        dm_permission=False
    )
    @interactions.slash_option(
        name="keep_files",
        description="Choose whether to archive or completely delete the active game's files",
        required=True,
        opt_type=interactions.OptionType.BOOLEAN,
    )
    async def delete_bingo_game(self, ctx: interactions.SlashContext, keep_files: bool):
        await ctx.defer()
        if ctx.guild_id not in bd.active_bingos:
            await ctx.send(content="There is no active game! To make one, use /bingo newgame", ephemeral=True)
            return True

        game = bd.active_bingos[ctx.guild_id]

        if keep_files:
            game.active = False
            game.save_game(f"{bd.parent}/Guilds/{ctx.guild_id}/Bingo/{game.name}")
        else:
            bu.del_game_files(guild_id=ctx.guild_id, game_name=game.name, game_type="Bingo")
        del bd.active_bingos[ctx.guild_id]
        await ctx.send(content=bd.pass_str)
        return False

    @interactions.slash_command(
        name="mod",
        sub_cmd_name="restorebingo",
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
    async def restore_bingo(self, ctx: interactions.SlashContext, name: str):
        if ctx.guild_id in bd.active_bingos:
            await ctx.send("There is already an active game in this server!")
            return True
        try:
            test_game = await bi.load_bingo_game(
                filepath=f"{bd.parent}/Guilds/{ctx.guild_id}/Bingo/{name}", guild=ctx.guild
            )
        except FileNotFoundError:
            await ctx.send(content="Game name does not exist.")
            return True
        if any(player.done is True for player in test_game.players):
            await ctx.send("You can not restore a completed game to active status.")
            return True

        test_game.active = True
        test_game.save_game(f"{bd.parent}/Guilds/{ctx.guild_id}/Bingo/{test_game.name}")
        bd.active_bingos[ctx.guild_id] = test_game
        await ctx.send(content=bd.pass_str)
        return False

    @restore_bingo.autocomplete("name")
    async def autocomplete(self, ctx: interactions.AutocompleteContext) -> None:
        games = listdir(f"{bd.parent}/Guilds/{ctx.guild_id}/Bingo")
        games = [gamename for gamename in games if ctx.input_text in gamename]
        choices = list(map(bu.autocomplete_filter, games))
        if len(choices) > 25:
            choices = choices[:24]
        await ctx.send(choices=choices)

    @interactions.slash_command(
        name="bingo",
        sub_cmd_name="rules",
        sub_cmd_description="Display the rules for playing bingo",
        dm_permission=False
    )
    @interactions.slash_option(
        name="page",
        description="Specify which page of the rules to view.",
        opt_type=interactions.OptionType.INTEGER,
        required=False
    )
    async def send_rules(self, ctx: interactions.SlashContext, page: int = 0):
        rules_msg = await ctx.send(
            embeds=bi.gen_rules_embed(page=page, expired=False),
            components=[bu.nextpg_button(), bu.prevpg_button()]
        )
        channel = ctx.channel
        sent = bu.ListMsg(rules_msg.id, page, ctx.guild, channel, "bingorules")
        bd.active_msgs.append(sent)
        _ = asyncio.create_task(
            bu.close_msg(sent, 300, ctx)
        )
        return False
