"""
Промокоды: активация пользователем, применение скидки к ценам тарифов,
статистика для админки.

Два независимых эффекта, код может иметь один или оба сразу:
- discount_percent — скидка на следующую покупку (см. get_effective_tariffs)
- bonus_balance — начисляется на баланс сразу при активации

Один пользователь может активировать один и тот же код только один раз
(UniqueConstraint на PromoRedemption) — второй ввод того же кода просто
отклоняется с понятной причиной, не как ошибка.
"""

import dataclasses
import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.db import async_session
from app.models import PromoCode, PromoRedemption, User
from app.services.tariffs import get_tariffs


@dataclasses.dataclass
class RedeemResult:
    ok: bool
    reason: str | None = None  # причина отказа, для сообщения пользователю
    bonus_balance: int | None = None  # сколько реально начислено (если начислено)
    discount_percent: int | None = None  # какая скидка зарезервирована (если да)
    new_balance: int | None = None


async def redeem_code(user_id: int, raw_code: str) -> RedeemResult:
    """Активирует промокод для пользователя. Атомарно проверяет все
    условия и применяет эффекты в одной транзакции — гонка "два
    одновременных ввода одного кода в последний свободный слот"
    закрыта тем, что UniqueConstraint и bump activations_count/
    max_activations проверяются внутри одной сессии с одним commit."""

    code = raw_code.strip().upper()

    if not code:
        return RedeemResult(ok=False, reason="empty")

    async with async_session() as session:
        result = await session.execute(
            select(PromoCode).where(PromoCode.code == code)
        )
        promo = result.scalar_one_or_none()

        if promo is None:
            return RedeemResult(ok=False, reason="not_found")

        if not promo.is_active:
            return RedeemResult(ok=False, reason="inactive")

        if promo.is_expired:
            return RedeemResult(ok=False, reason="expired")

        if promo.is_exhausted:
            return RedeemResult(ok=False, reason="exhausted")

        already = await session.execute(
            select(PromoRedemption).where(
                PromoRedemption.promo_code_id == promo.id,
                PromoRedemption.user_id == user_id,
            )
        )
        if already.scalar_one_or_none() is not None:
            return RedeemResult(ok=False, reason="already_used")

        user = await session.get(User, user_id)
        if user is None:
            return RedeemResult(ok=False, reason="not_found")

        granted_balance = None
        if promo.bonus_balance:
            user.balance += promo.bonus_balance
            granted_balance = promo.bonus_balance

        reserved_discount = promo.discount_percent if promo.discount_percent else None

        session.add(
            PromoRedemption(
                promo_code_id=promo.id,
                user_id=user_id,
                bonus_balance_granted=granted_balance,
                discount_percent_reserved=reserved_discount,
            )
        )
        promo.activations_count += 1

        try:
            await session.commit()
        except IntegrityError:
            # Гонка: тот же пользователь активировал этот же код почти
            # одновременно вторым запросом (двойной тап по кнопке и
            # т.п.) — UniqueConstraint поймал то, что проверка "already"
            # выше не успела увидеть. Не ошибка сервера, а штатный
            # повторный ввод.
            await session.rollback()
            return RedeemResult(ok=False, reason="already_used")

        new_balance = user.balance

    return RedeemResult(
        ok=True,
        bonus_balance=granted_balance,
        discount_percent=reserved_discount,
        new_balance=new_balance,
    )


async def get_active_discount(user_id: int) -> int | None:
    """Скидка (%), зарезервированная за пользователем и ещё не
    применённая ни к одной покупке. Если у пользователя активировано
    несколько скидочных кодов подряд — действует самая свежая
    неиспользованная, остальные просто ждут своей очереди (списание
    всегда гасит ровно одну, самую раннюю неиспользованную — см.
    consume_discount)."""

    async with async_session() as session:
        result = await session.execute(
            select(PromoRedemption.discount_percent_reserved)
            .where(
                PromoRedemption.user_id == user_id,
                PromoRedemption.discount_percent_reserved.is_not(None),
                PromoRedemption.discount_used_at.is_(None),
            )
            .order_by(PromoRedemption.activated_at.asc())
            .limit(1)
        )
        row = result.first()
        return row[0] if row else None


async def consume_discount(user_id: int) -> None:
    """Гасит самую раннюю неиспользованную зарезервированную скидку
    пользователя — вызывается один раз сразу после ЛЮБОЙ успешно
    оплаченной покупки подписки (Stars/карта/СБП/крипта/баланс), чтобы
    скидка не применилась повторно к следующей покупке. Если активной
    скидки нет — тихо ничего не делает (безопасно вызывать всегда,
    даже если пользователь ничего не активировал)."""

    async with async_session() as session:
        result = await session.execute(
            select(PromoRedemption)
            .where(
                PromoRedemption.user_id == user_id,
                PromoRedemption.discount_percent_reserved.is_not(None),
                PromoRedemption.discount_used_at.is_(None),
            )
            .order_by(PromoRedemption.activated_at.asc())
            .limit(1)
        )
        redemption = result.scalar_one_or_none()
        if redemption is None:
            return

        redemption.discount_used_at = datetime.datetime.now()
        await session.commit()


def _apply_discount(tariff: dict, discount_percent: int) -> dict:
    """Возвращает копию тарифа с уменьшенными card/stars/balance —
    trial (card=None) не трогаем, там скидывать нечего."""

    discounted = dict(tariff)
    for field in ("card", "stars", "balance"):
        price = discounted.get(field)
        if price:
            discounted[field] = max(1, round(price * (100 - discount_percent) / 100))
    return discounted


async def get_effective_tariffs(user_id: int) -> dict:
    """get_tariffs() с применённой промо-скидкой пользователя (если
    она у него сейчас есть). Использовать везде, где цена показывается
    пользователю или участвует в создании платежа — вместо прямого
    get_tariffs()."""

    tariffs = await get_tariffs()

    discount = await get_active_discount(user_id)
    if not discount:
        return tariffs

    return {
        key: (_apply_discount(t, discount) if not t.get("is_trial") else t)
        for key, t in tariffs.items()
    }


async def get_effective_tariff(tariff_key: str, user_id: int) -> dict | None:
    tariffs = await get_effective_tariffs(user_id)
    return tariffs.get(tariff_key)


# =====================================================
# Для админки
# =====================================================

async def list_promo_codes() -> list[PromoCode]:
    async with async_session() as session:
        result = await session.execute(
            select(PromoCode).order_by(PromoCode.created_at.desc())
        )
        return list(result.scalars().all())


async def get_promo_code(promo_id: int) -> PromoCode | None:
    async with async_session() as session:
        return await session.get(PromoCode, promo_id)


async def get_promo_redemptions(promo_id: int) -> list[PromoRedemption]:
    """Полный список активаций конкретного кода — кто и когда, для
    детальной страницы/списка в админке."""

    async with async_session() as session:
        result = await session.execute(
            select(PromoRedemption)
            .options(selectinload(PromoRedemption.user))
            .where(PromoRedemption.promo_code_id == promo_id)
            .order_by(PromoRedemption.activated_at.desc())
        )
        return list(result.scalars().all())
