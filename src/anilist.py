import httpx


def anime_id_from_url(url: str) -> int | None:
    url = url.lower().split("/")
    url = tuple(filter(None, url))

    if "anime" not in url:
        return None
    if url[-1].isdigit():
        return int(url[-1])
    elif url[-2].isdigit():
        return int(url[-2])

    return None


def username_from_url(url: str) -> str | None:
    url = url.split("/")
    url = tuple(filter(None, url))
    if not url:
        return None

    return url[-1]


def query_media(*, media_id: int):
    query = """
    query Media($mediaId: Int) {
      Media(id: $mediaId) {
        episodes
        genres
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
    variables = {
        "mediaId": media_id
    }
    response = httpx.post(
        url="https://graphql.anilist.co",
        json={"query": query, "variables": variables}
    )
    if response.status_code != 200:
        return None

    return response.json()["data"]["Media"]


def query_user_id(username: str) -> int | None:
    query = """
    query
    User($name: String) {
        User(name: $name) {
        id
      }
    }
    """
    variables = {
        "name": username
    }
    response = httpx.post(
        url="https://graphql.anilist.co",
        json={"query": query, "variables": variables}
    )
    if response.status_code != 200:
        return None

    return response.json()["data"]["User"]["id"]


# Query a user's anime list. Data is in form of [{"mediaId": 160181, "status": "CURRENT"}, {...]
def query_user_animelist(user_id: int) -> list | None:
    query = """
    query MediaListCollection($type: MediaType, $userId: Int, $statusNotIn: [MediaListStatus]) {
    MediaListCollection(type: $type, userId: $userId, status_not_in: $statusNotIn) {
      lists {
        entries {
          mediaId
          status
          }
        }
      }
    }
    """
    variables = {
        "userId": user_id,
        "type": "ANIME",
        "statusNotIn": "PLANNING"
    }
    response = httpx.post(
        url="https://graphql.anilist.co",
        json={"query": query, "variables": variables}
    )
    if response.status_code != 200:
        return None

    full_user_list: list = []
    for anime_list in response.json()["data"]["MediaListCollection"]["lists"]:
        anime_list = anime_list["entries"]
        full_user_list += anime_list

    return full_user_list
