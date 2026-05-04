import brbot.Core.botdata as bd
import brbot.Core.botutils as bu
from brbot.Core.bot import BrBot
from brbot.Features.Responses.service import ResponseService
from brbot.Features.Responses.data import RspView
from brbot.Shared.Responses.models import CachedResponse
from brbot.Shared.Members.repository import get_or_create_member
from discord import app_commands, Interaction, Message
from discord.ext import commands
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ResponsesCog(commands.GroupCog, name="response"):
    def __init__(self, bot: BrBot):
        self.response_service = ResponseService(
            exact_cache=bot.responses,
            phrase_cache=bot.mentions,
            guild_config_cache=bot.guild_configs,
        )
        self.bot = bot

    @app_commands.command(
        name="add",
        description="Add a response",
    )
    @app_commands.describe(
        trigger="Text to respond to",
        text="What the bot should respond with",
        exact="If the message should exactly match the trigger phrase to respond",
    )
    async def add(self, ctx: Interaction, trigger: str, text: str, exact: bool):
        # Config permission checks
        async with self.bot.locks[ctx.guild_id]:
            async with self.bot.session_generator() as session:
                member = await get_or_create_member(ctx.user.id, ctx.guild_id, session)
                error = await self.response_service.get_response_add_validation_error(
                    ctx.guild_id, member, exact, session
                )

        if error:
            await ctx.response.send_message(
                content=error,
                ephemeral=True,
            )
        async with self.bot.locks[ctx.guild_id]:
            async with self.bot.session_generator() as session:
                error = await self.response_service.add_response(
                    ctx.guild_id,
                    CachedResponse(
                        trigger=trigger, text=text, exact=exact, member_id=member.id
                    ),
                    session,
                )

        await self.response_service.migrate_responses(
            bd.OLD_DATA_DIRECTORY, self.bot.session_generator
        )

        if not error:
            await ctx.response.send_message(content=bd.pass_str)
            return False
        else:
            await ctx.response.send_message(content=bd.fail_str)
            return True

    @app_commands.command(
        name="remove",
        description="Remove a response",
    )
    @app_commands.describe(
        trigger="Text to respond to",
        text="What the bot should respond with",
        exact="If the message should exactly match the trigger phrase to respond",
    )
    async def remove(
        self,
        ctx: Interaction,
        trigger: str = "",
        text: str = "",
        exact: Optional[bool] = None,
    ) -> None:
        # Config permission checks
        response_to_delete: Optional[CachedResponse] = self.response_service.get_resp(
            ctx.guild_id, trigger, text, exact
        )
        if response_to_delete is None:
            await ctx.response.send_message(
                content="Couldn't find a specific response to delete! Try specifying response or exact arguments.",
                ephemeral=True,
            )
            return
        async with self.bot.locks[ctx.guild_id]:
            async with self.bot.session_generator() as session:
                member = await get_or_create_member(ctx.user.id, ctx.guild_id, session)
                error = (
                    await self.response_service.get_response_remove_validation_error(
                        ctx.guild_id, member, response_to_delete
                    )
                )

        if error:
            await ctx.response.send_message(
                content=error,
                ephemeral=True,
            )
            return

        async with self.bot.locks[ctx.guild_id]:
            async with self.bot.session_generator() as session:
                error = await self.response_service.remove_response(
                    ctx.guild_id, response_to_delete, session
                )

        if not error:
            await ctx.response.send_message(content=bd.pass_str)
            return
        else:
            await ctx.response.send_message(content=bd.fail_str)
            return

    @remove.autocomplete("trigger")
    async def trigger_autocomplete(
        self, ctx: Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        trigs: set = set()
        # Add autocomplete options if they match input text, remove duplicates. 25 maximum values (discord limit)
        for response in self.bot.responses[ctx.guild_id]:
            if response.trigger not in trigs and current in response.trigger:
                trigs.add(response.trigger)
        for response in self.bot.mentions[ctx.guild_id]:
            if response.trigger not in trigs and current in response.trigger:
                trigs.add(response.trigger)
        choices = list(map(bu.autocomplete_filter, trigs))
        if len(choices) > 25:
            choices = choices[0:24]
        return choices

    @remove.autocomplete("text")
    async def response_autocomplete(self, ctx: Interaction, current: str):
        # Add autocomplete response options for the specified trigger.
        responses = [
            response.text
            for response in self.bot.responses[ctx.guild_id]
            if response.trigger == ctx.namespace["trigger"]
        ]
        choices = list(map(bu.autocomplete_filter, responses))
        if len(choices) > 25:
            choices = choices[0:24]
        return choices

    @app_commands.command(
        name="list",
        description="Show list of all responses for the server",
    )
    async def list(self, ctx: Interaction, page: int = 1):
        view = RspView(response_service=self.response_service, page=page)
        await ctx.response.send_message(
            embed=self.response_service.gen_resp_list(ctx.guild, page), view=view
        )
        return False

    @app_commands.command(
        name="clearall",
        description="Deletes ALL response data from the server (admin only)",
    )
    async def clearall(self, ctx: Interaction):
        if not ctx.user.guild_permissions.administrator:
            await ctx.response.send_message(
                content="You must be an administrator to use this command!",
                ephemeral=True,
            )
            return True

        try:
            async with self.bot.locks[ctx.guild_id]:
                async with self.bot.session_generator() as session:
                    await self.response_service.remove_all_guild_responses(
                        ctx.guild_id, session
                    )
        except Exception as e:
            logger.warning(
                f"Error deleting all responses for guild {ctx.guild_id}: {e}"
            )
            await ctx.response.send_message(content=bd.fail_str)
            return True

        await ctx.response.send_message(content=bd.pass_str)
        return False

    @commands.Cog.listener()
    async def on_message(self, message: Message):
        response = self.response_service.generate_response(message)

        if response is None:
            return False

        await message.reply(content=response)
        return False


async def setup(bot: BrBot):
    await bot.add_cog(ResponsesCog(bot))
