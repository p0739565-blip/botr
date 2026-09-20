"""
Реферальная программа.

Механика: у каждого пользователя есть персональная ссылка вида
t.me/<bot>?start=ref_<его tg_id>. Новый пользователь, пришедший по
такой ссылке, привязывается к пригласившему (User.referred_by_id) при
первом /start.

БОНУС начисляется не за сам переход по ссылке, а за КАЖДУЮ успешную
ОПЛАТУ приглашённого — оплата картой, СБП, криптой или Telegram Stars
(то есть реальными деньгами) даёт пригласившему вознаграждение каждый
раз, а не только один раз при первой покупке.

Оплата БОНУСНЫМ БАЛАНСОМ реферала в награду НЕ засчитывается ни разу —
при такой оплате мы не получаем реальных денег (баланс — это либо
ранее уже выданный кем-то бонус, либо подарок от администратора), так
что начислять за это ещё один бонус пригласившему было бы начислением
денег из ниоткуда. См. app.handlers.payment.buy_balance — оплата с
баланса сознательно НЕ вызывает maybe_reward_referrer.

Два режима награды, каждый пользователь выбирает свой (см.
User.referral_reward_mode, переключается через set_referral_reward_mode):

- "days"    — продление ПОДПИСКИ пригласившего на N дней (фиксировано,
              настройка referral_bonus_days в админке) за КАЖДУЮ
              оплату приглашённого.
- "balance" — начисление на БОНУСНЫЙ БАЛАНС пригласившего X% от суммы
              КАЖДОЙ оплаты приглашённого (настройка
              referral_bonus_percent в админке). Процент берётся от
              рублёвого эквивалента тарифа (tariff["card"]) независимо
              от того, чем реально платил приглашённый (в том числе
              Stars/крипта) — так сумма бонуса не зависит от курса и
              одинаково считается для любого способа оплаты.

Защита от двойного начисления за ОДНУ и ту же оплату — не через
глобальный флаг "уже награждён" (это раньше делало награду одноразовой
раз и навсегда — было исправлено), а через естественную идемпотентность
самого места вызова:

- app.webhooks.platega.process_status_update сам не даёт себя
  выполнить дважды для одной транзакции (ранний возврат, если статус
  уже терминальный) — и вебхук, и фоновая сверка используют одну и ту
  же функцию, так что гонки между ними не создают двойного вызова
  maybe_reward_referrer.
- Успешная оплата Stars (successful_payment) — одноразовое событие от
  Telegram на один инвойс, дублей не бывает.

Режим награды фиксируется в ReferralReward.reward_type НА МОМЕНТ
начисления — последующее переключение режима пригласившим не меняет
историю уже начисленных бонусов.
"""

import logging

from aiogram import Bot
from sqlalchemy import func, select

from app.db import async_session
from app.models import ReferralReward, User
from app.services.settings import get_setting_int
from app.services.subscription import issue_subscription

logger = logging.getLogger("referral")

VALID_REWARD_MODES = {"days", "balance"}

# Кэшируем username бота в процессе — он не меняется на лету, а
# get_me() дёргать на каждое построение ссылки незачем.
_bot_username_cache: str | None = None


async def get_bot_username(bot: Bot) -> str:
    global _bot_username_cache
    if _bot_username_cache is None:
        me = await bot.get_me()
        _bot_username_cache = me.username
    return _bot_username_cache


def build_referral_link(bot_username: str, tg_id: int) -> str:
    return f"https://t.me/{bot_username}?start=ref_{tg_id}"


def parse_referral_payload(start_text: str | None) -> int | None:
    """start_text — полный текст команды (например "/start ref_12345").
    Возвращает tg_id пригласившего или None, если ссылка не реферальная
    (обычный /start без параметра, битый payload и т.п.)."""

    if not start_text:
        return None

    parts = start_text.split(maxsplit=1)
    if len(parts) < 2:
        return None

    payload = parts[1].strip()
    if not payload.startswith("ref_"):
        return None

    raw_id = payload.removeprefix("ref_")
    if not raw_id.isdigit():
        return None

    return int(raw_id)


async def register_referral(new_user: User, referrer_tg_id: int | None, bot: Bot) -> None:
    """Привязывает пригласившего к новому пользователю, если он ещё ни
    к кому не привязан, и сразу уведомляет пригласившего о новом
    реферале (это отдельное уведомление от бонуса за оплату — тот
    придёт позже, из maybe_reward_referrer, только если реферал
    реально оплатит подписку).

    Безопасно вызывать на каждый /start — если referred_by_id уже
    проставлен (в том числе не по реферальной ссылке, а просто раньше),
    ничего не меняет и не уведомляет повторно."""

    if referrer_tg_id is None or referrer_tg_id == new_user.tg_id:
        return

    async with async_session() as session:
        db_user = await session.get(User, new_user.id)
        if db_user is None or db_user.referred_by_id is not None:
            return

        referrer_result = await session.execute(
            select(User).where(User.tg_id == referrer_tg_id)
        )
        referrer = referrer_result.scalar_one_or_none()
        if referrer is None:
            return

        db_user.referred_by_id = referrer.id
        await session.commit()

        logger.info(
            "referral: user tg_id=%s привязан к пригласившему tg_id=%s",
            new_user.tg_id, referrer_tg_id,
        )

    who = f"@{new_user.username}" if new_user.username else f"id{new_user.tg_id}"
    await _notify_referrer(
        bot, referrer_tg_id,
        f"👋 По вашей реферальной ссылке зарегистрировался новый пользователь ({who}).\n"
        f"Как только он оформит платную подписку, вам придёт бонус.",
    )


async def set_referral_reward_mode(user_id: int, mode: str) -> None:
    """Пользователь сам выбирает, в каком виде получать награду за
    СВОИХ будущих приглашённых. Не влияет на уже начисленные бонусы —
    те хранят режим на момент начисления в ReferralReward.reward_type."""

    if mode not in VALID_REWARD_MODES:
        raise ValueError(f"Неизвестный режим награды: {mode!r}")

    async with async_session() as session:
        user = await session.get(User, user_id)
        if user is None:
            return
        user.referral_reward_mode = mode
        await session.commit()


async def maybe_reward_referrer(
    user_id: int, bot: Bot, payment_amount_rub: int
) -> None:
    """Вызывается сразу после того, как у пользователя (user_id — id
    в нашей БД, не tg_id) зафиксирован факт успешной оплаты — из
    app.webhooks.platega.process_status_update (карта/СБП/крипта,
    включая путь через фоновую сверку) и из
    app.handlers.payment.successful_payment (Stars).

    payment_amount_rub — рублёвый эквивалент оплаченного тарифа
    (tariff["card"]), используется только для режима "balance"; для
    режима "days" сумма оплаты не участвует в расчёте бонуса.

    Вызывается на КАЖДУЮ оплату реальными деньгами (не только на
    первую) — см. докстринг модуля. НЕ вызывать для оплаты бонусным
    балансом."""

    async with async_session() as session:
        user = await session.get(User, user_id)
        if user is None or user.referred_by_id is None:
            return

        referrer = await session.get(User, user.referred_by_id)
        if referrer is None:
            return

        referrer_id = referrer.id
        referrer_tg_id = referrer.tg_id
        reward_mode = referrer.referral_reward_mode

    if reward_mode == "balance":
        await _reward_with_balance(referrer_id, referrer_tg_id, user_id, payment_amount_rub, bot)
    else:
        await _reward_with_days(referrer_id, referrer_tg_id, user_id, bot)


async def _reward_with_days(
    referrer_id: int, referrer_tg_id: int, referred_user_id: int, bot: Bot
) -> None:
    bonus_days = await get_setting_int("referral_bonus_days")
    if bonus_days <= 0:
        return

    async with async_session() as session:
        referrer_fresh = await session.get(User, referrer_id)
        if referrer_fresh is None:
            return

    await issue_subscription(referrer_fresh, bonus_days)

    async with async_session() as session:
        session.add(
            ReferralReward(
                referrer_id=referrer_id,
                referred_user_id=referred_user_id,
                reward_type="days",
                bonus_days=bonus_days,
            )
        )
        await session.commit()

    await _notify_referrer(
        bot, referrer_tg_id,
        f"🎉 Ваш друг оформил платную подписку по вашей реферальной "
        f"ссылке!\nВам начислено +{bonus_days} дн. к подписке.",
    )


async def _reward_with_balance(
    referrer_id: int,
    referrer_tg_id: int,
    referred_user_id: int,
    payment_amount_rub: int,
    bot: Bot,
) -> None:
    bonus_percent = await get_setting_int("referral_bonus_percent")
    if bonus_percent <= 0 or payment_amount_rub <= 0:
        return

    bonus_amount = round(payment_amount_rub * bonus_percent / 100)
    if bonus_amount <= 0:
        return

    async with async_session() as session:
        referrer_fresh = await session.get(User, referrer_id)
        if referrer_fresh is None:
            return
        referrer_fresh.balance += bonus_amount
        session.add(
            ReferralReward(
                referrer_id=referrer_id,
                referred_user_id=referred_user_id,
                reward_type="balance",
                bonus_balance=bonus_amount,
            )
        )
        await session.commit()

    await _notify_referrer(
        bot, referrer_tg_id,
        f"🎉 Ваш друг оформил платную подписку по вашей реферальной "
        f"ссылке!\nВам начислено +{bonus_amount}₽ на бонусный баланс.",
    )


async def _notify_referrer(bot: Bot, referrer_tg_id: int, text: str) -> None:
    try:
        await bot.send_message(referrer_tg_id, text)
    except Exception:
        # Пригласивший мог заблокировать бота — бонус уже начислен и
        # это не должно ронять обработку платежа.
        logger.exception(
            "referral: не удалось уведомить пригласившего tg_id=%s", referrer_tg_id
        )


async def get_referral_stats(user_id: int) -> dict:
    """Статистика для самого пользователя (раздел «Реферальная
    программа» в боте)."""

    async with async_session() as session:
        total_invited = (
            await session.execute(
                select(func.count(User.id)).where(User.referred_by_id == user_id)
            )
        ).scalar_one()

        # Уникальные рефералы, которые хоть раз оплатили (реальными
        # деньгами) — считаем по логу начислений, а не по снятому
        # одноразовому флагу User.referral_reward_given: теперь один
        # реферал может принести несколько начислений (за каждую свою
        # оплату), а не только одно.
        paid_invited = (
            await session.execute(
                select(func.count(func.distinct(ReferralReward.referred_user_id))).where(
                    ReferralReward.referrer_id == user_id
                )
            )
        ).scalar_one()

        total_bonus_days = (
            await session.execute(
                select(func.coalesce(func.sum(ReferralReward.bonus_days), 0)).where(
                    ReferralReward.referrer_id == user_id,
                    ReferralReward.reward_type == "days",
                )
            )
        ).scalar_one()

        total_bonus_balance = (
            await session.execute(
                select(func.coalesce(func.sum(ReferralReward.bonus_balance), 0)).where(
                    ReferralReward.referrer_id == user_id,
                    ReferralReward.reward_type == "balance",
                )
            )
        ).scalar_one()

        current_user = await session.get(User, user_id)
        current_mode = current_user.referral_reward_mode if current_user else "days"
        current_balance = current_user.balance if current_user else 0

    return {
        "total_invited": total_invited,
        "paid_invited": paid_invited,
        "total_bonus_days": total_bonus_days,
        "total_bonus_balance": total_bonus_balance,
        "reward_mode": current_mode,
        "balance": current_balance,
    }
