import logging
from brbot.Shared.Discord.buttons import NextPgButton, PrevPgButton
from discord.ui import View, Button
from discord import Interaction, ButtonStyle
from enum import Enum
from sqlalchemy.ext.asyncio import async_sessionmaker
from typing import Optional

logger = logging.getLogger(__name__)


class IgnoreRecButton(Button):
    def __init__(self):
        super().__init__(
            style=ButtonStyle.secondary,
            label="Ignore",
            custom_id="ignore_rec",
        )


class RestoreRecButton(Button):
    def __init__(self):
        super().__init__(
            style=ButtonStyle.primary, label="Stop Ignoring", custom_id="restore_rec"
        )


class MediaType(Enum):
    Anime = False
    Manga = True


class RecView(View):
    """
    Discord UI View for handling animanga recommendation interactions.

    Attributes:
        animanga_service (AnimangaService): Animanga service
        user_id (int): discord user ID
        anilist_user_id (int): anilist user ID recommending to
        anilist_username (str): anilist username recommending to
        current_media_id (int): current displying rec media id
        media_type (str): Specify to recommend manga/anime
        genre (str): Limit recommendations to specified genre
        session_generator (async_sessionmaker): bot DB session factory
    """

    def __init__(
        self,
        animanga_service,
        user_id: int,
        anilist_user_id: int,
        anilist_username: str,
        current_media_id: int,
        media_type: MediaType,
        genre: str,
        session_generator: async_sessionmaker,
        max_page: Optional[int] = None,
    ):
        super().__init__(timeout=60)
        self.animanga_service = animanga_service
        self.add_item(PrevPgButton())
        self.add_item(NextPgButton())
        self.add_item(IgnoreRecButton())
        self.user_id = user_id
        self.anilist_user_id = anilist_user_id
        self.anilist_username = anilist_username
        self.current_media_id = current_media_id
        self.media_type = media_type
        self.genre = genre
        self.page = 0
        self.session_generator = session_generator
        self.max_page = max_page

    async def interaction_check(self, interaction: Interaction) -> bool:
        if self.current_media_id is None:
            await interaction.response.defer()
            return True
        if interaction.data["custom_id"] == "prev_page":
            self.page -= 1
        elif interaction.data["custom_id"] == "next_page":
            self.page += 1
        elif interaction.user.id != self.user_id:
            await interaction.response.defer()
            return True
        elif interaction.data["custom_id"] == "ignore_rec":
            async with self.session_generator() as session:
                await self.animanga_service.ignore_media_rec(
                    user_discord_id=self.user_id,
                    anilist_user_id=self.anilist_user_id,
                    media_id=self.current_media_id,
                    media_type=self.media_type,
                    session=session,
                )
                if self.max_page is not None:
                    self.max_page -= 1

        if self.max_page is None:
            async with self.session_generator() as session:
                max_page = await self.animanga_service.get_user_recommendation_count(
                    self.anilist_user_id, self.media_type, session, self.genre
                )
                self.max_page = max_page

        async with self.session_generator() as session:
            embed, media_id = await self.animanga_service.gen_rec_embed_page(
                anilist_user_id=self.anilist_user_id,
                anilist_username=self.anilist_username,
                media_type=self.media_type,
                genre=self.genre,
                page=self.page,
                session=session,
                max_page=self.max_page,
            )
        self.current_media_id = media_id

        await interaction.response.edit_message(embed=embed, view=self)
        return False


class IgnoredRecView(View):
    """
    Discord UI View for handling animanga recommendation interactions.

    Attributes:
        animanga_service (AnimangaService): Animanga service
        user_id (int): discord user ID
        current_media_id (int): current displying rec media id
        media_type (str): Specify to recommend manga/anime
        session_generator (async_sessionmaker): bot DB session factory
        max_page (int): maximum number of ignored recs, if found
    """

    def __init__(
        self,
        animanga_service,
        user_id: int,
        discord_username: str,
        current_media_id: int,
        media_type: MediaType,
        session_generator: async_sessionmaker,
        max_page: Optional[int] = None,
    ):
        super().__init__(timeout=60)
        self.animanga_service = animanga_service
        self.add_item(PrevPgButton())
        self.add_item(NextPgButton())
        self.add_item(RestoreRecButton())
        self.user_id = user_id
        self.discord_username = discord_username
        self.current_media_id = current_media_id
        self.media_type = media_type
        self.page = 0
        self.session_generator = session_generator
        self.max_page = max_page

    async def interaction_check(self, interaction: Interaction) -> bool:
        if self.current_media_id is None:
            await interaction.response.defer()
            return True
        if interaction.data["custom_id"] == "prev_page":
            self.page -= 1
        elif interaction.data["custom_id"] == "next_page":
            self.page += 1
        elif interaction.user.id != self.user_id:
            await interaction.response.defer()
            return True
        elif interaction.data["custom_id"] == "restore_rec":
            async with self.session_generator() as session:
                await self.animanga_service.restore_media_rec(
                    user_discord_id=self.user_id,
                    ignored_media_id=self.current_media_id,
                    media_type=self.media_type,
                    session=session,
                )
                if self.max_page is not None:
                    self.max_page -= 1

        if self.max_page is None:
            async with self.session_generator() as session:
                max_page = await self.animanga_service.get_user_ignored_count(
                    self.user_id, self.media_type, session
                )
                self.max_page = max_page

        async with self.session_generator() as session:
            (
                embed,
                ignored_media_id,
            ) = await self.animanga_service.get_ignored_rec_embed_page(
                username=self.discord_username,
                media_type=self.media_type,
                page=self.page,
                user_discord_id=self.user_id,
                max_page=self.max_page,
                session=session,
            )
        self.current_media_id = ignored_media_id

        await interaction.response.edit_message(embed=embed, view=self)
        return False


class RecScoringModel:
    """Contains weights/factors/corrections for animanga rec scoring"""

    global_mean = 65
    genre_count_weight = 1.3
    genre_count_score_max = 1
    genre_user_score_weight = 0.8
    genre_user_score_max = 2
    popularity_exp = 1.3
    global_scale_exp = 0.35
    node_score_weight = 0.8
    favorite_weight = 3
    rec_show_score_weight = 1
    rec_genre_score_weight = 1.1
    score_variation = 0.2
