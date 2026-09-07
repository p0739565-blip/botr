from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy import select

from app.db import async_session
from app.models import Subscription
from app.services.subscription import send_subscription
from app.services.users import get_or_create_user
from app.settings.tariffs import TARIFFS
from app.texts.messages import ALREADY_HAS_SUBSCRIPTION_TEXT

router = Router()


@router.message(F.text == "🚀 Получить VPN")
async def get_vpn(message: Message):

    user = await get_or_create_user(
        message.from_user.id,
        message.from_user.username
    )

    async with async_session() as session:

        result = await session.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user.id
            )
        )

        sub = result.scalars().first()

    if sub:
        await message.answer(ALREADY_HAS_SUBSCRIPTION_TEXT)
        return

    await send_subscription(
        message,
        user,
        TARIFFS["trial"]["days"]
    )
