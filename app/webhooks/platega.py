"""
Приём callback'ов от Platega об изменении статуса транзакции.

URL для настройки в личном кабинете Platega (Настройки → Callback
URLs): {SUB_DOMAIN}/webhooks/platega

Документация: https://docs.platega.io/callback-об-изменении-статуса-транзакции

Важно: этот роутер живёт в процессе app.api (uvicorn), у которого нет
aiogram-диспетчера — только сам процесс бота (app.bot) его запускает.
Поэтому для отправки сообщения пользователю здесь заводится собственный
Bot(token=BOT_TOKEN); это два независимых клиента одного и того же
бота, Telegram Bot API это допускает.
"""

import logging

from aiogram import Bot
from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from app.config import BOT_TOKEN, PLATEGA_MERCHANT_ID, PLATEGA_SECRET
from app.db import async_session
from app.models import Payment, PlategaPayment, User
from app.services.referral import maybe_reward_referrer
from app.services.subscription import send_subscription_by_chat_id
from app.settings.tariffs import TARIFFS
from app.texts.messages import PAYMENT_THANKS_TEXT

logger = logging.getLogger("platega_webhook")

router = APIRouter()

# Отдельный Bot для уведомлений из вебхука — см. пояснение в шапке
# файла. Токен тот же, что у основного бота.
_notify_bot = Bot(token=BOT_TOKEN)

# Статусы, которые реально приходят от Platega (см. CallbackPayload).
STATUS_CONFIRMED = "CONFIRMED"
STATUS_CANCELED = "CANCELED"
STATUS_CHARGEBACKED = "CHARGEBACKED"


async def process_status_update(transaction_id: str, status: str, *, source: str = "webhook") -> None:
    """Общая обработка нового статуса транзакции Platega — общая для
    вебхука (вызывается сразу при колбэке) и для фоновой сверки
    (app.services.platega_reconciliation, вызывается по опросу API,
    когда колбэк не дошёл — например, из-за смены адреса туннеля).

    Идемпотентна: если платёж уже в терминальном статусе, ничего не
    делает повторно, так что дублирующийся вызов из вебхука и сверки
    (или несколько ретраев самой Platega) безопасен."""

    async with async_session() as session:
        result = await session.execute(
            select(PlategaPayment).where(
                PlategaPayment.transaction_id == transaction_id
            )
        )
        payment = result.scalar_one_or_none()

        if payment is None:
            logger.warning(
                "platega %s: unknown transaction_id=%s", source, transaction_id
            )
            return

        if payment.status in (STATUS_CONFIRMED, STATUS_CANCELED, STATUS_CHARGEBACKED):
            # Уже обработан — либо повторный колбэк, либо сверка
            # догнала транзакцию, которую вебхук уже успел обработать.
            return

        payment.status = status
        user_id = payment.user_id
        chat_id = payment.chat_id
        tariff_key = payment.tariff_key
        amount = payment.amount
        method = payment.method or "card"

        await session.commit()

        if status == STATUS_CONFIRMED:
            user_result = await session.execute(
                select(User).where(User.id == user_id)
            )
            user = user_result.scalar_one_or_none()

    if status != STATUS_CONFIRMED:
        # CANCELED — платёж не прошёл, пользователь и так видит это на
        # странице оплаты. CHARGEBACKED — возврат по уже выданной
        # подписке; отмена доступа для MVP делается вручную из админки,
        # чтобы не рвать доступ на автомате при спорных возвратах.
        return

    if user is None:
        logger.error(
            "platega %s: user_id=%s not found for transaction_id=%s",
            source, user_id, transaction_id,
        )
        return

    tariff = TARIFFS.get(tariff_key)

    if tariff is None:
        logger.error(
            "platega %s: unknown tariff_key=%s for transaction_id=%s",
            source, tariff_key, transaction_id,
        )
        return

    async with async_session() as session:
        session.add(
            Payment(
                user_id=user_id,
                tariff_key=tariff_key,
                method=method,
                amount=amount,
                days=tariff["days"],
            )
        )
        await session.commit()

    try:
        await _notify_bot.send_message(chat_id, PAYMENT_THANKS_TEXT)
        await send_subscription_by_chat_id(
            _notify_bot,
            chat_id,
            user,
            tariff["days"],
        )
    except Exception:
        # Если здесь упадёт (например, пользователь заблокировал бота),
        # важно не ронять обработку callback'а — Platega ждёт 200 в
        # течение 60 секунд и иначе будет ретраить.
        logger.exception(
            "platega %s: failed to notify chat_id=%s", source, chat_id
        )

    await maybe_reward_referrer(user_id, _notify_bot, amount)

    if source != "webhook":
        logger.info(
            "platega %s: доставил подписку по transaction_id=%s "
            "(вебхук от Platega, судя по всему, не дошёл)",
            source, transaction_id,
        )


@router.post("/webhooks/platega")
async def platega_webhook(request: Request):

    # Platega подписывает запрос теми же двумя заголовками, что и мы
    # используем для авторизации своих запросов к их API.
    if (
        request.headers.get("X-MerchantId") != PLATEGA_MERCHANT_ID
        or request.headers.get("X-Secret") != PLATEGA_SECRET
    ):
        logger.warning("platega webhook: bad X-MerchantId/X-Secret")
        return Response(status_code=401)

    data = await request.json()

    transaction_id = data.get("id")
    status = data.get("status")

    if not transaction_id or not status:
        logger.warning("platega webhook: malformed payload %r", data)
        return Response(status_code=400)

    await process_status_update(transaction_id, status, source="webhook")
    return {"ok": True}
