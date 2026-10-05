from httpx import AsyncClient, Response
from cryptography.fernet import Fernet
from random import shuffle

from asyncio import sleep as asyncio_sleep
from brbot.Features.Mtg.data import base_url, user_agent, InvalidKeyError
from brbot.db.models import Guild, Member
from discord import User as DiscordUser
from os import getenv
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import Optional, Dict, List
from brbot.Shared.Users.repository import get_or_create_user


class PlaygroupService:
    def __init__(self, async_session_generator: async_sessionmaker):
        key = getenv("ENCRYPTION_KEY")
        if key is None:
            raise RuntimeError("ENCRYPTION_KEY environment variable not set")

        self.cipher = Fernet(key.encode())
        self.session_generator = async_session_generator

    async def register_api_key(self, discord_user: DiscordUser, key: str):
        async with AsyncClient(
            headers={"User-Agent": user_agent, "Authorization": f"Bearer {key}"}
        ) as client:
            r = await client.get(f"{base_url}/me")

        if self.is_request_success(r):
            rsp_json = r.json()
        else:
            raise InvalidKeyError

        encrypted_key = self.cipher.encrypt(key.encode())

        async with self.session_generator() as session:
            user = await get_or_create_user(discord_user.id, discord_user.name, session)
            user.playgroup_id = rsp_json["id"]
            user.playgroup_name = rsp_json["username"]
            user.encoded_playgroup_key = encrypted_key.decode()
            await session.commit()

    @staticmethod
    async def is_request_success(r: Response) -> bool:
        if r.status_code == 200:
            return True
        elif r.status_code == 429:
            raise ConnectionRefusedError(f"Rate limit exceeded for {base_url}")
        else:
            return False

    async def remove_api_key(self, discord_user: DiscordUser) -> None:
        async with self.session_generator() as session:
            user = await get_or_create_user(discord_user.id, discord_user.name, session)
            user.encoded_playgroup_key = None
            await session.commit()

    def decrypt_api_key(self, key: str) -> str:
        return self.cipher.decrypt(key.encode()).decode()

    async def get_daily_playgroup_games(self, guild_id: int):
        async with self.session_generator() as session:
            stmt = (
                select(Guild)
                .where(Guild.id == guild_id)
                .options(selectinload(Guild.config))
                .options(selectinload(Guild.members).selectinload(Member.user))
            )
            result = await session.execute(stmt)
            guild: Guild = result.scalar_one()
            guild_playgroup_id = guild.config.tracked_playgroup_id

            member_keys = [
                m.user.encoded_playgroup_key
                for m in guild.members
                if m.user.encoded_playgroup_key is not None
            ]
            if not member_keys:
                return

        shuffle(member_keys)  # Don't favor use of a single user's key
        games_data = await self.query_playgroup_game_data(
            member_keys, guild_playgroup_id
        )
        if not games_data:
            return

        # now = datetime.now(timezone.utc)
        # daily_games = [
        #    g
        #    for g in games_data
        #    if datetime.fromisoformat(g["ended_at"].replace("Z", "+00:00"))
        #    > now - timedelta(days=1)
        # ]

    async def query_playgroup_game_data(
        self, encoded_keys: list[str], playgroup_id: int
    ) -> Optional[List[Dict]]:
        async with AsyncClient(headers={"User-Agent": user_agent}) as client:
            for encoded_key in encoded_keys:
                client.headers["Authorization"] = f"Bearer {encoded_key}"
                r = await client.get(f"{base_url}/playgroups/{playgroup_id}/games")

                if self.is_request_success(r):
                    return r.json()
                await asyncio_sleep(0.25)
        return None
