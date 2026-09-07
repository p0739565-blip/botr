import datetime
import secrets

from aiogram import Bot
from aiogram.types import CallbackQuery
from sqlalchemy import select

from app.config import SUB_DOMAIN
from app.db import async_session
from app.keyboards.reply import main_menu
from app.models import Subscription, User
from app.services.qr import make_qr
from app.texts.messages import subscription_issued_text


async def issue_subscription(
    user: User,
    days: int,
) -> Subscription:
    """
    Создать или продлить подписку.

    days — количество дней, добавляемых к подписке.

    Если у пользователя уже есть активная (не истёкшая) подписка —
    days прибавляются к её текущему expiry (продление "поверх" остатка).
    Если активной подписки нет — создаётся новая, отсчитываясь от
    текущего момента.
    """

    now = datetime.datetime.now()

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

        existing = result.scalars().first()

        if existing and existing.is_valid:
            # Продление: прибавляем дни к текущему остатку, а не
            # начинаем отсчёт заново — иначе пользователь теряет уже
            # оплаченное время.
            existing.expiry = existing.expiry + datetime.timedelta(days=days)

            await session.commit()
            await session.refresh(existing)

            return existing

        token = secrets.token_urlsafe(16)

        subscription = Subscription(
            user_id=user.id,
            token=token,
            expiry=now + datetime.timedelta(days=days),
            is_active=True,
        )

        session.add(subscription)

        await session.commit()
        await session.refresh(subscription)

        return subscription


async def send_subscription(
    message_or_callback,
    user: User,
    days: int,
) -> None:
    """
    Выдать (или продлить) пользователю подписку на указанное количество
    дней. Используется одинаково для триала, Stars, карты и крипты —
    вызывающий код просто передаёт days и объект user.
    """

    subscription = await issue_subscription(
        user=user,
        days=days,
    )

    sub_url = f"{SUB_DOMAIN}/sub/{subscription.token}"

    expiry_str = subscription.expiry.strftime("%d.%m.%Y %H:%M")

    text = subscription_issued_text(
        sub_url=sub_url,
        expiry_str=expiry_str,
    )

    qr_file = make_qr(sub_url)

    target = (
        message_or_callback.message
        if isinstance(message_or_callback, CallbackQuery)
        else message_or_callback
    )

    # Клавиатура снизу — отдельный параметр сообщения, который Telegram
    # запоминает только с того сообщения, где он передан. Подписка
    # часто выдаётся через inline-кнопку ("✅ Я подписался" на канал),
    # а не через /start, поэтому если не прислать её здесь, у
    # пользователя не появится нижнее меню, пока он не наберёт /start
    # заново.
    await target.answer_photo(
        photo=qr_file,
        caption=text,
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )


async def send_subscription_by_chat_id(
    bot: Bot,
    chat_id: int,
    user: User,
    days: int,
) -> None:
    """
    То же самое, что send_subscription(), но для случаев, когда нет
    объекта Message/CallbackQuery — например, из вебхука Platega в
    процессе app.api, у которого нет aiogram-диспетчера и который
    поэтому создаёт свой собственный Bot() и шлёт сообщения напрямую
    по chat_id.
    """

    subscription = await issue_subscription(
        user=user,
        days=days,
    )

    sub_url = f"{SUB_DOMAIN}/sub/{subscription.token}"

    expiry_str = subscription.expiry.strftime("%d.%m.%Y %H:%M")

    text = subscription_issued_text(
        sub_url=sub_url,
        expiry_str=expiry_str,
    )

    qr_file = make_qr(sub_url)

    await bot.send_photo(
        chat_id=chat_id,
        photo=qr_file,
        caption=text,
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )
