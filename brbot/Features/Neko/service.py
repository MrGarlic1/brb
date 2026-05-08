from sqlalchemy.ext.asyncio import AsyncSession
from brbot.Shared.Neko.models import NekoRarity
from brbot.Features.Neko.data import (
    NEKO_ROLL_CHANCES,
    NEKO_HOURLY_ROLLS,
    NEKO_NSFW_LOSS_CHANCES,
)
from random import uniform
from sqlalchemy import select, func
from brbot.db.models import Neko
from datetime import datetime


class NekoService:
    def __init__(self):
        self.guild_user_hourly_rolls: dict[int, dict[int, int]] = {}
        self.current_hour = datetime.now().hour

    @staticmethod
    def roll_rarity() -> NekoRarity:
        cumulative = 0
        rng = uniform(0, 1)
        selected_roll_rarity = NekoRarity.B  # Default
        for rarity_level, chance in NEKO_ROLL_CHANCES.items():
            cumulative += chance
            if rng <= cumulative:
                selected_roll_rarity = rarity_level
                break
        return selected_roll_rarity

    @staticmethod
    async def roll_and_get_neko_info(
        include_nsfw: bool, rarity: NekoRarity, session: AsyncSession
    ) -> tuple[str, str]:
        if include_nsfw:
            nsfw_roll = uniform(0, 1)
            if nsfw_roll <= NEKO_NSFW_LOSS_CHANCES[rarity]:
                include_nsfw = False

        stmt = (
            select(Neko)
            .where(Neko.nsfw.is_(include_nsfw))
            .where(Neko.rarity.is_(rarity.value))
            .order_by(func.random())
            .limit(1)
        )

        result = await session.execute(stmt)
        neko: Neko = result.scalars().one()

        return neko.image_url, neko.source

    async def check_remaining_hourly_rolls(self, guild_id, user_id) -> int:
        if datetime.now().hour != self.current_hour:
            self.guild_user_hourly_rolls = {}
            self.current_hour = datetime.now().hour

        if guild_id not in self.guild_user_hourly_rolls:
            self.guild_user_hourly_rolls[guild_id] = {}
        if user_id not in self.guild_user_hourly_rolls[guild_id]:
            self.guild_user_hourly_rolls[guild_id][user_id] = NEKO_HOURLY_ROLLS

        return self.guild_user_hourly_rolls[guild_id][user_id]
