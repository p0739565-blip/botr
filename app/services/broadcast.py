import asyncio
import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.models import Broadcast, BroadcastAudience, BroadcastStatus
from app.config import BOT_TOKEN, BROADCAST_MEDIA_DIR
from app.db import async_session
from app.models import Payment, Subscription, User

# Пауза между отправками одному за другим адресату. Telegram официально
# не даёт жёсткую цифру для разных чатов, но ~20 сообщений/сек
# (0.05с) — общепринятый безопасный ориентир, оставляющий запас от
# лимита 30/сек на другие нужды бота (ответы в поддержку и т.п.),
# которые могут идти параллельно из другого процесса.
SEND_INTERVAL_SECONDS = 0.05

# Раз в сколько обработанных получателей коммитим прогресс в БД — не на
# каждое сообщение (лишняя нагрузка на sqlite при большой аудитории), но
# и не только в конце (иначе прогресс на странице не двигался бы вживую).
PROGRESS_COMMIT_EVERY = 20


def _build_audience_stmt(broadcast: Broadcast):
    """Собирает SQL-запрос получателей по сохранённым в Broadcast
    настройкам. Один и тот же запрос используется и для подсчёта
    аудитории при сохранении черновика, и для реальной отправки —
    так превью и факт рассылки никогда не разъезжаются."""

    now = datetime.datetime.now()
    stmt = select(User)

    if broadcast.audience == BroadcastAudience.ACTIVE_SUBSCRIPTION:
        active_subq = select(Subscription.user_id).where(
            Subscription.is_active.is_(True), Subscription.expiry > now
        )
        stmt = stmt.where(User.id.in_(active_subq))
    elif broadcast.audience == BroadcastAudience.NO_ACTIVE_SUBSCRIPTION:
        active_subq = select(Subscription.user_id).where(
            Subscription.is_active.is_(True), Subscription.expiry > now
        )
        stmt = stmt.where(User.id.not_in(active_subq))
    elif broadcast.audience == BroadcastAudience.NEVER_SUBSCRIBED:
        ever_subq = select(Subscription.user_id)
        stmt = stmt.where(User.id.not_in(ever_subq))
    elif broadcast.audience == BroadcastAudience.PAYING:
        paid_subq = select(Payment.user_id)
        stmt = stmt.where(User.id.in_(paid_subq))
    # BroadcastAudience.ALL — без доп.условия

    if broadcast.tariff_filter:
        tariff_subq = select(Payment.user_id).where(
            Payment.tariff_key == broadcast.tariff_filter
        )
        stmt = stmt.where(User.id.in_(tariff_subq))

    if broadcast.registered_from:
        stmt = stmt.where(User.created_at >= broadcast.registered_from)
    if broadcast.registered_to:
        stmt = stmt.where(User.created_at <= broadcast.registered_to)

    return stmt.order_by(User.id)


async def count_audience(session: AsyncSession, broadcast: Broadcast) -> int:
    stmt = _build_audience_stmt(broadcast)
    result = await session.execute(stmt)
    return len(result.scalars().all())


async def get_audience_tg_ids(session: AsyncSession, broadcast: Broadcast) -> list[int]:
    stmt = _build_audience_stmt(broadcast).with_only_columns(User.tg_id)
    result = await session.execute(stmt)
    return [row[0] for row in result.all()]


def _build_keyboard(broadcast: Broadcast) -> InlineKeyboardMarkup | None:
    if not (broadcast.button_text and broadcast.button_url):
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=broadcast.button_text, url=broadcast.button_url)]
        ]
    )


async def _send_one(bot: Bot, chat_id: int, broadcast: Broadcast) -> bool:
    """Отправляет одно сообщение. Возвращает True при успехе. Ловит
    ожидаемые "не наша вина" ошибки (юзер заблокировал бота, чат не
    найден и т.п.) как обычный неуспех — они не должны прерывать всю
    рассылку остальным."""

    keyboard = _build_keyboard(broadcast)

    try:
        if broadcast.photo_path:
            photo = FSInputFile(BROADCAST_MEDIA_DIR / broadcast.photo_path)
            await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=broadcast.text,
                parse_mode=broadcast.parse_mode,
                reply_markup=keyboard,
            )
        else:
            await bot.send_message(
                chat_id=chat_id,
                text=broadcast.text,
                parse_mode=broadcast.parse_mode,
                reply_markup=keyboard,
            )
        return True
    except TelegramRetryAfter as e:
        # Telegram сам просит подождать — уважаем именно эту паузу и
        # пробуем этого же получателя ещё раз один раз, не теряя его.
        await asyncio.sleep(e.retry_after)
        try:
            return await _send_one(bot, chat_id, broadcast)
        except Exception:
            return False
    except TelegramForbiddenError:
        # Пользователь заблокировал бота — ожидаемо, не считаем сбоем
        # инфраструктуры, просто отмечаем как недоставленное.
        return False
    except Exception:
        return False


async def send_test_message(chat_id: int, broadcast: Broadcast) -> bool:
    """Разовая тестовая отправка одному конкретному tg_id — до запуска
    рассылки на всю аудиторию, проверить как выглядит сообщение."""

    bot = Bot(token=BOT_TOKEN)
    try:
        return await _send_one(bot, chat_id, broadcast)
    finally:
        await bot.session.close()


async def run_broadcast(broadcast_id: int) -> None:
    """Фоновая задача: проходит по всей аудитории с троттлингом и
    периодически сохраняет прогресс. Рассчитана на запуск через
    asyncio.create_task — вызывающий роут не ждёт её завершения."""

    async with async_session() as session:
        broadcast = await session.get(Broadcast, broadcast_id)
        if broadcast is None or broadcast.status != BroadcastStatus.DRAFT:
            return

        tg_ids = await get_audience_tg_ids(session, broadcast)

        broadcast.status = BroadcastStatus.SENDING
        broadcast.started_at = datetime.datetime.now()
        broadcast.total_recipients = len(tg_ids)
        await session.commit()

    bot = Bot(token=BOT_TOKEN)
    sent = 0
    failed = 0

    try:
        for i, tg_id in enumerate(tg_ids, start=1):
            ok = await _send_one(bot, tg_id, broadcast)
            if ok:
                sent += 1
            else:
                failed += 1

            if i % PROGRESS_COMMIT_EVERY == 0 or i == len(tg_ids):
                async with async_session() as session:
                    fresh = await session.get(Broadcast, broadcast_id)
                    if fresh is not None:
                        fresh.sent_count = sent
                        fresh.failed_count = failed
                        await session.commit()

            await asyncio.sleep(SEND_INTERVAL_SECONDS)
    finally:
        await bot.session.close()

    async with async_session() as session:
        fresh = await session.get(Broadcast, broadcast_id)
        if fresh is not None:
            fresh.sent_count = sent
            fresh.failed_count = failed
            fresh.status = BroadcastStatus.COMPLETED
            fresh.finished_at = datetime.datetime.now()
            await session.commit()
