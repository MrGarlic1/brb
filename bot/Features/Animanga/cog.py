import interactions
import Core.botdata as bd
import Features.Animanga.data as am
import Core.botutils as bu
from asyncio import create_task
from httpx import RequestError


class Anime(interactions.Extension):
    @interactions.slash_command(
        name="recommend",
        description="Have the bot recommend anime/manga for you.",
        dm_permission=True,
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
        name="medium",
        description="Choose to recommend anime/manga",
        required=False,
        opt_type=interactions.OptionType.STRING,
        choices=[
            interactions.SlashCommandChoice(name="Anime", value="anime"),
            interactions.SlashCommandChoice(name="Manga", value="manga")
        ]
    )
    @interactions.slash_option(
        name="force",
        description="Force updates anilist stats. WILL BE SLOW.",
        required=False,
        opt_type=interactions.OptionType.BOOLEAN,
    )
    async def show_animanga_rec(
            self, ctx: interactions.SlashContext, genre: str = "", medium: str = "anime", force: bool = False
    ):
        if ctx.author_id not in bd.linked_profiles:
            await ctx.send(
                content=f"Your anilist profile isn't linked! (/anilist link)"
            )
            return True

        await ctx.defer()
        try:
            await am.check_recommendation(
                anilist_id=bd.linked_profiles[ctx.author_id],
                media_type=medium,
                force_update=force,
            )
        except RequestError:
            await ctx.send("An error occurred connecting to Anilist. Please try again later.")
            return True

        embed = am.get_rec_embed(
            anilist_id=bd.linked_profiles[ctx.author_id],
            media_type=medium,
            genre=genre,
            page=0,
        )
        rec_msg = await ctx.send(embed=embed, components=[am.prev_rec_button(), am.next_rec_button()])
        channel = ctx.channel
        sent = bu.ListMsg(
            rec_msg.id,
            0,
            ctx.guild,
            channel,
            "rec",
            {"anilist_id": bd.linked_profiles[ctx.author_id], "genre": genre, "animanga": animanga}
        )

        bd.active_msgs.append(sent)
        _ = create_task(
            bu.close_msg(sent, 300, ctx)
        )
        return False
