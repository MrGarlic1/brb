from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from brbot.db.models import User


async def get_or_create_user(
    user_id: int, username: str, session: AsyncSession
) -> User:
    stmt = select(User).where(User.user_id == user_id)

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
        await session.commit()
        return user
    except IntegrityError:
        await session.rollback()
        result = await session.execute(stmt)
        user = result.scalar_one()
        return user
