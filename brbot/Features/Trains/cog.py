from brbot.Features.Trains.service import TrainGame, load_trains_game
from brbot.Features.Trains.data import (
    TrainShot,
    TrainPlayer,
    default_shop,
    train_game_embed,
    GameStatsView,
    GameRulesView,
    gen_rules_embed,
)
import brbot.Core.anilist as al
import brbot.Core.botdata as bd
import asyncio
from os import path, listdir, mkdir
import brbot.Core.botutils as bu
from shutil import copytree, ignore_patterns
from datetime import datetime
from io import BytesIO
from discord import app_commands, Interaction, File, Member
from discord.ext import commands
import logging

logger = logging.getLogger(__name__)


class TrainsCog(commands.GroupCog, name="trains"):
    @app_commands.command(name="newgame", description="Create a new trains game")
    @app_commands.describe(
        name="Trains game name",
        players="@ the participating players",
        width="Board width (must be divisible by 4)",
        height="Board height (must be divisible by 4)",
    )
    async def newgame(
        self,
        ctx: Interaction,
        name: str,
        players: str,
        width: int = 16,
        height: int = 16,
    ):
        await ctx.response.defer()
        river_ring: int = 1

        # Return errors if game is active or invalid name/width/height
        if ctx.guild_id in bd.active_trains:
            await ctx.followup.send(
                content=f'The game "{bd.active_trains[ctx.guild_id].name}" is already active in this server.'
            )
            return True
        if path.exists(f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{name}"):
            await ctx.followup.send(content="Name already exists!")
            return True

        logger.info(f"Creating new trains game {name} in {ctx.guild.name}")

        async def add_trains_player(m: Member, t: str):
            dm_channel = await m.create_dm() if m.dm_channel is None else m.dm_channel
            players.append(
                TrainPlayer(
                    member=m,
                    tag=t,
                    dmchannel=dm_channel,
                    anilist_id=bd.linked_profiles[m.id],
                )
            )

        # Create player list and tags
        members = await bu.get_members_from_str(ctx.guild, players)
        players: list = []
        tags: list = bu.get_player_tags(members)

        tasks: list = []
        for member, tag in zip(members, tags):
            if member.id not in bd.linked_profiles:
                logger.error(
                    f"User {member.name} not linked to any anilist profile, aborting game creation"
                )
                await ctx.followup.send(
                    content=f"Could not create game, <@{member.id}> must link their anilist profile! (/animanga link)"
                )
                return True

            tasks.append(asyncio.create_task(add_trains_player(m=member, t=tag)))
        await asyncio.gather(*tasks)

        # Return error if player list is empty
        if not players:
            await ctx.followup.send(content="No valid players specified.")
            return True

        # Create game object and set parameters
        date = datetime.now().strftime(bd.date_format)
        gameid = int(datetime.now().strftime("%Y%m%d%H%M%S"))

        game = TrainGame(
            name=name,
            date=date,
            players=players,
            board=None,
            gameid=gameid,
            active=True,
            size=(
                width + 2 * river_ring,
                height + 2 * river_ring,
            ),  # Add space on board for river border
        )
        try:
            game.gen_trains_board(play_area_size=(width, height), river_ring=river_ring)
            game.gen_player_locations(river_ring=river_ring)
        except game.BoardGenError as e:
            await ctx.followup.send(content=str(e))
            return True

        try:
            await game.set_game_anilist_info()
        except Exception as e:
            await ctx.followup.send(
                content="Error fetching player anilist information. Please try again in a few seconds."
            )
            logger.error(f"Could not create game {self.name}: {e}")
            return True

        try:
            mkdir(f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{name}")
        except OSError as e:
            logger.error(f"Could not create game folder for {ctx.guild.name}: {e}")
            await ctx.followup.send(
                content="Invalid name! Game must not contain the following characters: / \\ : * ? < > |"
            )
            return True

        # Push updates to player boards
        await ctx.followup.send(embed=train_game_embed(ctx=ctx, game=game))
        await game.update_boards_after_create(ctx=ctx)
        return False

    @app_commands.command(
        name="viewshop", description="View the shop for the active trains game."
    )
    async def viewshop(self, ctx: Interaction):
        if ctx.guild_id not in bd.active_trains:
            await ctx.response.send_message(
                content="There is no active game! To make one, use /trains newgame",
                ephemeral=True,
            )
            return True

        game = bd.active_trains[ctx.guild_id]
        await ctx.response.send_message(
            content="\n".join([item.shop_entry() for item in game.shop.values()])
        )
        return False

    @app_commands.command(name="buy", description="Buy an item from a shop/city.")
    @app_commands.describe(
        name="Item type to buy",
        showinfo="Show/stock information",
    )
    @app_commands.choices(
        name=[
            app_commands.Choice(name=itemname, value=itemname)
            for itemname in default_shop()
        ]
    )
    async def buy(self, ctx: Interaction, name: str, showinfo: str):
        if ctx.guild_id not in bd.active_trains:
            await ctx.response.send_message(
                content="There is no active game! To make one, use /trains newgame",
                ephemeral=True,
            )
            return True

        game = bd.active_trains[ctx.guild_id]

        err = game.buy_item(itemname=name, showinfo=showinfo, ctx=ctx)
        if err:
            await ctx.response.send_message(content=bd.fail_str)
            return True

        await ctx.response.send_message(content=bd.pass_str)
        return False

    @app_commands.command(
        name="inventory", description="View your inventory for the active trains game."
    )
    async def inventory(self, ctx: Interaction):
        if ctx.guild_id not in bd.active_trains:
            await ctx.response.send_message(
                content="There is no active game! To make one, use /trains newgame",
                ephemeral=True,
            )
            return True

        game = bd.active_trains[ctx.guild_id]

        player_idx, player = game.get_player(ctx.user.id)
        if player is None:
            await ctx.response.send_message(
                content="You are not a player in this game.", ephemeral=True
            )

        inv_str = "\n".join([item.inv_entry() for item in player.inventory.values()])
        if inv_str:
            await ctx.response.send_message(content=inv_str, ephemeral=True)
        else:
            await ctx.response.send_message(
                content="Your inventory is empty!", ephemeral=True
            )
        return False

    @app_commands.command(name="use", description="Use an item in your inventory.")
    @app_commands.describe(
        item="Item type to use",
        row="Row to use item on",
        column="Column to use item on",
    )
    @app_commands.choices(item=[app_commands.Choice(name="Bucket", value="Bucket")])
    async def use(self, ctx: Interaction, item: str, row: int, column: int):
        if ctx.guild_id not in bd.active_trains:
            await ctx.response.send_message(
                content="There is no active game! To make one, use /trains newgame",
                ephemeral=True,
            )
            return True

        game = bd.active_trains[ctx.guild_id]

        if item == "Bucket":
            err = game.use_bucket(ctx=ctx, row=row, col=column)
            if err:
                await ctx.response.send_message(content=bd.fail_str)
                return True
            await ctx.response.send_message(content=bd.pass_str)
            await game.update_boards_after_shot(ctx=ctx, row=row, column=column)
        return False

    @app_commands.command(name="shot", description="Make a trains shot")
    @app_commands.describe(
        link="Anilist link of show",
        row="Row to place a rail",
        column="Column to place a rail",
        info="Shot show/stock information",
    )
    async def shot(self, ctx: Interaction, row: int, column: int, link: str, info: str):
        await ctx.response.defer(ephemeral=False)
        if ctx.guild_id not in bd.active_trains:
            await ctx.followup.send(
                content="There is no active game! To make one, use /trains newgame",
                ephemeral=True,
            )
            return True

        game = bd.active_trains[ctx.guild_id]

        # This is bad and needs to be reworked
        copytree(
            f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{game.name}",
            f"{bd.parent}/Guilds/{ctx.guild_id}/TrainBackups/[BACKUP] {game.name}",
            dirs_exist_ok=True,
            ignore=ignore_patterns("*.png"),
        )
        # Get player, validate shot
        show_id = al.anilist_id_from_url(url=link)
        if show_id is None:
            await ctx.followup.send(
                content="Could not find show, please check anilist URL!"
            )
            return True

        sender_idx, player = game.get_player(int(ctx.user.id))
        if not game.is_valid_shot(player, row, column):
            await ctx.followup.send(content=bd.fail_str)
            return True

        # Fetch anilist show information if it isn't already cached
        if show_id not in game.known_shows:
            logger.info(f"{show_id} not in {game.known_shows}, fetching anilist info")
            show_info = await al.query_media(media_id=show_id)
            if show_info is None:
                await ctx.followup.send(
                    content="Error connecting to anilist, please check URL and try again."
                )
                return True
            game.known_shows[show_id] = show_info

        # Update board, player rails
        shot = TrainShot(
            row=row,
            col=column,
            show_id=show_id,
            info=info,
            time=datetime.now().strftime(bd.date_format),
        )
        game.update_player_stats_after_shot(
            sender_idx=sender_idx, player=player, shot=shot
        )

        # Save/update games
        await ctx.followup.send(content=bd.pass_str)
        await game.update_boards_after_shot(ctx=ctx, row=row, column=column)
        if not game.active:
            await game.calculate_player_scores(ctx=ctx)
            embed, image = game.gen_score_embed(ctx=ctx, page=0)
            view = GameStatsView(game=game)
            await ctx.followup.send(embed=embed, file=image, view=view)
        return False

    @app_commands.command(name="undo", description="Undo your last shot.")
    async def undo(self, ctx: Interaction):
        await ctx.response.defer(ephemeral=True)

        # Determine if undo is valid
        if ctx.guild_id not in bd.active_trains:
            await ctx.followup.send(
                content="There is no active game! To make one, use /trains newgame",
                ephemeral=True,
            )
            return True

        game = bd.active_trains[ctx.guild_id]

        # This is bad and needs to be reworked
        copytree(
            f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{game.name}",
            f"{bd.parent}/Guilds/{ctx.guild_id}/TrainBackups/[BACKUP] {game.name}",
            dirs_exist_ok=True,
            ignore=ignore_patterns("*.png"),
        )

        sender_idx, player = game.get_player(ctx.user.id)
        if not player.shots:
            await ctx.followup.send(
                content="You have not taken any shots yet!", ephemeral=True
            )
            return True

        # Delete last shot from record, update active player status
        shot = game.players[sender_idx].shots[-1]

        if (shot.row, shot.col) in player.shops_used:
            await ctx.followup.send(
                content="You have bought an item at this shop, can not undo shot."
            )
            return True

        game.update_player_stats_after_shot(
            sender_idx=sender_idx, player=player, undo=True, shot=shot
        )

        await ctx.followup.send(content=bd.pass_str)
        # Save/update games
        await game.update_boards_after_shot(ctx=ctx, row=shot.row, column=shot.col)
        return False

    @app_commands.command(
        name="stats",
        description="View limited/full stats for an in-progress/completed game.",
    )
    @app_commands.describe(
        name="Game name to view stats of (defaults to active)",
    )
    async def stats(self, ctx: Interaction, name: str = None) -> bool:
        # Logic to get game or return error if no game found
        if name is None:
            if ctx.guild_id not in bd.active_trains:
                await ctx.response.send_message(
                    content="No active game found, please specify a game name."
                )
                return True
            game = bd.active_trains[ctx.guild_id]

        else:
            try:
                game = await load_trains_game(
                    filepath=f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{name}",
                    guild=ctx.guild,
                )
            except FileNotFoundError:
                await ctx.response.send_message(content="Game name does not exist.")
                return True
            except TypeError or ValueError:
                return True
        await ctx.response.defer()

        # Send stats
        embed, image = game.gen_stats_embed(ctx=ctx)
        view = GameStatsView(game=game)
        if image:
            await ctx.followup.send(embed=embed, file=image, view=view)
        else:
            await ctx.followup.send(embed=embed, view=view)
        return False

    @stats.autocomplete("name")
    async def stats_autocomplete(self, ctx: Interaction, current: str):
        games: list = listdir(f"{bd.parent}/Guilds/{ctx.guild_id}/Trains")
        games = [gamename for gamename in games if current in gamename]
        choices = list(map(bu.autocomplete_filter, games))
        if len(choices) > 25:
            choices = choices[:24]
        return choices

    @app_commands.command(
        name="board", description="View your train board for the active game."
    )
    async def board(self, ctx: Interaction):
        if ctx.guild_id not in bd.active_trains:
            await ctx.response.send_message(
                content="No active game found.", ephemeral=True
            )
            return True

        game = bd.active_trains[ctx.guild_id]
        player_idx, player = game.get_player(ctx.user.id)

        if not player:
            await ctx.response.send_message(
                content="You are not a player in this game.", ephemeral=True
            )
            return True

        try:
            with open(
                f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{game.name}/{ctx.user.id}.png",
                "rb",
            ) as f:
                file = BytesIO(f.read())
        except FileNotFoundError:
            await ctx.response.send_message(bd.fail_str, ephemeral=True)
            return True

        await ctx.response.send_message(
            file=File(file, filename="board_img.png"), ephemeral=True
        )
        return False

    @app_commands.command(
        name="delete", description="Remove the active trains game. (admin only)"
    )
    @app_commands.describe(
        keep_files="Choose whether to archive or completely delete the active game's files"
    )
    async def delete(self, ctx: Interaction, keep_files: bool):
        if not ctx.user.guild_permissions.administrator:
            await ctx.response.send_message(
                content="You must be an administrator to use this command!",
                ephemeral=True,
            )
            return True

        await ctx.response.defer()
        if ctx.guild_id not in bd.active_trains:
            await ctx.followup.send(
                content="There is no active game! To make one, use /trains newgame",
                ephemeral=True,
            )
            return True

        game = bd.active_trains[ctx.guild_id]

        if keep_files:
            game.active = False
            game.save_game(f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{game.name}")
        else:
            bu.del_game_files(
                guild_id=ctx.guild_id, game_name=game.name, game_type="Trains"
            )
        del bd.active_trains[ctx.guild_id]
        await ctx.followup.send(content=bd.pass_str)
        return False

    @app_commands.command(
        name="restore",
        description="Restore an incomplete, archived game to active status. (admin only)",
    )
    @app_commands.describe(name="Name of game to be restored")
    async def restore(self, ctx: Interaction, name: str):
        if not ctx.user.guild_permissions.administrator:
            await ctx.response.send_message(
                content="You must be an administrator to use this command!",
                ephemeral=True,
            )
            return True
        if ctx.guild_id in bd.active_trains:
            await ctx.response.send_message(
                "There is already an active game in this server!"
            )
            return True
        try:
            test_game = await load_trains_game(
                filepath=f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{name}",
                guild=ctx.guild,
            )
        except FileNotFoundError:
            await ctx.response.send_message(content="Game name does not exist.")
            return True
        if not any(player.done is False for player in test_game.players):
            await ctx.response.send_message(
                "You can not restore a completed game to active status."
            )
            return True

        test_game.active = True
        logger.info(f"Restored game {name} to active status in {ctx.guild.name}")
        test_game.save_game(
            f"{bd.parent}/Guilds/{ctx.guild_id}/Trains/{test_game.name}"
        )
        bd.active_trains[ctx.guild_id] = test_game
        await ctx.response.send_message(content=bd.pass_str)
        return False

    @restore.autocomplete("name")
    async def restore_autocomplete(self, ctx: Interaction, current: str):
        games = listdir(f"{bd.parent}/Guilds/{ctx.guild_id}/Trains")
        games = [gamename for gamename in games if current in gamename]
        choices = list(map(bu.autocomplete_filter, games))
        if len(choices) > 25:
            choices = choices[:24]
        return choices

    @app_commands.command(
        name="rules", description="Display the rules for playing trains"
    )
    @app_commands.describe(page="Specify which page of the rules to view.")
    async def rules(self, ctx: Interaction, page: int = 1):
        view = GameRulesView(page=page - 1)
        await ctx.response.send_message(embed=gen_rules_embed(page=page - 1), view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(TrainsCog(bot))
