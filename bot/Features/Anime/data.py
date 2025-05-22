import interactions
from emoji import emojize, demojize
import Core.botdata as bd
from datetime import datetime
from random import choice
from Core.anilist import query_media_list_recs
from json import dump


def fetch_recommendations(anilist_id: int, force_update: bool = False) -> str:

    # Use cached data if it is new enough
    if anilist_id in bd.known_recommendations and not force_update:
        time_delta = ((datetime.now() - datetime.strptime(bd.known_recommendations[anilist_id]["date"], bd.date_format))
                      .total_seconds())
        if time_delta < 345600:
            recs = bd.known_recommendations[anilist_id]["recs"]
            final_rec = choice(tuple(recs.keys()))
            return f"https://anilist.co/anime/{final_rec}/\nRecommendation Score: {recs[final_rec]:.3f}"

    list_data = query_media_list_recs(user_id=anilist_id)
    if not list_data:
        return "An error occurred while getting recommendations. Please try again later."

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
                    user_score_weight*(entry["score"] - user_mean_score) +
                    0.8*(show_rec["mediaRecommendation"]["meanScore"] - 70)/100
                )*show_rec["rating"]/max_rec_rating
            else:
                recommendation_scores[show_rec["mediaRecommendation"]["id"]] += (
                    user_score_weight*(entry["score"] - user_mean_score) +
                    0.8*(show_rec["mediaRecommendation"]["meanScore"] - 70)/100
                )*show_rec["rating"]/max_rec_rating

    # Filter recommendations by max score, then sort by score and take the top 15
    recommendation_scores = dict((showid, score) for showid, score in recommendation_scores.items() if score > 40)
    recommendation_scores = dict(sorted(recommendation_scores.items(), key=lambda item: item[1], reverse=True))
    recommendation_scores = {k: v for i, (k, v) in enumerate(recommendation_scores.items()) if i < 15}

    bd.known_recommendations[anilist_id] = {
        "date": datetime.now().strftime(bd.date_format), "recs": recommendation_scores
    }
    with open(f"{bd.parent}/Data/recommendation_cache.json", "w") as f:
        dump(bd.known_recommendations, f, separators=(",", ":"))

    recs = bd.known_recommendations[anilist_id]["recs"]
    final_rec = choice(tuple(recs.keys()))
    return f"https://anilist.co/anime/{final_rec}/\nRecommendation Score: {recs[final_rec]:.3f}"
