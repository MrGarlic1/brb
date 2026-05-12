from brbot.Core.bot import BrBot
from brbot.Features.Trains.gameservice import GameService
from brbot.Features.Trains.data import (
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    default_shop,
    train_game_embed,
    GameStatsView,
    GameRulesView,
    gen_rules_embed,
)
from brbot.Features.Trains.renderservice import RenderService
from brbot.db.models import TrainShot
import brbot.Core.botdata as bd
from os import listdir
import brbot.Core.botutils as bu
from datetime import datetime, timezone
from discord import app_commands, Interaction, File
from discord.ext import commands
import logging

logger = logging.getLogger(__name__)


class TrainsCog(commands.GroupCog, name="trains"):
    def __init__(self, bot: BrBot):
        self.bot = bot
        self.game_service = GameService()
        self.render_service = RenderService()

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
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
    ):
        await ctx.response.defer()

        # Return errors if game is active or invalid name/width/height
        async with self.bot.session_generator() as session:
            existing_game = await self.game_service.get_guild_train_game(
                ctx.guild.id, session, active=True
            )

            if existing_game is not None:
                await ctx.followup.send(
                    content=f"The game {existing_game.name} is already active in this server."
                )
                return

        # Get valid game players
        players = await bu.get_members_from_str(ctx.guild, players)
        if not players:
            await ctx.followup.send(content="No valid players specified.")
            return

        error = await self.game_service.create_train_game(
            ctx.guild,
            name,
            players,
            height=height,
            width=width,
            session_generator=self.bot.session_generator,
        )

        if error:
            await ctx.followup.send(content=error)
            return

        # Push updates to player boards
        await ctx.followup.send(
            embed=train_game_embed(
                ctx=ctx, name=name, width=width, height=height, members=players
            )
        )
        async with self.bot.session_generator() as session:
            game = await self.game_service.get_guild_train_game(
                ctx.guild.id, session, load_players=True, active=True
            )
            await RenderService.send_updates_after_create(game=game, guild=ctx.guild)
        return

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
        await ctx.response.defer()

        async with self.bot.session_generator() as session:
            item_counts = await self.game_service.get_player_item_counts(
                ctx.guild.id, ctx.user.id, session
            )
        if item_counts is None:
            await ctx.response.send_message(
                content="You are not currently involved in a train game in this server!",
                ephemeral=True,
            )
            return

        if item_counts:
            await ctx.followup.send(
                content=self.game_service.inventory_string(item_counts)
            )
        else:
            await ctx.followup.send(content="Your inventory is empty!", ephemeral=True)
        return

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
        async with self.bot.session_generator() as session:
            game = await self.game_service.get_guild_train_game(
                ctx.guild_id, session, load_players=True, active=True
            )

            if game is None:
                await ctx.followup.send(
                    content="There is no active game! To make one, use /trains newgame",
                    ephemeral=True,
                )
                return
            if not any(p.member.user_id == ctx.user.id for p in game.players):
                await ctx.followup.send(
                    content="You are not a player in this game!", ephemeral=True
                )
                return

        # Get player, validate shot
        show_id = await self.game_service.validate_and_cache_anilist_info(
            link=link, cache=self.bot.cached_al_media
        )
        if show_id is None:
            await ctx.followup.send(
                content="Could not find show, please check Anilist URL!"
            )
            return
        anilist_info = self.bot.cached_al_media.get(show_id)

        if anilist_info is None:
            await ctx.followup.send(
                content="Error connecting to Anilist, please try again."
            )
            return

        async with self.bot.session_generator() as session:
            # Update board, player rails

            game = await self.game_service.get_guild_train_game(
                ctx.guild_id, session, load_players=True, active=True
            )
            player = next(p for p in game.players if p.member.user_id == ctx.user.id)
            if not self.game_service.is_valid_shot(game, player, column, row):
                await ctx.followup.send(content=bd.fail_str)
                return

            shot = TrainShot(
                player_id=player.id,
                anilist_media_id=show_id,
                column=column,
                row=row,
                genres=anilist_info["genres"],
                info=info,
                time=datetime.now(timezone.utc),
            )
            await self.game_service.save_shot(game, player, shot, session)
            await session.commit()

            # Send out board updates to relevant players
            await ctx.followup.send(content=bd.pass_str)
            await self.render_service.send_updates_after_shot(
                game=game, guild=ctx.guild, column=column, row=row
            )

        if not game.active:
            await self.game_service.calculate_player_scores(ctx=ctx)
            embed, image = self.render_service.gen_score_embed(game=game, page=0)
            view = GameStatsView(game.id, True, self.bot.session_generator, self.render_service)
            await ctx.followup.send(embed=embed, file=image, view=view)
        return

    @app_commands.command(
        name="stats",
        description="View limited/full stats for an in-progress/completed game.",
    )
    @app_commands.describe(
        name="Game name to view stats of (defaults to active)",
    )
    async def stats(self, ctx: Interaction, name: str = None):
        # Logic to get game or return error if no game found
        await ctx.response.defer()
        async with self.bot.session_generator() as session:
            if name is None:
                game = await self.game_service.get_guild_train_game(
                    ctx.guild_id, session, load_players=True, active=True
                )
                if game is None:
                    await ctx.response.send_message(
                        content="No active game found, please specify a game name."
                    )
                    return
            else:
                game = await self.game_service.get_guild_train_game(
                    ctx.guild_id, session, load_players=True, active=False, name=name
                )
                if game is None:
                    names = await self.game_service.get_guild_game_names(
                        ctx.guild_id, session
                    )
                    await ctx.response.send_message(
                        content=f"No game found! Possible options: {', '.join(names)}"
                    )
                    return

            # Send stats
            is_done = self.game_service.is_done(game)
            embed, image = await self.render_service.gen_stats_embed(
                game, ctx, game_done=is_done
            )
            view = GameStatsView(game.id, is_done, self.bot.session_generator, self.render_service)
            if image:
                await ctx.followup.send(embed=embed, file=image, view=view)
            else:
                await ctx.followup.send(embed=embed, view=view)
            return

    @app_commands.command(
        name="board", description="View your train board for the active game."
    )
    async def board(self, ctx: Interaction):
        await ctx.response.defer(ephemeral=True)
        async with self.bot.session_generator() as session:
            game = await self.game_service.get_guild_train_game(
                ctx.guild_id, session, load_players=True
            )
            if game:
                player = next(
                    player
                    for player in game.players
                    if player.member.user_id == ctx.user.id
                )

            if not game or not player:
                await ctx.followup.send(
                    content="You are not currently in a train game in this server!",
                    ephemeral=True,
                )
                return True
            img_bytes = self.render_service.draw_board_img(
                game_width=game.board_width,
                game_height=game.board_height,
                board={tile.position: tile for tile in game.tiles},
                player=player,
            )

        await ctx.followup.send(
            file=File(img_bytes, filename="attachment://train_board.png"),
            ephemeral=True,
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
            await ctx.followup.send(
                content="You must be an administrator to use this command!",
                ephemeral=True,
            )
            return

        await ctx.response.defer()
        async with self.bot.session_generator() as session:
            game = await self.game_service.get_guild_train_game(
                ctx.guild_id, session=session
            )
            if game is None:
                ctx.followup.send(
                    content="There is no active game! To make one, use /train newgame",
                    ephemeral=True,
                )
                return

            try:
                await self.game_service.delete_train_game(
                    game, keep_files=keep_files, session=session
                )
            except Exception as e:
                logger.warning(
                    f"Error when deleting train game in guild {ctx.guild.id}: {e}"
                )
                await ctx.followup.send(
                    content="A transient error occurred while deleting. Please try again!"
                )
            await session.commit()

        await ctx.followup.send(content=bd.pass_str)
        return

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


async def setup(bot: BrBot):
    await bot.add_cog(TrainsCog(bot))
