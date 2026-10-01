from httpx import AsyncClient
from cryptography.fernet import Fernet
from brbot.Features.Mtg.data import base_url, user_agent
from discord import User as DiscordUser
from os import getenv
from sqlalchemy.ext.asyncio import async_sessionmaker
from brbot.Shared.Users.repository import get_or_create_user


class PlaygroupService:
    def __init__(self, async_session_generator: async_sessionmaker):
        key = getenv("ENCRYPTION_KEY")
        if key is None:
            raise RuntimeError("ENCRYPTION_KEY environment variable not set")

        self.cipher = Fernet(key.encode())
        self.session_generator = async_session_generator

    @staticmethod
    async def api_key_is_valid(key: str) -> bool:
        async with AsyncClient(
            headers={"User-Agent": user_agent, "Authorization": f"Bearer {key}"}
        ) as client:
            r = await client.get(f"{base_url}/me")
            if r.status_code == 200:
                return True
            elif r.status_code == 429:
                raise ConnectionRefusedError(f"Rate limit exceeded for {base_url}")
            else:
                return False

    async def encrypt_and_store_api_key(
        self, key: str, discord_user: DiscordUser
    ) -> None:
        encrypted_key = self.cipher.encrypt(key.encode())
        async with self.session_generator() as session:
            user = await get_or_create_user(discord_user.id, discord_user.name, session)
            user.encoded_playgroup_key = encrypted_key.decode()
            await session.commit()

    def decrypt_api_key(self, key: str) -> str:
        return self.cipher.decrypt(key.encode()).decode()
