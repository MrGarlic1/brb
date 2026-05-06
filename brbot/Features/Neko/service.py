from sqlalchemy.ext.asyncio import AsyncSession
from brbot.Shared.Neko.models import NekoRarity
from brbot.Features.Neko.data import NEKO_ROLL_CHANCES
from random import uniform
from sqlalchemy import select, func
from brbot.db.models import Neko


class NekoService:
    def __init__(self):
        pass

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
        stmt = select(Neko).where(Neko.nsfw.is_not(None))
        if not include_nsfw:
            stmt = stmt.where(Neko.nsfw.is_(False))

        stmt = stmt.where(Neko.rarity.is_(rarity.value))
        stmt = stmt.order_by(func.random()).limit(1)

        result = await session.execute(stmt)
        neko: Neko = result.scalars().one()

        return neko.image_url, neko.source
