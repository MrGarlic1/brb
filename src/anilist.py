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
        genres
        season
        source
        title {
          english
        }
        episodes
        startDate {
          year
        }
      }
    }
    """
    variables = {
    'mediaId': media_id
    }
    r = httpx.post(
        url='https://graphql.anilist.co',
        json={'query': query, 'variables': variables}
    )
    if r.status_code != 200:
        return None
    else:
        return r.json()["data"]["Media"]

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
    'name': username
    }
    r = httpx.post(
        url='https://graphql.anilist.co',
        json={'query': query, 'variables': variables}
    )
    if r.status_code != 200:
        return None
    else:
        return r.json()["data"]["User"]["id"]


def query_user_animelist(user_id: int):
    print(user_id)
    pass