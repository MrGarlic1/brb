import logging
from asyncio import sleep
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from random import uniform
from statistics import mean, stdev
import httpx
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from typing import Optional, Dict, List, Sequence

from sqlalchemy.orm import selectinload

from brbot.Features.Animanga.data import (
    MediaType,
    DailyStatSnapshot,
    placement_emojis,
    LeaderboardStats,
)
from brbot.db.models import AnimangaDailyStats, AnimangaListEntry, Member, User
from httpx import AsyncClient, ReadTimeout
from discord import (
    Embed,
    Guild as DiscordGuild,
    Member as DiscordMember,
)

logger = logging.getLogger(__name__)


class AniListAPIError(Exception):
    """AniList API request failed after all retries."""


class AnimangaStatService:
    def __init__(self):
        pass

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
    async def query_users_daily_activity(
        anilist_ids: list[int], beginning_timestamp: int | float, client: AsyncClient
    ) -> List[Dict]:
        """
        Args:
            anilist_ids (list[int]): Anilist user IDs to query
            beginning_timestamp (int): Beginning timestamp to query activity for
            client (AsyncClient): HTTP Async client

        Returns:
            List[Dict]: List of  graphQL activity objects from the last 24 hours

        Raises:
            AniListAPIError if either user statistics or list data is empty, or if request failed
        """

        query = """
        query Page($userIdIn: [Int], $page: Int, $perPage: Int, $createdAtGreater: Int, $sort: [ActivitySort]) {
          Page(page: $page, perPage: $perPage) {
            activities(userId_in: $userIdIn, createdAt_greater: $createdAtGreater, sort: $sort) {
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
                status
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
                    "createdAtGreater": beginning_timestamp,
                    "sort": ["ID"],
                }

                logger.debug(f"Querying daily activities page {page}")

                try:
                    data = await client.post(
                        url="https://graphql.anilist.co",
                        json={"query": query, "variables": req_vars},
                        timeout=10,
                    )
                    response_data = data.json()
                    if data.status_code == 200:
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

                    else:
                        if "errors" in response_data:
                            logger.warning(
                                f"Request error {"; ".join(response_data["errors"])}"
                            )

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
                raise AniListAPIError()

        return activities

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
    async def process_daily_activities(
        guild_id, session_generator: async_sessionmaker
    ) -> Optional[List[DailyStatSnapshot]]:
        async with session_generator() as session:
            stmt = (
                select(Member)
                .where(Member.guild_id == guild_id)
                .where(Member.stat_tracking_enabled.is_(True))
                .options(selectinload(Member.user))
            )
            result = await session.execute(stmt)
            members = result.scalars().all()
            anilist_ids = [m.user.anilist_id for m in members]

        async with session_generator() as session:
            recent_leaderboard_datetime = await session.scalar(
                select(func.max(AnimangaDailyStats.date)).where(
                    AnimangaDailyStats.guild_id == guild_id
                )
            )

            recent_leaderboard_timestamp = (
                recent_leaderboard_datetime.timestamp()
                if recent_leaderboard_datetime is not None
                else (datetime.now(timezone.utc) - timedelta(days=1)).timestamp()
            )

        async with httpx.AsyncClient() as client:
            try:
                daily_activities = await AnimangaStatService.query_users_daily_activity(
                    anilist_ids, recent_leaderboard_timestamp, client
                )
            except AniListAPIError:
                return None

        async with session_generator() as session:
            stmt = (
                select(Member)
                .where(Member.guild_id == guild_id)
                .where(Member.stat_tracking_enabled.is_(True))
                .options(selectinload(Member.user).selectinload(User.animanga_entries))
            )
            result = await session.execute(stmt)
            members = result.scalars().all()

            daily_stats = await AnimangaStatService.calculate_daily_activity_stats(
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
    async def calculate_daily_activity_stats(
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
                if activity.get("userId")
                and activity.get("userId") == member.user.anilist_id
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
                if activity.get("status") in ("plans to watch", "plans to read"):
                    continue

                if activity.get("status") in ("paused reading", "paused watching"):
                    continue

                if activity.get("status") == "dropped":
                    continue

                is_manga = activity["media"]["type"] == "MANGA"
                dict_to_check = manga_list_entries if is_manga else anime_list_entries

                current_progress = AnimangaStatService.get_max_progress_from_str(
                    activity["progress"]
                )
                is_complete = activity.get("status") == "completed"

                if current_progress is None and is_complete:
                    current_progress = (
                        activity["media"]["chapters"]
                        if is_manga
                        else activity["media"]["episodes"]
                    )

                if current_progress is None:
                    current_progress = 1

                existing_entry = dict_to_check.get(activity["media"]["id"])

                if existing_entry is None:
                    if not is_complete:
                        previous_progress = 0
                        updated_entry = AnimangaListEntry(
                            user_id=member.user_id,
                            media_id=activity["media"]["id"],
                            progress=current_progress,
                            is_manga=is_manga,
                        )
                        new_list_entries.append(updated_entry)
                        dict_to_check[activity["media"]["id"]] = updated_entry
                    else:
                        previous_progress = 0
                else:
                    previous_progress = existing_entry.progress
                    existing_entry.progress = current_progress

                    if is_complete:
                        if existing_entry in new_list_entries:
                            new_list_entries.remove(existing_entry)
                        else:
                            list_entries_to_delete.append(existing_entry)

                progress_diff = max(current_progress - previous_progress, 0)

                total_minutes += AnimangaStatService.calculate_activity_time(
                    activity["media"]["format"],
                    progress_diff,
                    duration=activity["media"]["duration"],
                )
                if activity["media"]["format"] == "MANGA":
                    manga_chapters += progress_diff
                elif activity["media"]["format"] == "NOVEL":
                    ln_chapters += progress_diff
                elif activity["media"]["format"] == "MOVIE":
                    movies += progress_diff
                else:
                    episodes += progress_diff

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
    def calculate_activity_time(
        media_format: str,
        progress_diff: int,
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

        return progress_diff * minutes_per_unit

    @staticmethod
    def get_max_progress_from_str(activity_progress_str: str | None):
        if activity_progress_str is None:
            return None
        activity_progress = activity_progress_str.split("-")
        return int(activity_progress[-1])

    @staticmethod
    async def get_leaderboard_stats(
        member: Member, session: AsyncSession
    ) -> Dict[int, LeaderboardStats]:
        stmt = (
            select(AnimangaDailyStats)
            .where(AnimangaDailyStats.guild_id == member.guild_id)
            .options(selectinload(AnimangaDailyStats.member).selectinload(Member.user))
        )

        result = await session.execute(stmt)
        daily_rankings: Sequence[AnimangaDailyStats] = result.scalars().all()
        daily_rankings_by_user_id: Dict[int, List[AnimangaDailyStats]] = defaultdict(
            list
        )
        for ranking in daily_rankings:
            daily_rankings_by_user_id[ranking.member.user_id].append(ranking)

        member_leaderboard_stats: dict[int, LeaderboardStats] = {}
        for user_id, rankings in daily_rankings_by_user_id.items():
            member_leaderboard_stats[user_id] = (
                AnimangaStatService.calculate_individual_leaderboard_stats(rankings)
            )

        sorted_member_leaderboard_stats = dict(
            sorted(
                member_leaderboard_stats.items(),
                key=lambda kv: (
                    kv[1].first_place_finishes,
                    kv[1].total_minutes_watched,
                ),
                reverse=True,
            )
        )
        return sorted_member_leaderboard_stats

    @staticmethod
    def calculate_individual_leaderboard_stats(
        daily_rankings: list[AnimangaDailyStats],
    ) -> LeaderboardStats:
        formats_consumed = {"Anime📺": 0, "Movie📽": 0, "Manga💬": 0, "Light Novel📖": 0}
        placements = []
        minutes_watched = []
        record = 0
        missed_days = 0
        record_date = None
        max_streak = 0
        current_streak = 0
        for r in daily_rankings:
            placements.append(r.placement)
            minutes_watched.append(r.minutes_watched)
            formats_consumed["Anime📺"] += r.episodes
            formats_consumed["Movie📽"] += r.movies
            formats_consumed["Manga💬"] += r.manga_chapters
            formats_consumed["Light Novel📖"] += r.ln_chapters

            if r.minutes_watched > record:
                record = r.minutes_watched
                record_date = r.date

            if r.minutes_watched == 0:
                missed_days += 1
                current_streak = 0
            else:
                current_streak += 1
                if current_streak >= max_streak:
                    max_streak = current_streak

        placements_dict = dict(sorted(Counter(placements).items()))

        try:
            consistency = (
                1 - stdev(minutes_watched) / (record - min(minutes_watched))
            ) * 100
            consistency = max(min(consistency, 100), 0)
        except ZeroDivisionError:
            consistency = 100

        return LeaderboardStats(
            consistency=consistency,
            missed_days=missed_days,
            record=record,
            record_date=record_date,
            first_place_finishes=placements_dict.get(1, 0),
            placements=placements_dict,
            average_minutes_watched=mean(minutes_watched),
            average_minutes_watched_active=mean([m for m in minutes_watched if m != 0]),
            current_streak=current_streak,
            max_streak=max_streak,
            total_minutes_watched=sum(minutes_watched),
            formats=formats_consumed,
        )

    @staticmethod
    async def create_leaderboard_embed(
        guild: DiscordGuild, date: datetime, daily_stats: list[DailyStatSnapshot] | None
    ) -> Embed:
        embed = Embed(title=f"Weeb Leaderboard {date.strftime('%Y/%m/%d')}")
        embed.set_author(name=guild.name, icon_url=guild.icon.url)
        if daily_stats is None:
            embed.add_field(
                name="\u200b", value="An error occurred when fetching leaderboard data!"
            )
            return embed

        daily_stats = sorted(daily_stats, key=lambda d: d.minutes_watched, reverse=True)
        placements = list(placement_emojis.keys())
        for i in range(min(len(daily_stats), len(placement_emojis))):
            pos = daily_stats[i]
            if i == 0:
                member = await guild.fetch_member(pos.user_discord_id)
                embed.set_thumbnail(url=member.avatar.url)

            user_str = f"**{placement_emojis[placements[i]]}: <@{pos.user_discord_id}> ({pos.minutes_watched} minutes**)\n"
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
                inline=False,
            )
        embed.set_footer(
            text="Want to be on the daily leaderboard? /animanga track_daily"
        )

        return embed

    @staticmethod
    def create_leaderboard_stats_embed(
        member: DiscordMember,
        guild: DiscordGuild,
        guild_leaderboard_stats: dict[int, LeaderboardStats],
    ) -> Embed:
        color = 0x19356D

        user_stats = guild_leaderboard_stats.get(member.id)

        try:
            member_server_rank = list(guild_leaderboard_stats.keys()).index(member.id)
        except ValueError:
            member_server_rank = -1

        if member_server_rank == 0:
            color = 0xD6AF36
        elif member_server_rank == 1:
            color = 0xA7A7AD
        elif member_server_rank == 2:
            color = 0xA77044

        embed = Embed(title=f"Leaderboard Stats for {member.name}", color=color)
        embed.set_author(name=guild.name, icon_url=guild.icon.url)
        embed.set_thumbnail(url=member.avatar.url)

        # No leaderboards/user is not tracking stats
        if user_stats is None or not user_stats.placements:
            embed.add_field(
                name="\u200b",
                value="**You have no stats yet!**",
            )
            return embed

        individual_stats_str = "**Daily Rankings:** "
        for rank, count in user_stats.placements.items():
            individual_stats_str += f"{placement_emojis[rank]}: {count} | "

        individual_stats_str += f"\n**Current Streak:** {user_stats.current_streak} days (record {user_stats.max_streak})\n"

        individual_stats_str += f"**Consistency:** {user_stats.consistency:.2f}%\n"
        individual_stats_str += (
            f"**Most Time in 1 Day:** {user_stats.record} minutes on "
            f"{user_stats.record_date.strftime('%b %d %Y')}\n"
        )
        individual_stats_str += f"**Average Time:** {user_stats.average_minutes_watched:.2f} | {user_stats.average_minutes_watched_active:.2f} minutes/day (all | active only)\n"
        individual_stats_str += (
            f"**Total Watch Time:** {user_stats.total_minutes_watched} minutes\n"
        )
        individual_stats_str += f"**Missed Days:** {user_stats.missed_days}\n"

        individual_stats_str += "**Formats Consumed:** "
        for media_format, count in user_stats.formats.items():
            individual_stats_str += f"{media_format}: **{count}** | "

        leaderboard_placement_str = ""
        for i, user_id in enumerate(list(guild_leaderboard_stats.keys())[0:10]):
            leaderboard_placement_str += f"{placement_emojis[i + 1]}: <@{user_id}>\n"

        embed.add_field(
            name="Individual Statistics",
            value=individual_stats_str,
            inline=False,
        )
        embed.add_field(
            name="Server Overall Rankings",
            value=leaderboard_placement_str,
            inline=False,
        )
        embed.set_footer(
            text="Want to be on the daily leaderboard? /animanga track_daily"
        )

        return embed
