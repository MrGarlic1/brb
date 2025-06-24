import brbot.Core.botdata as bd
import brbot.Core.botutils as bu
import brbot.Features.Responses.data as rsp
from discord import app_commands, Interaction, Message
from discord.ext import commands
import logging

logger = logging.getLogger(__name__)


class ResponsesCog(commands.GroupCog, name='response'):

    @app_commands.command(
        name="add",
        description="Add a response",
    )
    @app_commands.describe(
        trigger='Text to respond to',
        response='What the bot should respond with',
        exact='If the message should exactly match the trigger phrase to respond'
    )
    async def add(self, ctx: Interaction, trigger: str, response: str, exact: bool):
        # Config permission checks
        if not bd.config[ctx.guild_id]["ALLOW_PHRASES"] and not exact:
            await ctx.response.send_message(
                content=f"The server does not allow for phrase-based responses.",
                ephemeral=True
            )
            return True
        if bd.config[ctx.guild_id]["LIMIT_USER_RESPONSES"]:
            user_rsps = 0
            for existing_response in bd.responses[ctx.guild_id]:
                if existing_response.user_id == int(ctx.user.id):
                    user_rsps += 1
            if user_rsps >= bd.config[ctx.guild_id]["MAX_USER_RESPONSES"]:
                await ctx.response.send_message(
                    content=f"You currently have the maximum of "
                            f"{bd.config[ctx.guild_id]['MAX_USER_RESPONSES']} responses.",
                    ephemeral=True
                )
                return True

        error = rsp.add_response(ctx.guild_id, rsp.Response(exact, trigger.lower(), response, int(ctx.user.id)))

        # Update responses
        bd.responses[ctx.guild_id] = rsp.load_responses(f"{bd.parent}/Guilds/{ctx.guild_id}/responses.json")

        if not error:
            await ctx.response.send_message(content=bd.pass_str)
        else:
            await ctx.response.send_message(content=bd.fail_str)
            return True

    @app_commands.command(
        name="remove",
        description="Remove a response",
    )
    @app_commands.describe(
        trigger='Text to respond to',
        response='What the bot should respond with',
        exact='If the message should exactly match the trigger phrase to respond'
    )
    async def remove(
            self, ctx: Interaction, trigger: str = "", response: str = "", exact: bool = None
    ):
        # Config permission checks

        if bd.config[ctx.guild_id]["USER_ONLY_DELETE"] and \
                rsp.get_resp(ctx.guild_id, trigger, response, exact).user_id != ctx.user.id:
            await ctx.response.send_message(
                content=f"The server settings do not allow you to delete other people\'s responses.",
                ephemeral=True
            )
            return True

        error = rsp.rmv_response(ctx.guild_id, rsp.Response(exact=exact, trig=trigger.lower(), text=response))
        if not error:
            await ctx.response.send_message(content=bd.pass_str)
        else:
            await ctx.response.send_message(content=bd.fail_str)
            return True

        # Update responses
        bd.responses[ctx.guild_id] = rsp.load_responses(f"{bd.parent}/Guilds/{ctx.guild_id}/responses.json")

    @remove.autocomplete("trigger")
    async def trigger_autocomplete(self, ctx: Interaction, current: str) -> list[app_commands.Choice[str]]:
        trigs: list = []
        # Add autocomplete options if they match input text, remove duplicates. 25 maximum values (discord limit)
        for response in bd.responses[ctx.guild_id]:
            if response.trig not in trigs and current in response.trig:
                trigs.append(response.trig)
        choices = list(map(bu.autocomplete_filter, trigs))
        if len(choices) > 25:
            choices = choices[0:24]
        return choices

    @remove.autocomplete("response")
    async def response_autocomplete(self, ctx: Interaction, current: str):
        # Add autocomplete response options for the specified trigger.
        responses = [
            response.text for response in bd.responses[ctx.guild_id]
            if response.trig == ctx.namespace["trigger"]
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
        view = rsp.RspView(page=page)
        await ctx.response.send_message(
            embed=rsp.gen_resp_list(ctx.guild, page),
            view=view
        )
        return False

    @app_commands.command(
        name="clearall",
        description="Deletes ALL response data from the server (admin only)",
    )
    async def clearall(self, ctx: Interaction):
        if not ctx.user.guild_permissions.administrator:
            await ctx.response.send_message(content="You must be an administrator to use this command!", ephemeral=True)
            return True

        f = open(f"{bd.parent}/Guilds/{ctx.guild_id}/responses.json", "w")
        f.close()
        bd.responses[ctx.guild_id] = []
        logger.info(f'Cleared all responses from {ctx.guild_id}.')
        await ctx.response.send_message(content=bd.pass_str)
        return False

    @commands.Cog.listener()
    async def on_message(self, message: Message):
        response = rsp.generate_response(message)

        if response is None:
            return False

        await message.reply(content=response)
        return False


async def setup(bot: commands.Bot):
    await bot.add_cog(ResponsesCog(bot))
