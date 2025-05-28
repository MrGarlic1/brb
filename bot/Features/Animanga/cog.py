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
        name="genre",
        description="Request recommendation(s) of a specific genre.",
        required=False,
        opt_type=interactions.OptionType.STRING,
        choices=[
            interactions.SlashCommandChoice(name="Action", value="Action"),
            interactions.SlashCommandChoice(name="Adventure", value="Adventure"),
            interactions.SlashCommandChoice(name="Comedy", value="Comedy"),
            interactions.SlashCommandChoice(name="Drama", value="Drama"),
            interactions.SlashCommandChoice(name="Ecchi", value="Ecchi"),
            interactions.SlashCommandChoice(name="Fantasy", value="Fantasy"),
            interactions.SlashCommandChoice(name="Horror", value="Horror"),
            interactions.SlashCommandChoice(name="Mahou Shoujo", value="Mahou Shoujo"),
            interactions.SlashCommandChoice(name="Mecha", value="Mecha"),
            interactions.SlashCommandChoice(name="Music", value="Music"),
            interactions.SlashCommandChoice(name="Mystery", value="Mystery"),
            interactions.SlashCommandChoice(name="Psychological", value="Psychological"),
            interactions.SlashCommandChoice(name="Romance", value="Romance"),
            interactions.SlashCommandChoice(name="Sci-Fi", value="Sci-Fi"),
            interactions.SlashCommandChoice(name="Slice of Life", value="Slice of Life"),
            interactions.SlashCommandChoice(name="Sports", value="Sports"),
            interactions.SlashCommandChoice(name="Supernatural", value="Supernatural"),
            interactions.SlashCommandChoice(name="Thriller", value="Thriller"),
        ]
    )
    @interactions.slash_option(
        name="force",
        description="Force updates anilist stats. WILL BE SLOW.",
        required=False,
        opt_type=interactions.OptionType.BOOLEAN,
    )
    async def show_anime_rec(
            self, ctx: interactions.SlashContext, listall: bool = False, genre: str = "", force: bool = False
    ):
        if ctx.author_id not in bd.linked_profiles:
            await ctx.send(
                content=f"Your anilist profile isn't linked! (/anilist link)"
            )
            return True
        await ctx.defer()
        await ctx.send(
            content=await am.get_recommendation(
                anilist_id=bd.linked_profiles[ctx.author_id], listall=listall, requested_genre=genre, force_update=force
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
            content=await am.get_recommendation(
                anilist_id=bd.linked_profiles[ctx.author_id], listall=listall, force_update=force, manga=True
            )
        )