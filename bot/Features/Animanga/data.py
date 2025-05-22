import httpx

import Core.botdata as bd
from datetime import datetime
from random import choice
from Core.anilist import query_media_list_recs
from json import dump


def fetch_recommendations(anilist_id: int, manga: bool = False) -> None:

    list_data = query_media_list_recs(user_id=anilist_id, manga=manga)
    if not list_data:
        raise httpx.RequestError

    # Obtain average user score for user score weighing

    total_user_score = 0
    no_score_entries = 0
    max_score = 0
    already_seen_show_ids = []
    for entry in list_data:
        already_seen_show_ids.append(entry["media"]["id"])
        if entry["score"] == 0:
            no_score_entries += 1
            continue
        if entry["score"] > max_score:
            max_score = entry["score"]
        total_user_score += entry["score"]

    # Normalize by max score for alternate scoring schemes
    user_mean_score = total_user_score/max_score/(len(list_data) - no_score_entries)
    recommendation_scores = {}
    for entry in list_data:
        if not entry["media"]["recommendations"]["nodes"]:
            continue
        max_recs = max(5, len(entry["media"]["recommendations"]["nodes"]))
        max_rec_rating = entry["media"]["recommendations"]["nodes"][0]["rating"]
        if max_rec_rating == 0:
            continue
        for show_rec in entry["media"]["recommendations"]["nodes"][0:max_recs]:
            # Filter out bad data from anilist
            if show_rec["mediaRecommendation"] is None:
                continue
            if show_rec["mediaRecommendation"]["id"] in already_seen_show_ids:
                continue
            # Scoring
            user_score_weight = 0 if entry["score"] == 0 else 1

            if show_rec["mediaRecommendation"]["id"] not in recommendation_scores:
                recommendation_scores[show_rec["mediaRecommendation"]["id"]] = (
                    user_score_weight*(entry["score"]/max_score - user_mean_score) +
                    0.8*(show_rec["mediaRecommendation"]["meanScore"] - 65)/100
                )*show_rec["rating"]/max_rec_rating
            else:
                recommendation_scores[show_rec["mediaRecommendation"]["id"]] += (
                    user_score_weight*(entry["score"]/max_score - user_mean_score) +
                    0.8*(show_rec["mediaRecommendation"]["meanScore"] - 65)/100
                )*show_rec["rating"]/max_rec_rating

    # Sort recommendations by score then take the top 20
    recommendation_scores = dict(sorted(recommendation_scores.items(), key=lambda item: item[1], reverse=True))
    recommendation_scores = {
        k: v for i, (k, v) in enumerate(recommendation_scores.items()) if i < 20
    }

    # Normalize scores and apply filter for logical percentages
    max_recommendation_score = max(recommendation_scores.values())
    recommendation_scores = {
        k: (v/max_recommendation_score)**0.35*100 for k, v in recommendation_scores.items()
    }

    known_recs = bd.known_manga_recs if manga else bd.known_anime_recs
    filename = "manga_rec_cache.json" if manga else "anime_rec_cache.json"
    known_recs[anilist_id] = {
        "date": datetime.now().strftime(bd.date_format), "recs": recommendation_scores
    }
    with open(f"{bd.parent}/Data/{filename}", "w") as f:
        dump(known_recs, f, separators=(",", ":"))

    return None


def get_recommendation(anilist_id: int, listall: int, force_update: bool = False, manga: bool = False) -> str:
    known_recs = bd.known_manga_recs if manga else bd.known_anime_recs

    if anilist_id not in known_recs or force_update:
        fetch_recommendations(anilist_id, manga=manga)

    time_delta = ((datetime.now() - datetime.strptime(known_recs[anilist_id]["date"], bd.date_format))
                  .total_seconds())
    if time_delta > 345600:
        fetch_recommendations(anilist_id)

    recs = known_recs[anilist_id]["recs"]

    link_type = "manga" if manga else "anime"

    if listall:
        final_rec = ""
        for rec_id, score in recs.items():
            final_rec += f"Recommendation Score: {score:.1f}% - https://anilist.co/{link_type}/{rec_id}/\n"
    else:
        rec_id = choice(tuple(recs.keys()))
        final_rec = f"https://anilist.co/{link_type}/{rec_id}/\nRecommendation Score: {recs[rec_id]:.1f}%"

    return final_rec
