import interactions
import botdata as bd
import json


class Config(interactions.Extension):
    @interactions.slash_command(
        name="config",
        sub_cmd_name="reset",
        sub_cmd_description="Resets ALL server settings to default.",
        default_member_permissions=interactions.Permissions.ADMINISTRATOR,
        dm_permission=False
    )
    async def cfg_reset(self, ctx: interactions.SlashContext):
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
    async def cfg_view(self, ctx: interactions.SlashContext):
        await ctx.send(
            content=f"Allow Phrases: {bd.config[ctx.guild_id]['ALLOW_PHRASES']}\n"
                    f"Limit Responses: {bd.config[ctx.guild_id]['LIMIT_USER_RESPONSES']}\n"
                    f"Response Limit # (Only if Limit Responses is True): "
                    f"{bd.config[ctx.guild_id]['MAX_USER_RESPONSES']}\n"
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
    async def cfg_user_perms(self, ctx: interactions.SlashContext, enable: bool = True):
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
    async def cfg_set_limit(self, ctx: interactions.SlashContext, enable: bool = True, limit: int = 10):
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
    async def cfg_allow_phrases(self, ctx: interactions.SlashContext, enable: bool = True):
        bd.config[ctx.guild_id]["ALLOW_PHRASES"] = enable
        with open(f"{bd.parent}/Guilds/{ctx.guild_id}/config.json", "w") as f:
            json.dump(bd.config[ctx.guild_id], f, indent=4)
        await ctx.send(content=bd.pass_str)
