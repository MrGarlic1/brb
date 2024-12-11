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
def query_user_animelist(anilist_user_id: int) -> list | None:
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
    response = httpx.post(
        url="https://graphql.anilist.co",
        json={"query": query, "variables": variables}
    )
    if response.status_code != 200:
        return None

    user_genres = response.json()["data"]["User"]["statistics"]["anime"]["genres"]
    user_genres = sorted(user_genres, key=lambda genre: genre["minutesWatched"])

    try:
        if user_genres[0]["genre"] == "Hentai":  # Exclude hentai per game rules
            least_watched_genre = user_genres[1]["genre"]
        else:
            least_watched_genre = user_genres[0]["genre"]
    except IndexError:  # User has not watched more than one genre
        least_watched_genre = ""

    return full_user_list


def find_anilist_changes(start_anilist: list[dict], end_anilist: list[dict]) -> list[dict]:

    anilist_changes = []
    for end_anime in end_anilist:
        start_anime = next(
            (start_anime for start_anime in start_anilist if start_anime["mediaId"] == end_anime["mediaId"]), None
        )
        if start_anime == end_anime:  # Skip if the show is the same at the beginning and end of game
            continue

        if not start_anime:  # Show was not on player's anilist when the game started
            anilist_changes.append(end_anime)
        else:
            episode_changes = end_anime["progress"] - start_anime["progress"]
            anilist_changes.append(
                {"mediaId": end_anime["mediaId"], "status": end_anime["status"], "progress": episode_changes}
            )

    return anilist_changes


anilist = query_user_animelist(anilist_user_id=5862798)


"""
anilist = query_user_animelist(anilist_user_id=5862798)
print(anilist)
test_case = {'mediaId': 160181, 'status': 'COMPLETED', 'progress': 11}
for entry in anilist:
    if entry["mediaId"] == 160181:
        print(set(entry.values()) - set(test_case.values()))
    print(set(entry.values()) - set(entry.values()))
"""