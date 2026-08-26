import uuid as uuid_lib

from aiogram import Bot
from sqlalchemy import select

from app.config import CHANNEL_ID
from app.db import async_session
from app.models import User


async def is_subscribed(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
    except Exception:
        # бот не админ канала, канал недоступен и т.п. — считаем, что не подписан
        return False
    return member.status not in ("left", "kicked")


async def get_or_create_user(tg_id: int, username: str | None) -> User:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.tg_id == tg_id))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                tg_id=tg_id,
                username=username,
                vless_uuid=str(uuid_lib.uuid4()),
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
        return user
