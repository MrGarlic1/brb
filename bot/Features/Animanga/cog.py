import interactions
import Core.botdata as bd
import Features.Animanga.data as am


class Anime(interactions.Extension):
    @interactions.slash_command(
        name="anime",
        sub_cmd_name="recommend",
        sub_cmd_description="Have the bot recommend a show for you.",
        dm_permission=True,
    )
    @interactions.slash_option(
        name="listall",
        description="Show a list of all recommendations.",
        required=False,
        opt_type=interactions.OptionType.BOOLEAN
    )
    @interactions.slash_option(
        name="force",
        description="Force updates anilist stats. WILL BE SLOW.",
        required=False,
        opt_type=interactions.OptionType.BOOLEAN,
    )
    async def show_anime_rec(self, ctx: interactions.SlashContext, listall: bool = False, force: bool = False):
        if ctx.author_id not in bd.linked_profiles:
            await ctx.send(
                content=f"Your anilist profile isn't linked! (/anilist link)"
            )
            return True
        await ctx.defer()
        await ctx.send(
            content=am.get_recommendation(
                anilist_id=bd.linked_profiles[ctx.author_id], listall=listall, force_update=force
            )
        )

    @interactions.slash_command(
        name="manga",
        sub_cmd_name="recommend",
        sub_cmd_description="Have the bot recommend a manga for you.",
        dm_permission=True,
    )
    @interactions.slash_option(
        name="listall",
        description="Show a list of all recommendations.",
        required=False,
        opt_type=interactions.OptionType.BOOLEAN
    )
    @interactions.slash_option(
        name="force",
        description="Force updates anilist stats. WILL BE SLOW.",
        required=False,
        opt_type=interactions.OptionType.BOOLEAN,
    )
    async def show_manga_rec(self, ctx: interactions.SlashContext, listall: bool = False, force: bool = False):
        if ctx.author_id not in bd.linked_profiles:
            await ctx.send(
                content=f"Your anilist profile isn't linked! (/anilist link)"
            )
            return True
        await ctx.defer()
        await ctx.send(
            content=am.get_recommendation(
                anilist_id=bd.linked_profiles[ctx.author_id], listall=listall, force_update=force, manga=True
            )
        )