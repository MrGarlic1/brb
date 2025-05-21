import interactions
import Core.botdata as bd
import Features.Anime.data as anime


class Anime(interactions.Extension):
    @interactions.slash_command(
        name="anime",
        sub_cmd_name="recommend",
        sub_cmd_description="Have the bot recommend a show for you.",
        dm_permission=True,
    )
    async def get_recommendation(self, ctx: interactions.SlashContext):
        if ctx.author_id not in bd.linked_profiles:
            await ctx.send(
                content=f"Your anilist profile isn't linked! (/anilist link)"
            )
            return True
        await ctx.defer()
        await ctx.send(content=anime.fetch_recommendations(bd.linked_profiles[ctx.author_id]))
