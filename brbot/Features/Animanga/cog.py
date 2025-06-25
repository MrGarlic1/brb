import brbot.Core.botdata as bd
import brbot.Features.Animanga.data as am
from brbot.Core.anilist import query_user_id
from httpx import RequestError
from json import dump
from discord import app_commands, Interaction
from discord.ext import commands


class AnimangaCog(commands.GroupCog, name="animanga"):
    @app_commands.command(
        name="link", description="Link your discord profile to an anilist profile"
    )
    @app_commands.describe(username="Anilist username")
    async def link(self, ctx: Interaction, username: str):
        if username is None:
            await ctx.response.send_message(
                content="Could not find anilist profile, please check username!"
            )
            return True
        anilist_user_id = await query_user_id(username)
        if anilist_user_id is None:
            await ctx.response.send_message(
                content="Could not find anilist profile, please check username!"
            )
            return True

        bd.linked_profiles[ctx.user.id] = anilist_user_id
        with open(f"{bd.parent}/Data/linked_profiles.json", "w") as f:
            dump(bd.linked_profiles, f, separators=(",", ":"))
        await ctx.response.send_message(content=bd.pass_str)
        return False

    @app_commands.command(
        name="recommend", description="Have the bot recommend anime/manga for you."
    )
    @app_commands.describe(
        genre="Request recommendation(s) of a specific genre.",
        medium="Choose to recommend anime/manga",
        force="Force updates anilist stats. WILL BE SLOW.",
    )
    @app_commands.choices(
        genre=[
            app_commands.Choice(name="Action", value="Action"),
            app_commands.Choice(name="Adventure", value="Adventure"),
            app_commands.Choice(name="Comedy", value="Comedy"),
            app_commands.Choice(name="Drama", value="Drama"),
            app_commands.Choice(name="Ecchi", value="Ecchi"),
            app_commands.Choice(name="Fantasy", value="Fantasy"),
            app_commands.Choice(name="Horror", value="Horror"),
            app_commands.Choice(name="Mahou Shoujo", value="Mahou Shoujo"),
            app_commands.Choice(name="Mecha", value="Mecha"),
            app_commands.Choice(name="Music", value="Music"),
            app_commands.Choice(name="Mystery", value="Mystery"),
            app_commands.Choice(name="Psychological", value="Psychological"),
            app_commands.Choice(name="Romance", value="Romance"),
            app_commands.Choice(name="Sci-Fi", value="Sci-Fi"),
            app_commands.Choice(name="Slice of Life", value="Slice of Life"),
            app_commands.Choice(name="Sports", value="Sports"),
            app_commands.Choice(name="Supernatural", value="Supernatural"),
            app_commands.Choice(name="Thriller", value="Thriller"),
        ],
        medium=[
            app_commands.Choice(name="Anime", value="anime"),
            app_commands.Choice(name="Manga", value="manga"),
        ],
    )
    async def show_animanga_rec(
        self,
        ctx: Interaction,
        genre: str = "",
        medium: str = "anime",
        force: bool = False,
    ):
        if ctx.user.id not in bd.linked_profiles:
            await ctx.response.send_message(
                content="Your anilist profile isn't linked! (/anilist link)"
            )
            return True

        await ctx.response.defer()
        try:
            await am.check_recommendation(
                anilist_id=bd.linked_profiles[ctx.user.id],
                media_type=medium,
                force_update=force,
            )
        except RequestError:
            await ctx.followup.send(
                "An error occurred connecting to Anilist. Please try again later."
            )
            return True

        embed = am.get_rec_embed(
            username=ctx.user.name,
            anilist_id=bd.linked_profiles[ctx.user.id],
            media_type=medium,
            genre=genre,
            page=0,
        )
        view = am.RecView(
            anilist_id=bd.linked_profiles[ctx.user.id],
            media_type=medium,
            genre=genre,
            username=ctx.user.name,
        )
        await ctx.followup.send(embed=embed, view=view)
        return False


async def setup(bot: commands.Bot):
    await bot.add_cog(AnimangaCog(bot))
