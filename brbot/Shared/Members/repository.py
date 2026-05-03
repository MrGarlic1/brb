from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from brbot.db.models import Member


async def get_or_create_member(
    user_id: int, guild_id: int, session: AsyncSession
) -> Member:
    stmt = (
        select(Member)
        .where(Member.user_id == user_id)
        .where(Member.guild_id == guild_id)
    )

    result = await session.execute(stmt)
    member: Member = result.scalar_one_or_none()
    if member:
        return member

    member = Member(user_id=user_id, guild_id=guild_id)
    session.add(member)

    try:
        await session.commit()
        return member
    except IntegrityError:
        await session.rollback()
        result = await session.execute(stmt)
        user = result.scalar_one()
        return user
