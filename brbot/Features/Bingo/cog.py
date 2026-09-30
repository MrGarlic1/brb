from brbot.Features.Bingo.data import (
    bingo_game_embed,
    gen_rules_embed,
    ShotType,
    GameBoardView,
    GameRulesView,
)
from brbot.Features.Bingo.data import (
    col_emojis,
    row_emojis,
    bingo_tags,
    character_tags,
    episode_tags,
    season_tags,
)
import brbot.Shared.Anilist.anilist as al
import brbot.Core.botdata as bd
import asyncio
import brbot.Core.botutils as bu
from brbot.Core.bot import BrBot
from brbot.db.models import BingoShot, BingoPlayer
from datetime import datetime
from discord import app_commands, Interaction
from discord.ext import commands

from brbot.Features.Bingo.gameservice import BingoGameService
from brbot.Features.Bingo.renderservice import BingoRenderService
import logging

logger = logging.getLogger(__name__)


class BingoCog(commands.GroupCog, name="bingo"):
    def __init__(self, bot: BrBot):
        self.bot = bot
        self.game_service = BingoGameService()
        self.render_service = BingoRenderService()

    @app_commands.command(name="newgame", description="Create a new bingo game")
    @app_commands.describe(
        name="Bingo game name", players="@ the participating players"
    )
    async def newgame(self, ctx: Interaction, name: str, players: str):
        await ctx.response.defer()

        async with self.bot.session_generator() as session:
            existing_game = await self.game_service.get_guild_active_bingo_game(
                ctx.guild.id, session
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

        await self.game_service.create_bingo_game(
            ctx.guild.id, name, players, self.bot.session_generator
        )

        # Send game information embed
        mention_strs = [p.mention for p in players]
        await ctx.followup.send(
            embed=bingo_game_embed(
                ctx=ctx,
                game_name=name,
                game_date=datetime.now(),
                player_mentions=mention_strs,
            )
        )
        return

    @app_commands.command(name="shot", description="Make a bingo shot.")
    @app_commands.describe(
        link="anilist link of show/character",
        tag="Bingo tag to shoot for",
        info="Time/stock information",
    )
    async def shot(self, ctx: Interaction, link: str, info: str, tag: str):
        await ctx.response.defer(ephemeral=False)
        async with self.bot.session_generator() as session:
            game = await self.game_service.get_guild_active_bingo_game(
                ctx.guild.id, session, load_players=True
            )

            if game is None:
                await ctx.followup.send(
                    content="There is no active game! To make one, use /bingo newgame",
                    ephemeral=True,
                )
                return

            players: list[BingoPlayer] = list(game.players)
            player = next((p for p in players if p.member.user_id == ctx.user.id), None)

            if player is None:
                await ctx.followup.send("You are not in a player in this bingo game!")
                return

            player_id = player.id
            player_starting_anilist: dict = player.starting_anilist
            existing_shot_tags = [shot.tag for shot in player.shots]
            mention_str = ", ".join([f"<@{p.member.user_id}>" for p in players])

        if tag in existing_shot_tags:
            await ctx.followup.send(
                "You have already shot for this tag. Please select a different tag and try again."
            )
            return

        shot = BingoShot(
            player_id=player_id,
            anilist_entry_id=0,
            tag=tag,
            time=datetime.now(),
            hit=False,
            info=info,
        )
        shot_type = self.game_service.get_shot_type(tag)
        if shot_type == ShotType.OTHER:
            await ctx.followup.send(
                content="Invalid tag specified. Please check the tag and try again."
            )
            return

        anilist_id = al.anilist_id_from_url(
            url=link, is_character=shot_type == ShotType.CHARACTER
        )
        if anilist_id is None:
            await ctx.followup.send(
                content="Could not find show/character, please check anilist URL!"
            )
            return

        is_character = shot_type == ShotType.CHARACTER
        cache = (
            self.bot.cached_al_characters if is_character else self.bot.cached_al_media
        )

        anilist_info = cache.get(anilist_id)
        if anilist_info is None:
            anilist_info = (
                await al.query_character(character_id=anilist_id)
                if is_character
                else await al.query_media(media_id=anilist_id)
            )

        if anilist_info is None:
            await ctx.followup.send(
                content="Error connecting to anilist, please check URL and try again."
            )
            return

        cache[anilist_id] = anilist_info

        poll_msg = None

        if is_character:
            await ctx.followup.send(content="Sending poll.", ephemeral=True)
            poll_msg = await ctx.channel.send(
                content=f"{mention_str}\nDoes this character fill the tag [{shot.tag}]?\n\n*(Poll open for 2 hours)*"
            )
            await poll_msg.add_reaction("🔺")
            await poll_msg.add_reaction("🔻")
            await asyncio.sleep(7200)

        valid = await self.game_service.is_shot_valid(
            shot_anilist_id=anilist_id,
            shot_tag=tag,
            player_starting_anilist=player_starting_anilist,
            shot_anilist_info=anilist_info,
            poll_msg=poll_msg,
        )

        if not valid:
            await ctx.followup.send(
                "Show/Character does not meet requirements! Please choose a different tag.",
                ephemeral=True,
            )
            return

        # Update board, player rails
        async with self.bot.session_generator() as session:
            try:
                hit_tile = await self.game_service.get_hit_tile(tag, player_id, session)
                if hit_tile is None:
                    await ctx.followup.send(content="🟥")
                    return

                hit_tile.hit = True
                shot.hit = True
                session.add(shot)
                await ctx.followup.send(
                    content=f"🟩{col_emojis[hit_tile.column - 1]}{row_emojis[hit_tile.row - 1]}"
                )
                if await self.game_service.check_and_mark_game_finished(
                    game_id=game.id, player_id=player_id, session=session
                ):
                    await ctx.channel.send("Game's done! (Placeholder)")
                await session.commit()

            except Exception as e:
                await session.rollback()
                await ctx.channel.send(
                    "A transient error occurred while adding this shot. Please try again!"
                )
                logger.error(
                    f"An error occurred while adding shot in game {game.id}: {e}"
                )
        return

    @shot.autocomplete("tag")
    async def shot_autocomplete(self, _: Interaction, current: str):
        tags = bingo_tags + character_tags + season_tags + tuple(episode_tags.keys())
        tags = [tag for tag in tags if current.lower() in tag.lower()]
        choices = list(map(bu.autocomplete_filter, tags))
        if len(choices) > 25:
            choices = choices[:24]
        return choices

    @app_commands.command(
        name="board", description="View the bingo boards for the active game."
    )
    async def show_bingo_board(self, ctx: Interaction):
        await ctx.response.defer(ephemeral=True)
        async with self.bot.session_generator() as session:
            game = await self.game_service.get_guild_active_bingo_game(
                ctx.guild_id, session=session, load_players=True
            )

            if game is None:
                await ctx.followup.send(content="No active game found.", ephemeral=True)
                return
            frozen_players = await self.game_service.create_frozen_player_list(
                players=game.players
            )

        player_discord_ids = [p.discord_user_id for p in frozen_players]
        try:
            page = player_discord_ids.index(ctx.user.id)
        except ValueError:
            await ctx.followup.send(
                content="You are not a player in this game.", ephemeral=True
            )
            return

        embed, image = self.render_service.gen_board_embed(
            players=frozen_players, discord_member=ctx.user, page=page
        )
        view = GameBoardView(
            render_service=self.render_service, players=frozen_players, page=page
        )
        await ctx.followup.send(embed=embed, file=image, view=view, ephemeral=True)
        return

    @app_commands.command(
        name="delete", description="Remove the active bingo game. (admin only)"
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
            game = await self.game_service.get_guild_active_bingo_game(
                ctx.guild_id, session=session
            )
            if game is None:
                ctx.followup.send(
                    content="There is no active game! To make one, use /bingo newgame",
                    ephemeral=True,
                )
                return

            try:
                await self.game_service.delete_bingo_game(
                    game, keep_files=keep_files, session=session
                )
            except Exception as e:
                logger.warning(
                    f"Error when deleting bingo game in guild {ctx.guild.id}: {e}"
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
        """
            if not ctx.user.guild_permissions.administrator:
                await ctx.response.send_message(
                    content="You must be an administrator to use this command!",
                    ephemeral=True,
                )
                return True
            if ctx.guild_id in bd.active_bingos:
                await ctx.response.send_message(
                    "There is already an active game in this server!"
                )
                return True
            try:
                test_game = await bi.load_bingo_game(
                    filepath=f"{bd.parent}/Guilds/{ctx.guild_id}/Bingo/{name}",
                    guild=ctx.guild,
                )
            except FileNotFoundError:
                await ctx.response.send_message(content="Game name does not exist.")
                return True
            if any(player.done is True for player in test_game.players):
                await ctx.response.send_message(
                    "You can not restore a completed game to active status."
                )
                return True

            test_game.active = True
            test_game.save_game(f"{bd.parent}/Guilds/{ctx.guild_id}/Bingo/{test_game.name}")
            bd.active_bingos[ctx.guild_id] = test_game
            await ctx.response.send_message(content=bd.pass_str)
            return False

        @restore.autocomplete("name")
        async def restore_autocomplete(self, ctx: Interaction, current: str):
            games = listdir(f"{bd.parent}/Guilds/{ctx.guild_id}/Bingo")
            games = [gamename for gamename in games if current in gamename]
            choices = list(map(bu.autocomplete_filter, games))
            if len(choices) > 25:
                choices = choices[:24]
            return choices
        """

    @app_commands.command(
        name="rules", description="Display the rules for playing bingo"
    )
    @app_commands.describe(page="Specify which page of the rules to view.")
    async def send_rules(self, ctx: Interaction, page: int = 1):
        await ctx.response.send_message(
            embed=gen_rules_embed(page=page - 1),
            view=GameRulesView(page=page - 1),
        )
        return False


async def setup(bot: BrBot):
    await bot.add_cog(BingoCog(bot))
