import logging
from brbot.Shared.buttons import NextPgButton, PrevPgButton
from discord.ui import View, Button
from discord import Interaction, ButtonStyle
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MediaRec:
    def __init__(
        self,
        media_id: int,
        title: str,
        score: float = 0,
        genres: list[str] = (),
        cover_url: str = None,
        mean_score: float = None,
    ):
        self.media_id = media_id
        self.title = title
        self.score = score
        self.genres = genres
        self.cover_url = cover_url
        self.mean_score = mean_score

    def __lt__(self, other):
        return self.score < other.score

    def __eq__(self, other):
        if isinstance(other, MediaRec):
            return other.media_id == self.media_id
        else:
            return other == self.media_id

    @classmethod
    def from_dict(cls, data):
        if not data:
            return None
        return cls(**data)


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


class RecView(View):
    """
    Discord UI View for handling animanga recommendation interactions.

    Attributes:
        user_anilist_id (str): Anilist id to recommend for
        username (str): Discord username
        media_type (str): Specify to recommend manga/anime
        genre (str): Limit recommendations to specified genre
        page (int): Which recommendation in user's rec list to display
    """

    def __init__(
        self,
        rec_service,
        user_discord_id: int,
        username: str,
        user_anilist_id: int,
        media_rec: MediaRec,
        media_type: str,
        genre: str,
    ):
        super().__init__(timeout=60)
        self.rec_service = rec_service
        self.add_item(PrevPgButton())
        self.add_item(NextPgButton())
        self.add_item(IgnoreRecButton())
        self.user_anilist_id = user_anilist_id
        self.user_discord_id = user_discord_id
        self.media_rec = media_rec
        self.username = username
        self.media_type = media_type
        self.genre = genre
        self.page = 0

    async def interaction_check(self, interaction: Interaction) -> bool:
        if self.media_rec is None:
            await interaction.response.defer()
            return True
        if interaction.data["custom_id"] == "prev_page":
            self.page -= 1
        elif interaction.data["custom_id"] == "next_page":
            self.page += 1
        elif interaction.user.id != self.user_discord_id:
            return True
        elif interaction.data["custom_id"] == "ignore_rec":
            self.rec_service.ignore_media_rec(
                user_anilist_id=self.user_anilist_id,
                user_discord_id=self.user_discord_id,
                media_rec=self.media_rec,
                media_type=self.media_type,
            )

        embed, media_rec = self.rec_service.get_rec_embed(
            username=self.username,
            media_type=self.media_type,
            genre=self.genre,
            page=self.page,
            anilist_id=self.user_anilist_id,
        )
        self.media_rec = media_rec

        await interaction.response.edit_message(embed=embed, view=self)
        return False


class IgnoredRecView(View):
    """
    Discord UI View for handling animanga ignored recommendation interactions.

    Attributes:
        username (str): Discord username
        media_type (str): Specify to recommend manga/anime
        genre (str): Limit recommendations to specified genre
        page (int): Which recommendation in user's rec list to display
    """

    def __init__(
        self,
        rec_service,
        user_discord_id: int,
        username: str,
        ignored_media_rec: MediaRec,
        media_type: str,
    ):
        super().__init__(timeout=60)
        self.rec_service = rec_service
        self.add_item(PrevPgButton())
        self.add_item(NextPgButton())
        self.add_item(RestoreRecButton())
        self.user_discord_id = user_discord_id
        self.ignored_media_rec = ignored_media_rec
        self.username = username
        self.media_type = media_type
        self.page = 0

    async def interaction_check(self, interaction: Interaction) -> bool:
        if self.ignored_media_rec is None:
            await interaction.response.defer()
            return True
        if interaction.data["custom_id"] == "prev_page":
            self.page -= 1
        elif interaction.data["custom_id"] == "next_page":
            self.page += 1
        elif interaction.user.id != self.user_discord_id:
            return True
        elif interaction.data["custom_id"] == "restore_rec":
            self.rec_service.restore_media_rec(
                user_discord_id=self.user_discord_id,
                ignored_media_rec=self.ignored_media_rec,
                media_type=self.media_type,
            )

        embed, ignored_media_rec = self.rec_service.get_ignored_rec_embed(
            username=self.username,
            media_type=self.media_type,
            page=self.page,
            user_discord_id=self.user_discord_id,
        )
        self.ignored_media_rec = ignored_media_rec

        await interaction.response.edit_message(embed=embed, view=self)
        return False


class RecScoringModel:
    """Contains weights/factors/corrections for animanga rec scoring"""

    global_mean = 65
    genre_count_weight = 0.16
    popularity_exp = 1.5
    global_scale_exp = 0.35
    node_score_weight = 0.8
    favorite_weight = 3
    rec_show_score_weight = 1
    rec_genre_score_weight = 1.5
    score_variation = 0.2
