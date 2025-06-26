import httpx
import logging
from asyncio import sleep

logger = logging.getLogger(__name__)


def anilist_id_from_url(url: str, is_character: bool = False) -> int | None:
    url = url.lower().split("/")
    url = tuple(filter(None, url))
    if is_character and "character" not in url:
        return None
    if not is_character and "anime" not in url:
        return None
    if url[-1].isdigit():
        return int(url[-1])
    elif url[-2].isdigit():
        return int(url[-2])
    elif url[-3].isdigit():
        return int(url[-3])

    return None


async def query_media(*, media_id: int):
    query = """
    query Media($mediaId: Int) {
      Media(id: $mediaId) {
        episodes
        genres
        format
        meanScore
        popularity
        season
        source
        startDate {
          year
        }
        tags {
          name
          rank
        }
        title {
          english
        }
      }
    }
    """
    variables = {"mediaId": media_id}

    max_attempts = 2
    for attempt in range(max_attempts):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url="https://graphql.anilist.co",
                    json={"query": query, "variables": variables},
                )
            if response.status_code == 200:
                return response.json()["data"]["Media"]
            else:
                logger.warning(
                    f"Error {response.status_code} while fetching show data for show {media_id} ({attempt + 1}/{max_attempts} attempts)"
                )
                if response.status_code == 404:
                    break
        except (httpx.ReadTimeout, httpx.RequestError) as e:
            logger.warning(
                f"Error {e} while fetching show data for show {media_id} ({attempt + 1}/{max_attempts} attempts)"
            )
        await sleep(1)
    logger.error(
        f"Failed to retrieve show data for show {media_id} after {max_attempts} attempts"
    )
    return None


async def query_user_id(username: str) -> int | None:
    query = """
    query
    User($name: String) {
        User(name: $name) {
        id
      }
    }
    """
    variables = {"name": username}

    max_attempts = 2

    for attempt in range(max_attempts):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url="https://graphql.anilist.co",
                    json={"query": query, "variables": variables},
                )
            if response.status_code == 200:
                return response.json()["data"]["User"]["id"]
            else:
                logger.warning(
                    f"Error {response.status_code} while fetching user id for anilist user {username} ({attempt + 1}/{max_attempts} attempts)"
                )
                if response.status_code == 404:
                    break
        except (httpx.ReadTimeout, httpx.RequestError) as e:
            logger.warning(
                f"Error {e} while fetching user id for anilist user {username} ({attempt + 1}/{max_attempts} attempts)"
            )
        await sleep(1)

    logger.error(
        f"Failed to retrieve user id for anilist user {username} after {max_attempts} attempts"
    )
    return None


# Query a user's anime list. Data is in form of [{"mediaId": 160181, "status": "CURRENT"}, {...]
async def query_user_animelist(anilist_user_id: int) -> list | None:
    query = """
    query MediaListCollection($type: MediaType, $userId: Int, $statusNotIn: [MediaListStatus]) {
    MediaListCollection(type: $type, userId: $userId, status_not_in: $statusNotIn) {
      lists {
        entries {
          mediaId
          status
          progress
          }
        }
      }
    }
    """
    variables = {
        "userId": anilist_user_id,
        "type": "ANIME",
        "statusNotIn": ["PLANNING"],
    }
    max_attempts = 2
    for attempt in range(max_attempts):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url="https://graphql.anilist.co",
                    json={"query": query, "variables": variables},
                )
            if response.status_code == 200:
                full_user_list: list = []
                for anime_list in response.json()["data"]["MediaListCollection"][
                    "lists"
                ]:
                    full_user_list += anime_list["entries"]
                return full_user_list

            else:
                logger.warning(
                    f"Error {response.status_code} while fetching list data for anilist user {anilist_user_id} ({attempt + 1}/{max_attempts} attempts)"
                )
                if response.status_code == 404:
                    break
        except (httpx.ReadTimeout, httpx.RequestError) as e:
            logger.warning(
                f"Error {e} while fetching list data for anilist user {anilist_user_id} ({attempt + 1}/{max_attempts} attempts)"
            )
        await sleep(1)

    logger.error(
        f"Failed to retrieve list data for anilist user {anilist_user_id} after {max_attempts} attempts"
    )
    return None


async def query_user_genres(anilist_user_id: int) -> str | None:
    query = """
    query Statistics($userId: Int) {
      User(id: $userId) {
        statistics {
          anime {
            genres {
              genre
              minutesWatched
            }
          }
        }
      }
    }
    """
    variables = {
        "userId": anilist_user_id,
    }
    max_attempts = 2
    for attempt in range(max_attempts):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url="https://graphql.anilist.co",
                    json={"query": query, "variables": variables},
                )
            if response.status_code == 200:
                user_genres = response.json()["data"]["User"]["statistics"]["anime"][
                    "genres"
                ]
                user_genres = sorted(
                    user_genres, key=lambda genre: genre["minutesWatched"]
                )
                try:
                    if (
                        user_genres[0]["genre"] == "Hentai"
                    ):  # Exclude hentai per game rules
                        least_watched_genre = user_genres[1]["genre"]
                    else:
                        least_watched_genre = user_genres[0]["genre"]
                except IndexError:  # User has not watched more than one genre
                    least_watched_genre = ""
                logger.debug(
                    f"Anilist user {anilist_user_id} least watched genre is {least_watched_genre}"
                )
                return least_watched_genre

            else:
                logger.warning(
                    f"Error {response.status_code} while fetching genre data for anilist user {anilist_user_id}s ({attempt + 1}/{max_attempts} attempts)"
                )
                if response.status_code == 404:
                    break
        except (httpx.ReadTimeout, httpx.RequestError) as e:
            logger.warning(
                f"Error {e} while fetching genre data for anilist user {anilist_user_id} ({attempt + 1}/{max_attempts} attempts)"
            )
        await sleep(1)

    logger.error(
        f"Failed to retrieve genre data for anilist user {anilist_user_id} after {max_attempts} attempts"
    )
    return None


async def query_character(*, character_id: int):
    query = """
    query Character($characterId: Int) {
      Character(id: $characterId) {
        image {
          medium
        }
        name {
          full
        }
        siteUrl
      }
    }
    """
    variables = {"characterId": character_id}

    max_attempts = 2

    for attempt in range(max_attempts):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url="https://graphql.anilist.co",
                    json={"query": query, "variables": variables},
                )
            if response.status_code == 200:
                return response.json()["data"]["Character"]

            else:
                logger.warning(
                    f"Error {response.status_code} while fetching anilist character data for {character_id} ({attempt + 1}/{max_attempts} attempts)"
                )
                if response.status_code == 404:
                    break
        except (httpx.ReadTimeout, httpx.RequestError) as e:
            logger.warning(
                f"Error {e} while fetching character data for anillist character {character_id} ({attempt + 1}/{max_attempts} attempts)"
            )
        await sleep(1)

    logger.error(
        f"Failed to retrieve list data for anilist character {character_id} after {max_attempts} attempts"
    )
    return None
