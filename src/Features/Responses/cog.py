import interactions
import botdata as bd
import asyncio
import botutils as bu
import Features.Responses.data as rsp


class Responses(interactions.Extension):
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
    async def add_response(self, ctx: interactions.SlashContext, trigger: str, response: str, exact: bool):
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
                    content=f"You currently have the maximum of "
                            f"{bd.config[ctx.guild_id]['MAX_USER_RESPONSES']} responses.",
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
    async def remove_response(
            self, ctx: interactions.SlashContext, trigger: str = "", response: str = "", exact: bool = None
    ):
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
    async def autocomplete(self, ctx: interactions.AutocompleteContext):
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
    async def autocomplete(self, ctx: interactions.AutocompleteContext):
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
    async def listrsps(self, ctx: interactions.SlashContext, page: int = 1):
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
    async def delete_data(self, ctx: interactions.SlashContext):
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
    async def mod_add(self, ctx: interactions.SlashContext, trigger: str, response: str, exact: bool):
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
    async def mod_remove(
            self, ctx: interactions.SlashContext, trigger: str = "", response: str = "", exact: bool = True
    ):
        error = rsp.rmv_response(ctx.guild_id, rsp.Response(exact, trigger.lower(), response))
        if not error:
            await ctx.send(content=bd.pass_str)
        else:
            await ctx.send(content=bd.fail_str)
            return True

        # Update responses
        bd.responses[ctx.guild_id] = rsp.load_responses(f"{bd.parent}/Guilds/{ctx.guild_id}/responses.json")

    @mod_remove.autocomplete("trigger")
    async def autocomplete(self, ctx: interactions.AutocompleteContext):
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
    async def autocomplete(self, ctx: interactions.AutocompleteContext):
        # Add autocomplete response options for the specified trigger.
        responses = [
            response.text for response in bd.responses[ctx.guild_id]
            if response.trig == ctx.kwargs.get("trigger")
        ]
        choices = list(map(bu.autocomplete_filter, responses))
        if len(choices) > 25:
            choices = choices[0:24]
        await ctx.send(choices=choices)
