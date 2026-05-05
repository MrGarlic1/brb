from sqlalchemy.ext.asyncio import AsyncSession
from brbot.db.models import Neko
from brbot.Features.Admin.data import NekoRarity, NekoClassificationInfo
from discord import Embed
from sqlalchemy import delete, select, or_
from sqlalchemy.exc import IntegrityError
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class AdminService:
    def __init__(
        self,
    ):
        pass

    @staticmethod
    async def get_neko_classification_info(
        session: AsyncSession,
    ) -> Optional[NekoClassificationInfo]:
        stmt = (
            select(Neko).where(or_(Neko.nsfw.is_(None), Neko.rarity.is_(None))).limit(1)
        )
        result = await session.execute(stmt)
        neko: Neko = result.scalars().one_or_none()
        if neko is None:
            return None

        neko_id = neko.id
        img_url = neko.image_url
        rarity = NekoRarity.A
        is_nsfw = False

        return NekoClassificationInfo(
            neko_id=neko_id,
            image_url=img_url,
            rarity=rarity,
            is_nsfw=is_nsfw,
        )

    @staticmethod
    async def gen_neko_classification_embed(
        neko: Optional[NekoClassificationInfo],
    ) -> Embed:
        embed = Embed(title="Neko Classification")
        if neko is None:
            embed.add_field(
                name="Done!",
                value="There are no unclassified nekos remaining! Good work.",
            )
            return embed

        embed.set_image(url=neko.image_url)
        embed.set_footer(
            text=f"Current Values: \nSFW: {'❌' if neko.is_nsfw else '✅'}\nRarity: {neko.rarity}"
        )
        return embed

    @staticmethod
    async def update_neko(neko: NekoClassificationInfo, session: AsyncSession) -> None:
        stmt = select(Neko).where(Neko.id == neko.neko_id)
        result = await session.execute(stmt)
        db_neko: Neko = result.scalars().one_or_none()
        if db_neko is None:
            logger.warning(f"Neko ID {neko.neko_id} unexpectedly doesn't exist in db.")
            return

        db_neko.rarity = neko.rarity.value
        db_neko.is_nsfw = neko.is_nsfw

        try:
            await session.commit()
        except IntegrityError:
            logger.warning(
                f"Failed to update {neko.neko_id} in db due to race condition."
            )

    @staticmethod
    async def delete_neko(neko: NekoClassificationInfo, session: AsyncSession) -> None:
        stmt = delete(Neko).where(Neko.id == neko.neko_id)
        await session.execute(stmt)
        await session.commit()
