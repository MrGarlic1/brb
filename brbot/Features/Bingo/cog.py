import brbot.Features.Bingo.data as bi
import brbot.Core.anilist as al
import brbot.Core.botdata as bd
import asyncio
from os import path, listdir, mkdir
import brbot.Core.botutils as bu
from shutil import copytree, ignore_patterns
from datetime import datetime
from discord import app_commands, Interaction, Member
from discord.ext import commands


class BingoCog(commands.GroupCog, name='bingo'):
    @app_commands.command(
        name='newgame',
        description='Create a new bingo game'
    )
    @app_commands.describe(
        name='Bingo game name',
        players='@ the participating players'
    )
    async def newgame(
            self, ctx: Interaction, name: str, players: str
    ):
        await ctx.response.defer()

        # Return errors if game is active or invalid name
        if ctx.guild_id in bd.active_bingos:
            await ctx.followup.send(
                content=f"The game \"{bd.active_bingos[ctx.guild_id].name}\" is already active in this server."
            )
            return True
        if path.exists(f"{bd.parent}/Guilds/{ctx.guild_id}/Bingo/{name}"):
            await ctx.followup.send(content="Name already exists!")
            return True

        async def add_bingo_player(m: Member):
            starting_anilist = await al.query_user_animelist(bd.linked_profiles[m.id])
            dm_channel = await m.create_dm() if m.dm_channel is None else m.dm_channel
            players.append(bi.BingoPlayer(
                member=m, dmchannel=dm_channel, starting_anilist=starting_anilist,
                )
            )

        # Create player list and tags
        members = await bu.get_members_from_str(ctx.guild, players)
        players: list = []

        tasks: list = []
        for member in members:
            if member.id not in bd.linked_profiles:
                await ctx.followup.send(
                    content=f"Could not create game, <@{member.id}> must link their anilist profile! (/anilist link)"
                )
                return True

            tasks.append(asyncio.create_task(
                add_bingo_player(m=member)
            ))
        await asyncio.gather(*tasks)

        # Return error if player list is empty
        if not players:
            await ctx.followup.send(content="No valid players specified.")
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
            await ctx.followup.send(
                content="Invalid name! Game must not contain the following characters: / \\ : * ? < > |"
            )
            return True

        # Push updates to player boards
        await ctx.followup.send(embed=bi.bingo_game_embed(ctx=ctx, game=game))
        game.update_boards_after_create(ctx=ctx)
        return False

    @app_commands.command(
        name='shot',
        description='Make a bingo shot.'
    )
    @app_commands.describe(
        link='Anilist link of show/character',
        tag='Bingo tag to shoot for',
        info='Time/stock information'
    )
    async def shot(self, ctx: Interaction, link: str, info: str, tag: str):
        await ctx.response.defer(ephemeral=False)
        if ctx.guild_id not in bd.active_bingos:
            await ctx.followup.send(
                content="There is no active game! To make one, use /bingo newgame", ephemeral=True
            )
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

        sender_idx, player = game.get_player(int(ctx.user.id))

        if player is None:
            await ctx.followup.send("You are not in this bingo game!")
            return True

        if any(shot.tag == tag for shot in player.shots):
            await ctx.followup.send(
                "You have already shot for this tag. Please select a different tag and try again."
            )
            return True

        shot = bi.BingoShot(
            anilist_id=0, tag=tag, time=datetime.now().strftime(bd.date_format), info=info
        )
        shot_type = shot.get_shot_type()
        if not shot_type:
            await ctx.followup.send(content="Invalid tag specified. Please check the tag and try again.")
            return True

        if shot_type == "character":
            anilist_id = al.anilist_id_from_url(url=link, is_character=True)
        else:
            anilist_id = al.anilist_id_from_url(url=link)
        if anilist_id is None:
            await ctx.followup.send(content="Could not find show, please check anilist URL!")
            return True

        # Fetch anilist information if it isn't already cached
        if anilist_id not in game.known_entries:
            if shot_type == "character":
                anilist_info = al.query_character(character_id=anilist_id)
            else:
                anilist_info = al.query_media(media_id=anilist_id)

            if anilist_info is None:
                await ctx.followup.send(content="Error connecting to anilist, please check URL and try again.")
                return True
            game.known_entries[anilist_id] = anilist_info

        poll_msg = None

        if shot_type == "character":
            await ctx.followup.send(content="Sending poll.", ephemeral=True)
            poll_msg = await ctx.channel.send(
                content=f"Does this character fill the tag [{shot.tag}]?\n\n*(Poll open for 2 hours)*"
            )
            await poll_msg.add_reaction("🔺")
            await poll_msg.add_reaction("🔻")
            await asyncio.sleep(7200)

        valid = await shot.is_valid(
            anilist_info=game.known_entries[anilist_id],
            starting_anilist=player.starting_anilist,
            poll_msg=poll_msg
        )

        if not valid:
            await ctx.followup.send(
                "Show/Character does not meet requirements! Please choose a different tag.", ephemeral=True
            )
            return True

        # Update board, player rails

        hit_tile = player.find_tag(tag)

        if hit_tile:
            shot.hit = True
            player.board[hit_tile].hit = True
            await ctx.followup.send(
                content=f"🟩{bi.col_emojis[hit_tile[0] - 1]}{bi.row_emojis[hit_tile[1] - 1]}"
            )
            if player.has_bingo():
                player.done = True
                game.active = False
        else:
            await ctx.followup.send(content="🟥")

        game.update_game_after_shot(ctx=ctx, shot=shot, player_idx=sender_idx, hit_tile=hit_tile)
        return False

    @shot.autocomplete("tag")
    async def autocomplete(self, _: Interaction, current: str):
        tags = bi.bingo_tags + bi.character_tags + bi.season_tags + bi.episode_tags
        tags = [tag for tag in tags if current.lower() in tag.lower()]
        choices = list(map(bu.autocomplete_filter, tags))
        if len(choices) > 25:
            choices = choices[:24]
        return choices

    @app_commands.command(
        name='board',
        description='View the bingo boards for the active game.'
    )
    async def show_bingo_board(self, ctx: Interaction):
        if ctx.guild_id not in bd.active_bingos:
            await ctx.response.send_message(content="No active game found.", ephemeral=True)
            return True

        game = bd.active_bingos[ctx.guild_id]
        player_idx, player = game.get_player(ctx.user.id)

        if not player:
            await ctx.response.send_message(content="You are not a player in this game.", ephemeral=True)
            return True

        embed, image = game.gen_board_embed(page=0, sender_idx=player_idx)
        view = bi.GameBoardView(game=game, sender_idx=player_idx)
        await ctx.response.send_message(
            embed=embed, file=image, view=view, ephemeral=True
        )
        return False

    @app_commands.command(
        name='delete',
        description='Remove the active bingo game. (admin only)'
    )
    @app_commands.describe(
        keep_files='Choose whether to archive or completely delete the active game\'s files'
    )
    async def delete(self, ctx: Interaction, keep_files: bool):
        if not ctx.user.guild_permissions.administrator:
            await ctx.response.send_message(content="You must be an administrator to use this command!", ephemeral=True)
            return True
        await ctx.response.defer()
        if ctx.guild_id not in bd.active_bingos:
            ctx.followup.send(
                content="There is no active game! To make one, use /bingo newgame", ephemeral=True
            )
            return True

        game = bd.active_bingos[ctx.guild_id]

        if keep_files:
            game.active = False
            game.save_game(f"{bd.parent}/Guilds/{ctx.guild_id}/Bingo/{game.name}")
        else:
            bu.del_game_files(guild_id=ctx.guild_id, game_name=game.name, game_type="Bingo")
        del bd.active_bingos[ctx.guild_id]
        await ctx.followup.send(content=bd.pass_str)
        return False

    @app_commands.command(
        name='restore',
        description='Restore an incomplete, archived game to active status. (admin only)'
    )
    @app_commands.describe(
        name='Name of game to be restored'
    )
    async def restore(self, ctx: Interaction, name: str):
        if not ctx.user.guild_permissions.administrator:
            await ctx.response.send_message(content="You must be an administrator to use this command!", ephemeral=True)
            return True
        if ctx.guild_id in bd.active_bingos:
            await ctx.response.send_message("There is already an active game in this server!")
            return True
        try:
            test_game = await bi.load_bingo_game(
                filepath=f"{bd.parent}/Guilds/{ctx.guild_id}/Bingo/{name}", guild=ctx.guild
            )
        except FileNotFoundError:
            await ctx.response.send_message(content="Game name does not exist.")
            return True
        if any(player.done is True for player in test_game.players):
            await ctx.response.send_message("You can not restore a completed game to active status.")
            return True

        test_game.active = True
        test_game.save_game(f"{bd.parent}/Guilds/{ctx.guild_id}/Bingo/{test_game.name}")
        bd.active_bingos[ctx.guild_id] = test_game
        await ctx.response.send_message(content=bd.pass_str)
        return False

    @restore.autocomplete("name")
    async def autocomplete(self, ctx: Interaction, current: str):
        games = listdir(f"{bd.parent}/Guilds/{ctx.guild_id}/Bingo")
        games = [gamename for gamename in games if current in gamename]
        choices = list(map(bu.autocomplete_filter, games))
        if len(choices) > 25:
            choices = choices[:24]
        return choices

    @app_commands.command(
        name='rules',
        description='Display the rules for playing bingo'
    )
    @app_commands.describe(
        page='Specify which page of the rules to view.'
    )
    async def send_rules(self, ctx: Interaction, page: int = 1):
        await ctx.response.send_message(
            embed=bi.gen_rules_embed(page=page - 1),
            view=bi.GameRulesView(page=page - 1)
        )
        return False


async def setup(bot: commands.Bot):
    await bot.add_cog(BingoCog(bot))
