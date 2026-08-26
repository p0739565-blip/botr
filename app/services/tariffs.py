"""
Тарифы с учётом переопределения цены из админки (app.admin.routes.tariffs).

Базовая структура тарифа (название, срок, флаг триала) остаётся
статической — в app.settings.tariffs.TARIFFS, как и раньше. Меняться
из админки могут только card/stars — через таблицу TariffPrice
(NULL = "не переопределено, взять дефолт из кода").

Используется вместо прямого `from app.settings.tariffs import TARIFFS`
везде, где цена реально влияет на сумму платежа или на то, что видит
покупатель (клавиатура выбора тарифа, создание транзакции). Там, где
нужны только неизменяемые поля (title/days/is_trial — например, в
вебхуке при выдаче подписки по количеству дней), статический словарь
по-прежнему можно импортировать напрямую — так меньше лишних походов
в БД на путях, где цена не участвует.
"""

import copy

from sqlalchemy import select

from app.db import async_session
from app.models import TariffPrice
from app.settings.tariffs import TARIFFS as DEFAULT_TARIFFS


async def get_tariffs() -> dict:
    """Копия TARIFFS с применёнными переопределениями цены из БД.

    Поле "balance" (цена при оплате бонусным балансом) в статическом
    TARIFFS не хранится — по умолчанию равна эффективной card
    (с учётом её же переопределения), если явно не задана отдельная
    balance_price."""

    tariffs = copy.deepcopy(DEFAULT_TARIFFS)

    async with async_session() as session:
        result = await session.execute(select(TariffPrice))
        overrides = {row.tariff_key: row for row in result.scalars().all()}

    for key, tariff in tariffs.items():
        override = overrides.get(key)
        if override is not None:
            if override.card_price is not None:
                tariff["card"] = override.card_price
            if override.stars_price is not None:
                tariff["stars"] = override.stars_price

        # По умолчанию оплата балансом стоит столько же, сколько картой.
        tariff["balance"] = tariff["card"]
        if override is not None and override.balance_price is not None:
            tariff["balance"] = override.balance_price

    return tariffs


async def get_tariff(tariff_key: str) -> dict | None:
    tariffs = await get_tariffs()
    return tariffs.get(tariff_key)


async def set_tariff_override(
    tariff_key: str,
    *,
    card_price: int | None,
    stars_price: int | None,
    balance_price: int | None = None,
) -> None:
    """card_price/stars_price/balance_price = None сбрасывает
    соответствующую цену на дефолт (для card/stars — из кода, для
    balance — на эффективную цену card); число — устанавливает
    переопределение."""

    async with async_session() as session:
        row = await session.get(TariffPrice, tariff_key)
        if row is None:
            row = TariffPrice(tariff_key=tariff_key)
            session.add(row)

        row.card_price = card_price
        row.stars_price = stars_price
        row.balance_price = balance_price

        await session.commit()
