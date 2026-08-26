from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.config import SUB_DOMAIN
from app.db import async_session
from app.models import Subscription
from app.services.qr import make_qr
from app.services.subscription import send_subscription
from app.services.users import get_or_create_user, is_subscribed
from app.settings.tariffs import TARIFFS
from app.texts.messages import (
    NOT_SUBSCRIBED_ALERT,
    NO_ACTIVE_SUBSCRIPTION_TEXT,
    my_subscription_text,
)

router = Router()


@router.callback_query(F.data == "check_sub")
async def cb_check_sub(callback: CallbackQuery, bot: Bot):
    user = await get_or_create_user(callback.from_user.id, callback.from_user.username)

    if not await is_subscribed(bot, callback.from_user.id):
        await callback.answer(NOT_SUBSCRIBED_ALERT, show_alert=True)
        return

    await callback.answer()
    await send_subscription(callback, user, TARIFFS["trial"]["days"])


@router.message(F.text == "📱 Моя подписка")
async def my_subscription(message: Message):

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
            .order_by(
                Subscription.created_at.desc()
            )
        )

        sub = result.scalars().first()

    if not sub:
        await message.answer(NO_ACTIVE_SUBSCRIPTION_TEXT)
        return

    expiry = sub.expiry.strftime("%d.%m.%Y %H:%M")

    status = "🟢 Активна" if sub.is_valid else "🔴 Истекла"

    sub_url = f"{SUB_DOMAIN}/sub/{sub.token}"
    qr_file = make_qr(sub_url)

    await message.answer_photo(
        photo=qr_file,
        caption=my_subscription_text(status, expiry, sub_url),
        parse_mode="Markdown",
    )
