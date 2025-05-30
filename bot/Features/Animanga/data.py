from httpx import RequestError

import Core.botdata as bd
from datetime import datetime
from random import choice, uniform
from Core.anilist import query_media_list_recs
from json import dump


async def fetch_recommendations(anilist_id: int = None, manga: bool = False, requested_genre: str = "") -> None:

    user_stats, list_data = await query_media_list_recs(user_id=anilist_id, manga=manga)
    if not list_data or not user_stats:
        raise RequestError("An error occurred completing the request.")

    # Obtain max user score, collect watched show info
    max_score = 0
    max_popularity = 0
    seen_show_ids = []
    for entry in list_data:
        seen_show_ids.append(entry["media"]["id"])
        if entry["score"] > max_score:
            max_score = entry["score"]
        if entry["media"]["popularity"] > max_popularity:
            max_popularity = entry["media"]["popularity"]

    # Get user genre scores
    user_genre_scores = {}
    if not requested_genre:
        for genre in user_stats["genres"]:
            genre_name = genre["genre"]
            if not genre["meanScore"]:
                user_genre_scores[genre_name] = 0
            user_genre_scores[genre_name] = (
                (genre["meanScore"] - user_stats["meanScore"])/100
            )

    recommendation_scores = {}

    for entry in list_data:
        if not entry["media"]["recommendations"]["nodes"]:
            continue

        # Weight each show's recommendation by strength of recommendation on the site
        max_recs = max(8, len(entry["media"]["recommendations"]["nodes"]))
        max_rec_rating = entry["media"]["recommendations"]["nodes"][0]["rating"]
        if max_rec_rating == 0:
            continue

        for show_rec in entry["media"]["recommendations"]["nodes"][0:max_recs]:
            # Filter out bad data from anilist
            if show_rec["mediaRecommendation"] is None:
                continue
            if show_rec["mediaRecommendation"]["id"] in seen_show_ids:
                continue
            if not show_rec["mediaRecommendation"]["meanScore"]:
                show_rec["mediaRecommendation"]["meanScore"] = 65

            if requested_genre and not any(
                    genre == requested_genre for genre in show_rec["mediaRecommendation"]["genres"]
            ):
                continue

            try:
                if any(
                    related_show[0]["relationType"] == "PREQUEL" and related_show[1]["id"] not in seen_show_ids
                    for related_show in zip(
                        show_rec["mediaRecommendation"]["relations"]["edges"],
                        show_rec["mediaRecommendation"]["relations"]["nodes"]
                    )
                ):
                    continue
            except KeyError:
                pass

            # Scoring
            node_score_weight = 0 if entry["score"] == 0 else 1
            node_score = node_score_weight*(entry["score"]/max_score - user_stats["meanScore"]/100)
            rec_show_score_weight = 1
            rec_show_score = rec_show_score_weight*(show_rec["mediaRecommendation"]["meanScore"] - 65)/100
            rec_pop_factor = (1 - show_rec["mediaRecommendation"]["popularity"]/max_popularity)
            rec_pop_factor = rec_pop_factor ** 1.5 if rec_pop_factor > 0 else 0.1
            rec_genre_score_weight = 0.75
            rec_genre_score = 0
            if not requested_genre:
                for genre in show_rec["mediaRecommendation"]["genres"]:
                    try:
                        rec_genre_score += user_genre_scores[genre]
                    except KeyError:
                        continue
                rec_genre_score *= rec_genre_score_weight

            rec_total_weight = show_rec["rating"]/max_rec_rating

            if show_rec["mediaRecommendation"]["id"] not in recommendation_scores:
                recommendation_scores[show_rec["mediaRecommendation"]["id"]] = (
                    (node_score + rec_show_score + rec_genre_score)*rec_total_weight*rec_pop_factor
                )
            else:
                recommendation_scores[show_rec["mediaRecommendation"]["id"]] += (
                    (node_score + rec_show_score + rec_genre_score)*rec_total_weight*rec_pop_factor
                )

    # Sort recommendations by score then take the top 20, add random variation of +-20%
    recommendation_scores = {
        k: v*uniform(0.8, 1.2) for k, v in recommendation_scores.items()
    }
    recommendation_scores = dict(sorted(recommendation_scores.items(), key=lambda item: item[1], reverse=True))
    recommendation_scores = {
        k: v for i, (k, v) in enumerate(recommendation_scores.items()) if i < 20 and v >= 0
    }

    # Normalize scores and apply filter for logical percentages
    max_recommendation_score = max(recommendation_scores.values())
    recommendation_scores = {
        k: (v/max_recommendation_score)**0.35*100 for k, v in recommendation_scores.items()
    }

    known_recs = bd.known_manga_recs if manga else bd.known_anime_recs
    filename = "manga_rec_cache.json" if manga else "anime_rec_cache.json"
    known_recs[f"{anilist_id}{requested_genre}"] = {
        "date": datetime.now().strftime(bd.date_format), "recs": recommendation_scores
    }
    with open(f"{bd.parent}/Data/{filename}", "w") as f:
        dump(known_recs, f, separators=(",", ":"))

    return None


async def get_recommendation(
        anilist_id: int, listall: int, requested_genre: str = "", force_update: bool = False, manga: bool = False
) -> str:
    known_recs = bd.known_manga_recs if manga else bd.known_anime_recs
    requested_recs = f"{anilist_id}{requested_genre}"
    if requested_recs not in known_recs or force_update:
        try:
            await fetch_recommendations(anilist_id, manga=manga, requested_genre=requested_genre)
        except RequestError:
            return "Error fetching recommendations. Please try again later."
    time_delta = ((datetime.now() - datetime.strptime(known_recs[requested_recs]["date"], bd.date_format))
                  .total_seconds())
    if time_delta > 345600:
        await fetch_recommendations(anilist_id=anilist_id, manga=manga, requested_genre=requested_genre)

    recs = known_recs[requested_recs]["recs"]

    link_type = "manga" if manga else "anime"

    if listall:
        final_rec = ""
        for rec_id, score in recs.items():
            final_rec += f"Recommendation Score: {score:.1f}% - <https://anilist.co/{link_type}/{rec_id}/>\n"
    else:
        rec_id = choice(tuple(recs.keys()))
        final_rec = f"https://anilist.co/{link_type}/{rec_id}/\nRecommendation Score: {recs[rec_id]:.1f}%"

    return final_rec
