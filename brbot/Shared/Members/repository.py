from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, tuple_
from brbot.db.models import Member


async def get_or_create_member(
    user_id: int, guild_id: int, session: AsyncSession
) -> Member:
    stmt = (
        select(Member)
        .where(Member.user_id == user_id)
        .where(Member.guild_id == guild_id)
    )
    async with session.begin_nested():
        result = await session.execute(stmt)
        member: Member = result.scalar_one_or_none()
        if member:
            return member

        member = Member(user_id=user_id, guild_id=guild_id)
        session.add(member)

        try:
            await session.flush()
            return member
        except IntegrityError:
            pass

        result = await session.execute(stmt)
        member = result.scalar_one_or_none()
        if member is None:
            raise RuntimeError(
                f"Member with user ID {user_id} and guild id {guild_id} is unexpectedly not found."
            )
        return member


async def get_or_create_members(
    user_ids: list[int],
    guild_id_values: list[int] | int,
    session: AsyncSession,
) -> list[Member]:
    if isinstance(guild_id_values, int):
        guild_id_values = [guild_id_values] * len(user_ids)

    if len(user_ids) != len(guild_id_values):
        raise ValueError("User IDs and guild IDs must have the same number of entries.")

    id_pairs = list(zip(user_ids, guild_id_values))

    # Preload existing members
    stmt = select(Member).where(tuple_(Member.user_id, Member.guild_id).in_(id_pairs))
    result = await session.execute(stmt)
    existing = {(m.user_id, m.guild_id): m for m in result.scalars()}

    members: list[Member] = []

    for user_id, guild_id in id_pairs:
        member = existing.get((user_id, guild_id))
        if member is None:
            member = await get_or_create_member(user_id, guild_id, session)
        members.append(member)

    return members
