import interactions
import Core.botdata as bd
import json
from Core.botutils import dict_to_choices

config_keys = {
    "Allow Phrase-Based Responses": "ALLOW_PHRASES",
    "Limit # of User Responses": "LIMIT_USER_RESPONSES",
    "Maximum # of User Responses": "MAX_USER_RESPONSES",
    "Restrict Response Deletion": "USER_ONLY_DELETE",
}


class Config(interactions.Extension):
    @interactions.slash_command(
        name="config",
        sub_cmd_name="set",
        sub_cmd_description="Configure the bot's server settings",
        default_member_permissions=interactions.Permissions.ADMINISTRATOR,
        dm_permission=False
    )
    @interactions.slash_option(
        name="setting",
        description="Server setting to change/set",
        opt_type=interactions.OptionType.STRING,
        choices=dict_to_choices(config_keys)
    )
    @interactions.slash_option(
        name="value",
        description="The value to set for this setting",
        opt_type=interactions.OptionType.STRING,
        autocomplete=True
    )
    async def config_set(self, ctx: interactions.SlashContext, setting: str, value: str):
        if setting not in config_keys:
            await ctx.send(content=bd.fail_str)
            return True

        config_key = config_keys[setting]
        try:
            if config_key == "MAX_USER_RESPONSES":
                value = int(value)
                if value < 1 or value > 999999:
                    raise ValueError
            else:
                value = bool(value)
        except ValueError:
            await ctx.send(content=bd.fail_str)
            return True

        bd.config[ctx.guild_id][config_key] = value
        with open(f"{bd.parent}/Guilds/{ctx.guild_id}/config.json", "w") as f:
            json.dump(bd.config[ctx.guild_id], f, indent=4)
        await ctx.send(content=bd.pass_str)

    @config_set.autocomplete("value")
    async def autocomplete(self, ctx: interactions.AutocompleteContext):
        setting = ctx.kwargs.get("setting")
        if setting not in config_keys:
            choices = []
        elif config_keys[setting] == "MAX_USER_RESPONSES":
            choices = ["Please enter a positive integer."]
        else:
            choices = ["True", "False"]
        await ctx.send(choices)

    @interactions.slash_command(
        name="config",
        sub_cmd_name="wipe",
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
