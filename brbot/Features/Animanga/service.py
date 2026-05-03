import logging
from asyncio import gather, sleep, Semaphore
from datetime import datetime
from random import uniform

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, List, Tuple, Sequence
from brbot.Features.Animanga.data import RecScoringModel, MediaType
from brbot.db.models import Recommendation, IgnoredRecommendation, User
from httpx import AsyncClient, ReadTimeout, RequestError, post
from discord import Embed

logger = logging.getLogger(__name__)


class AnimangaService:
    def __init__(self):
        self.known_manga_recs = {}
        self.known_anime_recs = {}

    @staticmethod
    def _signed_power_floor(x, p, f):
        return min(abs(x) ** p, f) * (1 if x >= 0 else -1)

    @staticmethod
    async def query_user_statistics(
        anilist_id: int, media_type: MediaType
    ) -> Optional[Dict]:
        """
        Queries anilist for user statistics used for weighting/scoring of animanga recommendations

        Args:
            anilist_id (int): Anilist user ID to query
            media_type (str): Specifies anime or manga statistics

        Returns:
            dict: Anilist media type user statistics data
        """
        media_type_str = media_type.name.lower()
        query = f"""
        query User($userId: Int) {{
          User(id: $userId) {{
            statistics {{
              {media_type_str} {{
                count
                meanScore
                standardDeviation
                genres {{
                  count
                  genre
                  meanScore
                }}
              }}
            }}
            favourites {{
              {media_type_str} {{
                nodes {{
                  id
                }}
              }}
            }}
          }}
        }}
        """
        variables = {"userId": anilist_id}
        logger.info(f"Querying user statistics for {anilist_id} ({media_type_str})")

        try:
            response = post(
                url="https://graphql.anilist.co",
                json={"query": query, "variables": variables},
            )
        except ReadTimeout as e:
            logger.error(f"Request timed out fetching {anilist_id}: {e}")
            return None
        if response.status_code == 200:
            user_data = response.json()["data"]["User"]
            if user_data["statistics"][media_type_str]["count"]:
                favorites = [
                    fav["id"]
                    for fav in user_data["favourites"][media_type_str]["nodes"]
                ]
                user_data["favourites"][media_type_str] = favorites
                return user_data

        logger.error(f"Failed to fetch user statistics for {anilist_id}")
        return None

    @staticmethod
    async def query_media_recs(
        anilist_id: int, media_type: MediaType, watched_count: int
    ) -> Optional[List[Dict]]:
        """
        Queries anilist for user list data used for weighting/scoring of animanga recommendations

        Args:
            anilist_id (int): Anilist user ID to query
            media_type (MediaType): Specifies anime or manga statistics
            watched_count (int): Completed entries on user's list

        Returns:
            Optional[list[dict]]: Anilist media list collection data
        """
        media_type_str = media_type.name.lower()
        query = """
        query MediaListCollection($userId: Int, $type: MediaType, $statusNotIn: [MediaListStatus], $sort: [RecommendationSort], $perPage: Int, $perChunk: Int, $chunk: Int) {
          MediaListCollection(userId: $userId, type: $type, status_not_in: $statusNotIn, perChunk: $perChunk, chunk: $chunk) {
            lists {
              entries {
                score
                status
                progress
                media {
                  id
                  format
                  episodes
                  chapters
                  popularity
                  recommendations(sort: $sort, perPage: $perPage) {
                    nodes {
                      rating
                      mediaRecommendation {
                        format
                        id
                        coverImage {
                          large
                        }
                        genres
                        meanScore
                        popularity
                        title {
                          romaji
                        }
                        relations {
                          edges {
                            relationType
                          }
                          nodes {
                            id
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """

        chunk_size = 100
        max_concurrent = Semaphore(6)

        async def query_list_recommendations(session: AsyncClient, chunk):
            max_attempts = 3
            for attempt in range(max_attempts):
                req_vars = {
                    "userId": anilist_id,
                    "type": media_type_str.upper(),
                    "statusNotIn": "PLANNING",
                    "perPage": 8,
                    "sort": "RATING_DESC",
                    "perChunk": chunk_size,
                    "chunk": chunk,
                }
                logger.debug(f"Querying chunk {chunk} for {anilist_id}")
                async with max_concurrent:
                    try:
                        data = await session.post(
                            url="https://graphql.anilist.co",
                            json={"query": query, "variables": req_vars},
                            timeout=10,
                        )
                        if data.status_code == 200:
                            return data
                    except ReadTimeout:
                        logger.warning(
                            f"List data chunk {chunk} for {anilist_id} timed out"
                        )
                logger.warning(
                    f"Attempt {attempt + 1}/{max_attempts} failed for chunk {chunk}"
                )
                await sleep((1.75**attempt) + uniform(0, 1))

            logger.warning(
                f"Failed to get list data chunk {chunk} after {max_attempts}"
            )
            return None

        tasks: list = []

        logger.info(f"Querying user list data for {anilist_id} ({media_type_str})")
        async with AsyncClient() as client:
            for i in range(1, watched_count // chunk_size + 2):
                tasks.append(query_list_recommendations(client, i))

            raw_list_data = await gather(*tasks)

        full_rec_list: list = []
        for data_chunk in raw_list_data:
            if data_chunk is None:
                continue
            if data_chunk.status_code != 200:
                continue
            data_chunk = data_chunk.json()["data"]["MediaListCollection"]["lists"]
            for anime_list in data_chunk:
                anime_list = anime_list["entries"]
                full_rec_list += anime_list

        return full_rec_list

    @staticmethod
    async def fetch_new_recommendation_api_data(
        anilist_id: int, media_type: MediaType
    ) -> Tuple[List, Dict, List]:
        """
        Wrapper function for fetching anilist data for animanga recs

        Args:
            anilist_id (int): Anilist user ID to query
            media_type (MediaType): Specifies anime or manga statistics

        Returns:
            tuple: Tuple containing user list data, user statistics, and favorites

        Raises:
            RequestError if either user statistics or list data is empty
        """
        user_data = await AnimangaService.query_user_statistics(
            anilist_id=anilist_id, media_type=media_type
        )
        media_type_str = media_type.name.lower()
        if not user_data:
            raise RequestError("Error obtaining data from anilist.")
        user_stats = user_data["statistics"][media_type_str]
        user_favorites = user_data["favourites"][media_type_str]

        list_data = await AnimangaService.query_media_recs(
            anilist_id=anilist_id,
            media_type=media_type,
            watched_count=user_stats["count"],
        )
        if not list_data:
            raise RequestError("Error obtaining data from anilist.")

        return list_data, user_stats, user_favorites

    @staticmethod
    def calculate_rec_scores(
        list_data: List[Dict],
        user_stats: Dict,
        user_favorites: List[int],
        ignored_media_ids: Sequence[int],
        anilist_user_id: int,
        media_type: MediaType,
    ) -> List[Recommendation]:
        """
        Scoring algorithm for animanga recs

        Args:
            list_data (list[dict]): Anilist media list collection data
            user_stats (dict): Anilist user statistics
            user_favorites (list[int]): List of user favorited media IDs
            ignored_media_ids (list[int]): List of user's ignored media IDs to avoid recommending
            anilist_user_id (int): Anilist user ID
            media_type: MediaType enum value specifying anime/manga

        Returns:
            list[Recommendation]: List of user's recommendations
        """
        model = RecScoringModel()

        # Pre-processing: Obtain max user score, collect watched show info, calculate user genre scores
        max_score = 1
        max_popularity = 0
        seen_show_ids = set()
        for list_entry in list_data:
            seen_show_ids.add(list_entry["media"]["id"])
            if list_entry["score"] > max_score:
                max_score = list_entry["score"]
            if list_entry["media"]["popularity"] > max_popularity:
                max_popularity = list_entry["media"]["popularity"]

        max_genre_z_score = 0
        for genre in user_stats["genres"]:
            genre_z_score = (genre["meanScore"] - user_stats["meanScore"]) / max(
                user_stats["standardDeviation"], 1
            )
            if genre_z_score > max_genre_z_score:
                max_genre_z_score = genre_z_score

        user_genre_scores = {}
        for genre in user_stats["genres"]:
            genre_name = genre["genre"]
            if not genre["meanScore"]:
                user_genre_scores[genre_name] = 0
            else:
                genre_z_score = (genre["meanScore"] - user_stats["meanScore"]) / max(
                    user_stats["standardDeviation"], 1
                )
                user_genre_scores[genre_name] = AnimangaService._signed_power_floor(
                    x=genre_z_score
                    / max(max_genre_z_score, 0.001)
                    * model.genre_user_score_weight,
                    p=1,
                    f=model.genre_user_score_max,
                )
                user_genre_scores[genre_name] += (
                    AnimangaService._signed_power_floor(
                        x=(genre["count"] - 0.40 * len(seen_show_ids))
                        / len(seen_show_ids),
                        p=0.6,
                        f=model.genre_count_score_max,
                    )
                    * model.genre_count_weight
                )

        recommendation_scores: Dict[int, Recommendation] = {}
        for list_entry in list_data:
            if not list_entry["media"]["recommendations"]["nodes"]:
                continue

            if list_entry["status"] == "DROPPED":
                continue

            # If source show isn't complete, weight recommendations by % of media viewed
            if list_entry["status"] in ("PAUSED", "CURRENT"):
                if not list_entry["progress"]:
                    list_entry["progress"] = 0

                if list_entry["media"]["episodes"]:
                    progress_weight = (
                        list_entry["progress"] / list_entry["media"]["episodes"]
                    )
                elif list_entry["media"]["chapters"]:
                    progress_weight = (
                        list_entry["progress"] / list_entry["media"]["chapters"]
                    )
                else:
                    progress_weight = 0
            else:
                progress_weight = 1

            # Weight each show's recommendation by strength of recommendation on the site
            max_show_recs = max(8, len(list_entry["media"]["recommendations"]["nodes"]))
            max_rec_rating = list_entry["media"]["recommendations"]["nodes"][0][
                "rating"
            ]
            if max_rec_rating == 0:
                continue

            favorite_weight = (
                model.favorite_weight
                if list_entry["media"]["id"] in user_favorites
                else 1
            )

            for show_rec in list_entry["media"]["recommendations"]["nodes"][
                0:max_show_recs
            ]:
                rec_total_weight = show_rec["rating"] / max_rec_rating

                media_rec = show_rec["mediaRecommendation"]
                # Filter out bad data from anilist
                if media_rec is None:
                    continue
                if (
                    media_rec["id"] in seen_show_ids
                    or media_rec["id"] in ignored_media_ids
                    or media_rec["format"] == "MUSIC"
                ):
                    continue
                if not media_rec["meanScore"]:
                    media_rec["meanScore"] = model.global_mean

                # Filter out shows with prequels that have not been seen yet
                try:
                    if any(
                        related_show[0]["relationType"] == "PREQUEL"
                        and related_show[1]["id"] not in seen_show_ids
                        for related_show in zip(
                            media_rec["relations"]["edges"],
                            media_rec["relations"]["nodes"],
                        )
                    ):
                        continue
                except KeyError:
                    logger.debug(
                        f'No related media found for {media_rec["title"]["romaji"]}'
                    )

                rec_pop_factor = 1 - media_rec["popularity"] / max_popularity
                rec_pop_factor = (
                    rec_pop_factor**model.popularity_exp if rec_pop_factor > 0 else 0.1
                )

                node_score = (
                    model.node_score_weight
                    * (list_entry["score"] / max_score - user_stats["meanScore"] / 100)
                    / max(user_stats["standardDeviation"], 1)
                    if list_entry["score"] != 0
                    else 0
                )

                rec_show_score = (
                    model.rec_show_score_weight
                    * (media_rec["meanScore"] - model.global_mean)
                    / 100
                )
                rec_genre_score = 0
                for genre in media_rec["genres"]:
                    try:
                        rec_genre_score += user_genre_scores[genre] / len(
                            media_rec["genres"]
                        ) ** (1 / 2)
                    except (KeyError, ZeroDivisionError):
                        logger.debug(
                            f'No user data for {genre} in {media_rec["title"]["romaji"]}, skipping genre score'
                        )

                rec_genre_score *= model.rec_genre_score_weight

                total_rec_score = (
                    (node_score + rec_show_score + rec_genre_score)
                    * rec_total_weight
                    * rec_pop_factor
                    * favorite_weight
                    * progress_weight
                )
                """
                    id: Mapped[int] = mapped_column(primary_key=True)
                    media_id: Mapped[int] = mapped_column(Integer)
                    anilist_user_id: Mapped[int] = mapped_column(Integer)
                    is_manga: Mapped[bool] = mapped_column(Boolean)
                    title: Mapped[str] = mapped_column(String(400))
                    score: Mapped[float] = mapped_column(Float)
                    genres: Mapped[List[str]] = mapped_column(JSON)
                    cover_url: Mapped[str] = mapped_column(String(400))
                    mean_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
                """

                if media_rec["id"] not in recommendation_scores:
                    recommendation_scores[media_rec["id"]] = Recommendation(
                        media_id=media_rec["id"],
                        anilist_user_id=anilist_user_id,
                        is_manga=media_type.value,
                        title=media_rec["title"]["romaji"],
                        score=0,
                        genres=media_rec["genres"],
                        cover_url=media_rec["coverImage"]["large"],
                        mean_score=media_rec["meanScore"],
                    )

                recommendation_scores[media_rec["id"]].score += total_rec_score

        recommendation_scores_list = list(recommendation_scores.values())

        if not recommendation_scores_list:
            return recommendation_scores_list

        for rec in recommendation_scores_list:
            rec.score *= uniform(1 + model.score_variation, 1 - model.score_variation)

        recommendation_scores_list = [
            rec for rec in recommendation_scores_list if rec.score >= 0
        ]
        recommendation_scores_list.sort(reverse=True)

        # Normalize scores and apply filter for logical percentages
        max_score = recommendation_scores_list[0].score
        for rec in recommendation_scores_list:
            rec.score = (rec.score / max_score) ** model.global_scale_exp * 100

        return recommendation_scores_list

    async def check_or_update_recommendation_cache(
        self,
        user: User,
        media_type: MediaType,
        session: AsyncSession,
        force_update: bool = False,
    ) -> None:
        """
        Check if recommendations exist in cache and are up to date, and fetch new data if not cached.

        Args:
            user (User): User DB object
            media_type (MediaType): Defined by enum as anime or manga
            session (AsyncSession): sqlalchemy async db session
            force_update (bool): If true, will always fetch new data from anilist instead of using cache
        """
        anilist_id = user.anilist_id
        anilist_username = user.anilist_username
        user_id = user.user_id
        rec_timestamp = (
            user.rec_timestamp_anime
            if media_type == MediaType.Anime
            else user.rec_timestamp_manga
        )

        if anilist_id is None:
            return None

        # Use cached data unless cached data does not exist or is outdated

        use_cached = (
            AnimangaService.is_recommendation_cache_fresh(rec_timestamp)
            and not force_update
        )
        if use_cached:
            logger.info(
                f"Using cached {media_type} recommendations for anilist user {anilist_username}."
            )
            return None

        # Update last fetched timestamp
        if media_type == MediaType.Anime:
            user.rec_timestamp_anime = datetime.now()
        else:
            user.rec_timestamp_manga = datetime.now()
        await session.commit()

        logger.info(
            f"Updating cached {media_type} recommendations for anilist user {anilist_username}."
        )

        (
            list_data,
            user_stats,
            user_favorites,
        ) = await self.fetch_new_recommendation_api_data(
            anilist_id=anilist_id,
            media_type=media_type,
        )

        stmt = select(IgnoredRecommendation.media_id).where(
            IgnoredRecommendation.ignoring_user_id == user_id
        )
        result = await session.execute(stmt)
        ignored_recs = result.scalars().all()

        recommendations = self.calculate_rec_scores(
            list_data=list_data,
            user_stats=user_stats,
            user_favorites=user_favorites,
            ignored_media_ids=ignored_recs,
            anilist_user_id=anilist_id,
            media_type=media_type,
        )

        await AnimangaService.update_db_recommendations(
            recommendations, anilist_id, media_type, session
        )
        logger.info(
            f"Updated {len(recommendations)} {media_type.name} recs for anilist user {anilist_username}."
        )
        return None

    @staticmethod
    async def update_db_recommendations(
        new_recs: List[Recommendation],
        anilist_id: int,
        media_type: MediaType,
        session: AsyncSession,
    ) -> None:
        stmt = (
            delete(Recommendation)
            .where(Recommendation.anilist_user_id == anilist_id)
            .where(Recommendation.is_manga == media_type.value)
        )
        await session.execute(stmt)

        session.add_all(new_recs)

        try:
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.warning(
                f"Failed to write new recommendations to DB for anilist user {anilist_id}: {e}"
            )

    @staticmethod
    def is_recommendation_cache_fresh(rec_timestamp: datetime) -> bool:
        cache_expire_limit_days = 5
        if rec_timestamp is None:
            return False

        if (datetime.now() - rec_timestamp).days > cache_expire_limit_days:
            return False

        return True

    @staticmethod
    async def get_user_recommendation_count(
        anilist_user_id: int,
        media_type: MediaType,
        session: AsyncSession,
        genre: str = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(Recommendation)
            .where(Recommendation.anilist_user_id == anilist_user_id)
            .where(Recommendation.is_manga == media_type.value)
        )
        if genre is not None:
            stmt = stmt.where(Recommendation.genres.contains(genre))
        total = await session.scalar(stmt)
        return total

    @staticmethod
    async def get_user_ignored_count(
        user_id: int, media_type: MediaType, session: AsyncSession
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(IgnoredRecommendation)
            .where(IgnoredRecommendation.ignoring_user_id == user_id)
            .where(IgnoredRecommendation.is_manga == media_type.value)
        )
        total = await session.scalar(stmt)
        return total

    @staticmethod
    async def gen_rec_embed_page(
        anilist_user_id: int,
        anilist_username: str,
        media_type: MediaType,
        genre: str,
        page: int,
        session: AsyncSession,
        max_page: Optional[int] = None,
    ) -> tuple[Embed, int | None]:
        """
        Generate an embed with the recommended media.

        Args:
            anilist_user_id (int): User anilist ID
            anilist_username (str): User anilist username
            media_type (str): Specify to recommend manga/anime
            genre (str): Limit recommendations to specified genre
            page (int): Which recommendation in user's rec list to display
            session (AsyncSession): sqlalchemy async db session
            max_page (int): Max page of the view, if it has been found yet.
        Returns:
            Embed: Embed displaying recommended media and corresponding information
        """
        color = 0x7CD553 if media_type == MediaType.Manga else 0x3BAFEB

        stmt = (
            select(Recommendation)
            .where(Recommendation.anilist_user_id == anilist_user_id)
            .where(Recommendation.is_manga == media_type.value)
            .order_by(Recommendation.score.desc())
        )

        if genre:
            stmt = stmt.where(Recommendation.genres.contains(genre))

        capped_max_page = min(20, max_page) if max_page else 20
        page = page % capped_max_page if capped_max_page else 0

        stmt = stmt.offset(page).limit(1)

        result = await session.execute(stmt)
        rec: Optional[Recommendation] = result.scalars().one_or_none()

        embed = Embed(
            color=color,
            title=f"{anilist_username}'s Recommended {media_type.name.title()}",
        )
        if not rec:
            embed.description = "I couldn't find any recommendations!"
            return embed, None

        embed.description = f"""
    **{rec.title}** - https://anilist.co/{media_type}/{rec.media_id}/
    {rec.mean_score}% | *{', '.join(rec.genres)}*
    *Recommendation strength - {rec.score:.2f}%*
    """
        embed.set_thumbnail(url=rec.cover_url)
        return embed, rec.media_id

    @staticmethod
    async def ignore_media_rec(
        user_discord_id: int,
        anilist_user_id: int,
        media_id: int,
        media_type: MediaType,
        session: AsyncSession,
    ):
        stmt = (
            select(Recommendation)
            .where(Recommendation.anilist_user_id == anilist_user_id)
            .where(Recommendation.media_id == media_id)
            .where(Recommendation.is_manga == media_type.value)
        )

        result = await session.execute(stmt)
        rec: Optional[Recommendation] = result.scalars().one_or_none()
        if rec is None:
            return None

        # Create ignore object with attributes from the recommendation object
        ignoring_rec = IgnoredRecommendation(
            media_id=media_id,
            ignoring_user_id=user_discord_id,
            is_manga=media_type.value,
            title=rec.title,
            genres=rec.genres,
            cover_url=rec.cover_url,
            mean_score=rec.mean_score,
        )
        session.add(ignoring_rec)
        await session.delete(rec)

        try:
            await session.commit()
        except Exception as e:
            logger.warning(f"Failed to update user {user_discord_id} ignored recs: {e}")
        return None

    @staticmethod
    async def get_ignored_rec_embed_page(
        username: str,
        user_discord_id: int,
        media_type: MediaType,
        page: int,
        session: AsyncSession,
        max_page: Optional[int] = None,
    ) -> tuple[Embed, int | None]:
        """
        Generate an embed with the ignored rec media.

        Args:
            username (str): Discord display name
            user_discord_id (int): User discord ID to show ignore list for
            media_type (MediaType): View either manga or anime ignore list
            page (int): Which recommendation in user's rec list to display
            session (AsyncSession): sqlalchemy async db session
            max_page (int): Max page of the view, if it has been found yet.

        Returns:
            Embed: Embed displaying recommended media and corresponding information
        """
        stmt = (
            select(IgnoredRecommendation)
            .where(IgnoredRecommendation.ignoring_user_id == user_discord_id)
            .where(IgnoredRecommendation.is_manga == media_type.value)
        )

        capped_max_page = min(20, max_page) if max_page else 20
        page = page % capped_max_page if capped_max_page else 0

        stmt = stmt.offset(page).limit(1)

        result = await session.execute(stmt)
        ignored_rec: Optional[IgnoredRecommendation] = result.scalars().one_or_none()

        color = 0x7CD553 if media_type == MediaType.Manga else 0x3BAFEB

        embed = Embed(
            color=color, title=f"{username}'s Ignored {media_type.name.title()}"
        )
        if not ignored_rec:
            embed.description = "You have not ignored any recommendations!"
            return embed, None

        embed.description = f"""
        **{ignored_rec.title}** - https://anilist.co/{media_type}/{ignored_rec.media_id}/
        {ignored_rec.mean_score}% | *{', '.join(ignored_rec.genres)}*
        *To get updated recommendations after modifying your ignore list, specify force = true.*
        """
        embed.set_thumbnail(url=ignored_rec.cover_url)
        return embed, ignored_rec.media_id

    @staticmethod
    async def restore_media_rec(
        user_discord_id: int,
        ignored_media_id: int,
        media_type: MediaType,
        session: AsyncSession,
    ):
        stmt = (
            delete(IgnoredRecommendation)
            .where(IgnoredRecommendation.ignoring_user_id == user_discord_id)
            .where(IgnoredRecommendation.media_id == ignored_media_id)
            .where(IgnoredRecommendation.is_manga == media_type.value)
        )
        try:
            await session.execute(stmt)
            await session.commit()
        except Exception as e:
            logger.warning(
                f"Failed to remove ignored rec for user {user_discord_id}, media ID {ignored_media_id}: {e}"
            )
