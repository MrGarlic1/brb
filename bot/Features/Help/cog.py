import interactions
import Features.Help.data as hp


class Help(interactions.Extension):
    @interactions.slash_command(
        name="help",
        description="View information about the bot's commands.",
        dm_permission=True,
    )
    async def display_help(self, ctx: interactions.SlashContext):
        await ctx.send(embed=hp.base_help_embed(), components=hp.help_category_menu)
