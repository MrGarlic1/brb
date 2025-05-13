import interactions


class Help(interactions.Extension):
    @interactions.slash_command(
        name="help",
        description="View information about the bot's commands.",
        dm_permission=True,
    )
    @interactions.slash_option(
        name="category",
        description="Category of commands to view",
        required=False,
        opt_type=interactions.OptionType.STRING,
        choices=[
            interactions.SlashCommandChoice(name="General", value="General"),
            interactions.SlashCommandChoice(name="Responses", value="Responses"),
            interactions.SlashCommandChoice(name="Trains", value="Trains"),
            interactions.SlashCommandChoice(name="Bingo", value="Bingo"),
            interactions.SlashCommandChoice(name="Config", value="Config"),
        ]
    )
    async def display_help(self, ctx: interactions.SlashContext, category: str = "General"):
        pass