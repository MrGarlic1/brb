import logging
from asyncio import sleep
from datetime import datetime, timezone
from random import uniform

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from typing import Optional, Dict, List, Sequence

from sqlalchemy.orm import selectinload
from discord import Guild as DiscordGuild
from brbot.Features.Animanga.data import MediaType, DailyStatSnapshot
from brbot.db.models import AnimangaDailyStats, AnimangaListEntry, Member, User
from httpx import AsyncClient, ReadTimeout
from discord import Embed

logger = logging.getLogger(__name__)


class AnimangaStatService:
    def __init__(self):
        pass

    @staticmethod
    async def create_leaderboard_embed(
        guild: DiscordGuild, date: datetime, daily_stats: list[DailyStatSnapshot]
    ) -> Embed:
        daily_stats = sorted(daily_stats, key=lambda d: d.minutes_watched, reverse=True)
        placement_emojis = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]
        embed = Embed(title=f"Weeb Leaderboard {date.strftime('%Y/%m/%d')}")
        embed.set_author(name=guild.name, icon_url=guild.icon.url)
        for i in range(min(len(daily_stats), len(placement_emojis))):
            pos = daily_stats[i]
            if i == 0:
                member = await guild.fetch_member(pos.user_discord_id)
                embed.set_thumbnail(url=member.avatar.url)

            user_str = f"**{placement_emojis[i]}: <@{pos.user_discord_id}> ({pos.minutes_watched} minutes**)\n"
            manga_str = (
                f"**Manga💬 :** {pos.manga_chapters} chapters\n"
                if pos.manga_chapters != 0
                else ""
            )
            ln_str = (
                f"**Light Novel📖 :** {pos.ln_chapters} chapters\n"
                if pos.ln_chapters != 0
                else ""
            )
            tv_str = (
                f"**Anime📺 :** {pos.episodes} episodes\n" if pos.episodes != 0 else ""
            )
            movie_str = f"**Movie📽️ :** {pos.movies} movies" if pos.movies != 0 else ""
            embed.add_field(
                name="\u200b",
                value=f"{user_str}{manga_str}{ln_str}{tv_str}{movie_str}",
            )
        embed.set_footer(
            text="Want to be on the daily leaderboard? /animanga track_daily"
        )

        return embed

    @staticmethod
    async def get_user_list_entries(
        user_id: int, anilist_id: int
    ) -> Optional[List[Dict]]:
        manga_info = await AnimangaStatService.query_user_list_entries(
            anilist_id, MediaType.Manga
        )
        anime_info = await AnimangaStatService.query_user_list_entries(
            anilist_id, MediaType.Anime
        )
        if manga_info is None or anime_info is None:
            return None

        new_list_entries = []
        for entry in manga_info:
            new_list_entries.append(
                {
                    "user_id": user_id,
                    "media_id": entry["mediaId"],
                    "progress": entry["progress"],
                    "is_manga": True,
                }
            )

        for entry in anime_info:
            new_list_entries.append(
                {
                    "user_id": user_id,
                    "media_id": entry["mediaId"],
                    "progress": entry["progress"],
                    "is_manga": False,
                }
            )
        return new_list_entries

    @staticmethod
    async def query_user_list_entries(
        anilist_id: int, media_type: MediaType
    ) -> Optional[List[Dict]]:
        """
        Queries anilist for initial user list, used in comparison for activity tracking

        Args:
            anilist_id (int): Anilist user ID to query
            media_type (str): Specifies anime or manga statistics

        Returns:
            Optional[List[Dict]]: List of media entries, or None if none found
        """
        media_type_str = media_type.name.lower()
        query = """
        query MediaListCollection($userId: Int, $type: MediaType, $statusNotIn: [MediaListStatus]) {
          MediaListCollection(userId: $userId, type: $type, status_not_in: $statusNotIn) {
            lists {
              entries {
                progress
                mediaId
              }
            }
          }
        }
        """
        max_attempts = 3
        async with AsyncClient() as client:
            for attempt in range(max_attempts):
                req_vars = {
                    "userId": anilist_id,
                    "type": media_type_str.upper(),
                    "statusNotIn": ["PLANNING", "COMPLETED"],
                }

                logger.debug(f"Querying list progress for {anilist_id}")
                try:
                    data = await client.post(
                        url="https://graphql.anilist.co",
                        json={"query": query, "variables": req_vars},
                        timeout=10,
                    )
                    if data.status_code == 200:
                        media_lists = data.json()["data"]["MediaListCollection"][
                            "lists"
                        ]
                        entries = []
                        for media_list in media_lists:
                            entries.extend(media_list["entries"])
                        return entries

                except ReadTimeout:
                    logger.warning(f"List progress data for {anilist_id} timed out")
                logger.warning(
                    f"Attempt {attempt + 1}/{max_attempts} failed for {anilist_id}"
                )
                await sleep((1.75**attempt) + uniform(0, 1))

        logger.warning(
            f"Failed to get list entry data for {anilist_id} after {max_attempts}"
        )
        return None

    @staticmethod
    async def fetch_daily_activities(
        guild_id, session_generator: async_sessionmaker
    ) -> List[DailyStatSnapshot]:
        async with session_generator() as session:
            stmt = (
                select(Member)
                .where(Member.guild_id == guild_id)
                .where(Member.stat_tracking_enabled.is_(True))
                .options(selectinload(Member.user).selectinload(User.animanga_entries))
            )
            result = await session.execute(stmt)
            members = result.scalars().all()
            anilist_ids = [m.user.anilist_id for m in members]

        async with httpx.AsyncClient() as client:
            daily_activities = await AnimangaStatService.query_users_daily_activity(
                anilist_ids, client
            )

        async with session_generator() as session:
            daily_stats = await AnimangaStatService.calculate_user_daily_activity(
                members, daily_activities, session, datetime.now(timezone.utc)
            )
            daily_stat_snapshots: List[DailyStatSnapshot] = []
            for stat in daily_stats:
                daily_stat_snapshots.append(
                    DailyStatSnapshot(
                        user_discord_id=stat.member.user_id,
                        placement=stat.placement,
                        minutes_watched=stat.minutes_watched,
                        manga_chapters=stat.manga_chapters,
                        episodes=stat.episodes,
                        ln_chapters=stat.ln_chapters,
                        movies=stat.movies,
                    )
                )
            await session.commit()

        return daily_stat_snapshots

    @staticmethod
    async def query_users_daily_activity(
        anilist_ids: list[int], client: AsyncClient
    ) -> List[Dict]:
        """
        Args:
            anilist_ids (list[int]): Anilist user IDs to query
            client (AsyncClient): HTTP Async client

        Returns:
            List[Dict]: List of  graphQL activity objects from the last 24 hours

        Raises:
            RequestError if either user statistics or list data is empty
        """
        day_seconds = 24 * 60 * 60
        epoch_seconds = int(datetime.now(timezone.utc).timestamp() - day_seconds)

        query = """
        query Page($userIdIn: [Int], $page: Int, $perPage: Int, $createdAtGreater: Int) {
          Page(page: $page, perPage: $perPage) {
            activities(userId_in: $userIdIn, createdAt_greater: $createdAtGreater) {
              ... on ListActivity {
                progress
                media {
                  id
                  type
                  status
                  format
                  duration
                  episodes
                  chapters
                }
                userId
              }
            }
            pageInfo {
              hasNextPage
            }
          }
        }
        """
        page = 1
        has_next_page = True
        max_attempts = 3

        activities = []

        while has_next_page:
            success = False
            for attempt in range(max_attempts):
                req_vars = {
                    "userIdIn": anilist_ids,
                    "page": page,
                    "perPage": 50,
                    "createdAtGreater": epoch_seconds,
                }

                logger.debug(f"Querying daily activities page {page}")

                try:
                    data = await client.post(
                        url="https://graphql.anilist.co",
                        json={"query": query, "variables": req_vars},
                        timeout=10,
                    )
                    if data.status_code == 200:
                        response_data = data.json()
                        page += 1
                        try:
                            has_next_page = response_data["data"]["Page"]["pageInfo"][
                                "hasNextPage"
                            ]
                        except KeyError:
                            logger.warning(
                                "Next page info not found, assuming no more pages"
                            )
                            has_next_page = False

                        activities.extend(response_data["data"]["Page"]["activities"])
                        success = True
                        break

                except ReadTimeout:
                    logger.warning(f"Daily activity data page {page} timed out")
                logger.warning(
                    f"Attempt {attempt + 1}/{max_attempts} failed for daily activity page {page}"
                )
                await sleep((1.75**attempt) + uniform(0, 1))

            if not success:
                logger.warning(
                    f"Failed to get activity data for page {page} after {max_attempts} attempts"
                )
                break

        return activities

    @staticmethod
    async def calculate_user_daily_activity(
        members: Sequence[Member],
        daily_activities: list[Dict],
        session: AsyncSession,
        date: datetime,
    ):
        daily_stats: List[AnimangaDailyStats] = []
        new_list_entries: List[AnimangaListEntry] = []
        list_entries_to_delete: List[AnimangaListEntry] = []
        member_map = {m.id: m for m in members}

        for member in members:
            total_minutes = 0
            activities = [
                activity
                for activity in daily_activities
                if activity["userId"] == member.user.anilist_id
            ]

            manga_list_entries: dict[int, AnimangaListEntry] = {
                entry.media_id: entry
                for entry in member.user.animanga_entries
                if entry.is_manga
            }
            anime_list_entries: dict[int, AnimangaListEntry] = {
                entry.media_id: entry
                for entry in member.user.animanga_entries
                if not entry.is_manga
            }

            manga_chapters = 0
            ln_chapters = 0
            episodes = 0
            movies = 0

            for activity in activities:
                is_manga = activity["media"]["type"] == "MANGA"
                dict_to_check = manga_list_entries if is_manga else anime_list_entries
                current_progress = (
                    1
                    if activity["progress"] is None
                    else AnimangaStatService.get_max_progress_from_str(
                        activity["progress"]
                    )
                )

                is_complete = (
                    current_progress == activity["media"]["chapters"]
                    or current_progress == activity["media"]["episodes"]
                    or activity["progress"] is None
                )
                existing_entry = dict_to_check.get(activity["media"]["id"])

                if existing_entry is None:
                    if not is_complete:
                        previous_progress = 0
                        new_list_entries.append(
                            AnimangaListEntry(
                                user_id=member.user_id,
                                media_id=activity["media"]["id"],
                                progress=current_progress,
                                is_manga=is_manga,
                            )
                        )
                    else:
                        previous_progress = 0
                else:
                    previous_progress = existing_entry.progress

                    if is_complete:
                        list_entries_to_delete.append(
                            dict_to_check[activity["media"]["id"]]
                        )

                total_minutes += AnimangaStatService.calculate_time_delta(
                    activity["media"]["format"],
                    current_progress,
                    previous_progress,
                    duration=activity["media"]["duration"],
                )
                if activity["media"]["format"] == "MANGA":
                    manga_chapters += current_progress - previous_progress
                elif activity["media"]["format"] == "NOVEL":
                    ln_chapters += current_progress - previous_progress
                elif activity["media"]["format"] == "MOVIE":
                    movies += current_progress - previous_progress
                else:
                    episodes += current_progress - previous_progress

            daily_stats.append(
                AnimangaDailyStats(
                    guild_id=member.guild_id,
                    member_id=member.id,
                    minutes_watched=total_minutes,
                    placement=0,
                    date=date,
                    manga_chapters=manga_chapters,
                    ln_chapters=ln_chapters,
                    movies=movies,
                    episodes=episodes,
                )
            )

        daily_stats = sorted(daily_stats, key=lambda d: d.minutes_watched, reverse=True)
        for i, stat in enumerate(daily_stats):
            stat.placement = i + 1

        session.add_all(new_list_entries)
        session.add_all(daily_stats)

        for list_entry in list_entries_to_delete:
            await session.delete(list_entry)

        for stat in daily_stats:
            stat.member = member_map[stat.member_id]

        return daily_stats

    @staticmethod
    def calculate_time_delta(
        media_format: str,
        updated_progress: int,
        original_progress: int,
        duration: Optional[int],
    ):
        if duration is not None:
            minutes_per_unit = duration
        else:
            minutes_per_unit = 23
            match media_format:
                case "MANGA":
                    minutes_per_unit = 7
                case "NOVEL":
                    minutes_per_unit = 30
                case "ONE_SHOT":
                    minutes_per_unit = 10
                case "TV":
                    minutes_per_unit = 23
                case "MOVIE":
                    minutes_per_unit = 90
                case "MUSIC":
                    minutes_per_unit = 5
                case "TV_SHORT":
                    minutes_per_unit = 4
                case "SPECIAL":
                    minutes_per_unit = 5
                case "OVA":
                    minutes_per_unit = 23
                case "ONA":
                    minutes_per_unit = 23

        return (updated_progress - original_progress) * minutes_per_unit

    @staticmethod
    def get_max_progress_from_str(activity_progress_str):
        activity_progress = activity_progress_str.split("-")
        return int(activity_progress[-1])
