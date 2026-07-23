import logging
from datetime import datetime

from brbot.Shared.Discord.buttons import NextPgButton, PrevPgButton
from dataclasses import dataclass
from discord.ui import View, Button
from discord import Interaction, ButtonStyle
from enum import Enum
from sqlalchemy.ext.asyncio import async_sessionmaker
from typing import Optional

logger = logging.getLogger(__name__)


DAILY_UPDATE_HOUR_UTC = 4

placement_emojis = {
    1: "🥇",
    2: "🥈",
    3: "🥉",
    4: "4️⃣",
    5: "5️⃣",
    6: "6️⃣",
    7: "7️⃣",
    8: "8️⃣",
    9: "9️⃣",
}
format_emojis = {}


@dataclass
class LeaderboardStats:
    consistency: float
    missed_days: int
    record: int
    record_date: datetime
    total_minutes_watched: int
    average_minutes_watched: float
    average_minutes_watched_active: float
    current_streak: int
    max_streak: int
    placements: dict[int, int]
    first_place_finishes: int
    formats: dict[str, int]


@dataclass(frozen=True)
class DailyStatSnapshot:
    user_discord_id: int
    placement: int
    minutes_watched: int
    manga_chapters: int
    episodes: int
    ln_chapters: int
    movies: int


class IgnoreRecButton(Button):
    def __init__(self):
        super().__init__(
            style=ButtonStyle.secondary,
            label="Ignore",
            custom_id="ignore_rec",
        )

    async def callback(self, interaction: Interaction):
        async with self.view.session_generator() as session:
            await self.view.rec_service.ignore_media_rec(
                user_discord_id=self.view.user_id,
                anilist_user_id=self.view.anilist_user_id,
                media_id=self.view.current_media_id,
                media_type=self.view.media_type,
                session=session,
            )
            if self.view.max_page is not None:
                self.view.max_page -= 1


class RestoreRecButton(Button):
    def __init__(self):
        super().__init__(
            style=ButtonStyle.primary, label="Stop Ignoring", custom_id="restore_rec"
        )

    async def callback(self, interaction: Interaction):
        async with self.view.session_generator() as session:
            await self.view.rec_service.restore_media_rec(
                user_discord_id=self.view.user_id,
                ignored_media_id=self.view.current_media_id,
                media_type=self.view.media_type,
                session=session,
            )
            if self.view.max_page is not None:
                self.view.max_page -= 1


class MediaType(Enum):
    Anime = False
    Manga = True


class RecView(View):
    """
    Discord UI View for handling animanga recommendation interactions.

    Attributes:
        rec_service (AnimangaService): Animanga service
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
        rec_service,
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
        self.rec_service = rec_service
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
            return False
        elif interaction.user.id != self.user_id:
            return False
        return True

    async def render(self, interaction: Interaction):
        if self.max_page is None:
            async with self.session_generator() as session:
                max_page = await self.rec_service.get_user_recommendation_count(
                    self.anilist_user_id, self.media_type, session, self.genre
                )
                self.max_page = max_page

        async with self.session_generator() as session:
            embed, media_id = await self.rec_service.gen_rec_embed_page(
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
        rec_service (AnimangaService): Animanga service
        user_id (int): discord user ID
        current_media_id (int): current displying rec media id
        media_type (str): Specify to recommend manga/anime
        session_generator (async_sessionmaker): bot DB session factory
        max_page (int): maximum number of ignored recs, if found
    """

    def __init__(
        self,
        rec_service,
        user_id: int,
        discord_username: str,
        current_media_id: int,
        media_type: MediaType,
        session_generator: async_sessionmaker,
        max_page: Optional[int] = None,
    ):
        super().__init__(timeout=60)
        self.rec_service = rec_service
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
            return False
        elif interaction.user.id != self.user_id:
            return False
        return True

    async def render(self, interaction: Interaction):
        if self.max_page is None:
            async with self.session_generator() as session:
                max_page = await self.rec_service.get_user_ignored_count(
                    self.user_id, self.media_type, session
                )
                self.max_page = max_page

        async with self.session_generator() as session:
            (
                embed,
                ignored_media_id,
            ) = await self.rec_service.get_ignored_rec_embed_page(
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
    genre_count_weight = 0.8
    genre_count_score_max = 1
    genre_user_score_weight = 1.2
    genre_user_score_max = 2
    popularity_exp = 1.3
    global_scale_exp = 0.35
    node_score_weight = 0.8
    favorite_weight = 3
    rec_show_score_weight = 1
    rec_genre_score_weight = 1.1
    score_variation = 0.2
