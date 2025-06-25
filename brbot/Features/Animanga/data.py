import logging
from asyncio import gather, sleep, Semaphore
from datetime import datetime
from random import uniform
from typing import Optional, Dict, List, Tuple
import brbot.Core.botdata as bd
from httpx import AsyncClient, ReadTimeout, RequestError, post
from brbot.Shared.buttons import NextPgButton, PrevPgButton
from discord.ui import View
from discord import Interaction, Embed

logger = logging.getLogger(__name__)


class RecView(View):
    """
    Discord UI View for handling animanga recommendation interactions.

    Attributes:
        anilist_id (str): Anilist id to recommend for
        username (str): Discord username
        media_type (str): Specify to recommend manga/anime
        genre (str): Limit recommendations to specified genre
        page (int): Which recommendation in user's rec list to display
    """

    def __init__(self, username: str, anilist_id: int, media_type: str, genre: str):
        super().__init__(timeout=60)
        self.add_item(PrevPgButton())
        self.add_item(NextPgButton())
        self.anilist_id = anilist_id
        self.username = username
        self.media_type = media_type
        self.genre = genre
        self.page = 0

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.data["custom_id"] == "prev_page":
            self.page -= 1
        elif interaction.data["custom_id"] == "next_page":
            self.page += 1

        embed = get_rec_embed(
            username=self.username,
            media_type=self.media_type,
            genre=self.genre,
            page=self.page,
            anilist_id=self.anilist_id,
        )

        await interaction.response.edit_message(embed=embed, view=self)
        return True


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
        return isinstance(other, MediaRec) and other.media_id == self.media_id


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


async def query_user_statistics(anilist_id: int, media_type: str) -> Optional[Dict]:
    """
    Queries anilist for user statistics used for weighting/scoring of animanga recommendations

    Args:
        anilist_id (int): Anilist user ID to query
        media_type (str): Specifies anime or manga statistics

    Returns:
        dict: Anilist media type user statistics data
    """
    query = f"""
    query User($userId: Int) {{
      User(id: $userId) {{
        statistics {{
          {media_type} {{
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
          {media_type} {{
            nodes {{
              id
            }}
          }}
        }}
      }}
    }}
    """
    variables = {"userId": anilist_id}
    logger.info(f"Querying user statistics for {anilist_id} ({media_type})")

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
        if user_data["statistics"][media_type]["count"]:
            favorites = [
                fav["id"] for fav in user_data["favourites"][media_type]["nodes"]
            ]
            user_data["favourites"][media_type] = favorites
            return user_data

    logger.error(f"Failed to fetch user statistics for {anilist_id}")
    return None


async def query_media_recs(
    anilist_id: int, media_type: str, watched_count: int
) -> Optional[List[Dict]]:
    """
    Queries anilist for user list data used for weighting/scoring of animanga recommendations

    Args:
        anilist_id (int): Anilist user ID to query
        media_type (str): Specifies anime or manga statistics
        watched_count (int): Completed entries on user's list

    Returns:
        Optional[list[dict]]: Anilist media list collection data
    """
    query = """
    query MediaListCollection($userId: Int, $type: MediaType, $statusNotIn: [MediaListStatus], $sort: [RecommendationSort], $perPage: Int, $perChunk: Int, $chunk: Int) {
      MediaListCollection(userId: $userId, type: $type, status_not_in: $statusNotIn, perChunk: $perChunk, chunk: $chunk) {
        lists {
          entries {
            score
            status
            media {
              id
              popularity
              recommendations(sort: $sort, perPage: $perPage) {
                nodes {
                  rating
                  mediaRecommendation {
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
                "type": media_type.upper(),
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

        logger.warning(f"Failed to get list data chunk {chunk} after {max_attempts}")
        return None

    tasks: list = []

    logger.info(f"Querying user list data for {anilist_id} ({media_type})")
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


async def fetch_recommendations(
    anilist_id: int, media_type: str
) -> Tuple[List, Dict, List]:
    """
    Wrapper function for fetching anilist data for animanga recs

    Args:
        anilist_id (int): Anilist user ID to query
        media_type (str): Specifies anime or manga statistics

    Returns:
        tuple: Tuple containing user list data, user statistics, and favorites

    Raises:
        RequestError if either user statistics or list data is empty
    """
    user_data = await query_user_statistics(
        anilist_id=anilist_id, media_type=media_type
    )
    if not user_data:
        raise RequestError("Error obtaining data from anilist.")
    user_stats = user_data["statistics"][media_type]
    user_favorites = user_data["favourites"][media_type]

    list_data = await query_media_recs(
        anilist_id=anilist_id,
        media_type=media_type,
        watched_count=user_stats["count"],
    )
    if not list_data:
        raise RequestError("Error obtaining data from anilist.")

    return list_data, user_stats, user_favorites


def calculate_rec_scores(
    list_data: List[Dict], user_stats: Dict, user_favorites: List[int]
) -> List[MediaRec]:
    """
    Scoring algorithm for animanga recs

    Args:
        list_data (list[dict]): Anilist media list collection data
        user_stats (dict): Anilist user statistics
        user_favorites (list[int]): List of user favorited media IDs

    Returns:
        list[MediaRec]: List of user's recommendations
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

    user_genre_scores = {}
    for genre in user_stats["genres"]:
        genre_name = genre["genre"]
        if not genre["meanScore"]:
            user_genre_scores[genre_name] = 0
        else:
            user_genre_scores[genre_name] = (
                genre["meanScore"] - user_stats["meanScore"]
            ) / 100 + (genre["count"] - 0.5 * len(seen_show_ids)) / len(
                seen_show_ids
            ) * model.genre_count_weight

    recommendation_scores: dict[int:MediaRec] = {}
    for list_entry in list_data:
        if not list_entry["media"]["recommendations"]["nodes"]:
            continue
        if list_entry["status"] == "DROPPED":
            continue

        # Weight each show's recommendation by strength of recommendation on the site
        max_show_recs = max(8, len(list_entry["media"]["recommendations"]["nodes"]))
        max_rec_rating = list_entry["media"]["recommendations"]["nodes"][0]["rating"]
        if max_rec_rating == 0:
            continue

        favorite_weight = (
            model.favorite_weight if list_entry["media"]["id"] in user_favorites else 1
        )

        for show_rec in list_entry["media"]["recommendations"]["nodes"][
            0:max_show_recs
        ]:
            rec_total_weight = show_rec["rating"] / max_rec_rating

            media_rec = show_rec["mediaRecommendation"]
            # Filter out bad data from anilist
            if media_rec is None:
                continue
            if media_rec["id"] in seen_show_ids:
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
            )
            if media_rec["id"] not in recommendation_scores:
                recommendation_scores[media_rec["id"]] = MediaRec(
                    media_id=media_rec["id"],
                    title=media_rec["title"]["romaji"],
                    genres=media_rec["genres"],
                    cover_url=media_rec["coverImage"]["large"],
                    mean_score=media_rec["meanScore"],
                )
            recommendation_scores[media_rec["id"]].score += total_rec_score

    recommendation_scores = list(recommendation_scores.values())

    for rec in recommendation_scores:
        rec.score *= uniform(1 + model.score_variation, 1 - model.score_variation)

    recommendation_scores = [rec for rec in recommendation_scores if rec.score >= 0]
    recommendation_scores.sort(reverse=True)

    # Normalize scores and apply filter for logical percentages
    max_score = recommendation_scores[0].score
    for rec in recommendation_scores:
        rec.score = (rec.score / max_score) ** model.global_scale_exp * 100

    return recommendation_scores


async def check_recommendation(
    anilist_id: int,
    media_type: str,
    force_update: bool = False,
) -> None:
    """
    Check if recommendations exist in cache and are up to date, and fetch new data if not cached.

    Args:
        anilist_id (int): Anilist user ID to query
        media_type (str): Anilist user statistics
        force_update (bool): If true, will always fetch new data from anilist instead of using cache
    """
    known_recs = bd.known_manga_recs if media_type == "manga" else bd.known_anime_recs

    # Use cached data unless cached data does not exist or is outdated
    logger.info(f"Checking recommendation cache for {anilist_id} ({media_type})")

    try:
        time_delta = (datetime.now() - known_recs[anilist_id]["date"]).total_seconds()
    except KeyError:
        time_delta = 0
    if anilist_id not in known_recs or force_update or time_delta > 345600:
        logger.debug(f"Cache age for {anilist_id}: {time_delta:.2f} seconds")
        list_data, user_stats, user_favorites = await fetch_recommendations(
            anilist_id=anilist_id,
            media_type=media_type,
        )
        recommendation_scores = calculate_rec_scores(
            list_data=list_data,
            user_stats=user_stats,
            user_favorites=user_favorites,
        )
        known_recs[anilist_id] = {
            "date": datetime.now(),
            "recs": recommendation_scores,
        }
        logger.info(f"Updated recommendations cache for {anilist_id} ({media_type})")
    else:
        logger.info(f"Using cached recommendation data for {anilist_id} ({media_type})")

    return None


def get_rec_embed(
    username: str, anilist_id: int, media_type: str, genre: str, page: int
) -> Embed:
    """
    Generate an embed with the recommended media.

    Args:
        username (str): Discord display name
        anilist_id (str): Anilist username to recommend for
        media_type (str): Specify to recommend manga/anime
        genre (str): Limit recommendations to specified genre
        page (int): Which recommendation in user's rec list to display

    Returns:
        Embed: Embed displaying recommended media and corresponding information
    """
    if media_type == "manga":
        color = 0x7CD553
        recs = bd.known_manga_recs[anilist_id]["recs"]
    else:
        color = 0x3BAFEB
        recs = bd.known_anime_recs[anilist_id]["recs"]

    if genre:
        recs = [rec for rec in recs if genre in rec.genres]

    embed = Embed(color=color, title=f"Recommendation for {username}")
    if not recs:
        embed.description = "I couldn't find any recommendations!"
        return embed

    max_page = min(20, len(recs))
    rec = recs[page % max_page]

    embed.description = f"""
**{rec.title}** - https://anilist.co/{media_type}/{rec.media_id}/
{rec.mean_score}% | *{', '.join(rec.genres)}*
*Recommendation strength - {rec.score:.2f}%*
"""
    embed.set_thumbnail(url=rec.cover_url)
    return embed
