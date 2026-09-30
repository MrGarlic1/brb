from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from brbot.db.models import User
from typing import Sequence


async def get_or_create_user(
    user_id: int, username: str, session: AsyncSession
) -> User:
    stmt = select(User).where(User.user_id == user_id)

    async with session.begin_nested():
        result = await session.execute(stmt)
        user: User = result.scalar_one_or_none()
        if user is not None and user.name == username:
            return user

        if user is not None:
            user.name = username
        else:
            user = User(user_id=user_id, name=username)
            session.add(user)

        try:
            await session.flush()
            return user
        except IntegrityError:
            pass

        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            raise RuntimeError(f"User {user_id} is unexpectedly not found.")
        return user


async def get_or_create_users(
    user_ids: list[int], usernames: list[str], session: AsyncSession
) -> list[User]:
    if len(user_ids) != len(usernames):
        raise ValueError("Users and usernames must have the same length")

    user_info = dict(zip(user_ids, usernames))

    stmt = select(User).where(User.user_id.in_(user_ids))

    result = await session.execute(stmt)
    existing: Sequence[User] = result.scalars().all()
    existing_users = {u.user_id: u for u in existing}

    users: list[User] = []
    for user_id in user_ids:
        user = existing_users.get(user_id, None)
        if user is None:
            user = await get_or_create_user(user_id, user_info[user_id], session)
        users.append(user)

    return users
