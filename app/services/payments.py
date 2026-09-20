"""
Сервис формирования счетов.

Telegram Stars собирается локально (build_stars_invoice). Оплата
картой/СБП/криптой уходит во внешний платёжный шлюз Platega
(create_card_payment / create_sbp_payment / create_crypto_payment) —
в отличие от Stars, эта транзакция асинхронна: мы получаем ссылку на
оплату сразу, а факт оплаты приходит позже отдельным вебхуком
(app.api:platega_webhook), поэтому здесь же заводится запись
PlategaPayment для сопоставления вебхука с пользователем и тарифом.
"""

from aiogram.types import LabeledPrice

from app.config import PLATEGA_CARD_METHOD, PLATEGA_CRYPTO_METHOD, PLATEGA_SBP_METHOD, SUB_DOMAIN
from app.db import async_session
from app.models import PlategaPayment, User
from app.services import platega

STARS_CURRENCY = "XTR"


def build_stars_invoice(tariff: dict) -> dict:
    """
    Возвращает параметры для answer_invoice().
    """

    return {
        "title": f"Маквин VPN • {tariff['title']}",
        "description": f"Подписка на {tariff['days']} дней",
        "currency": STARS_CURRENCY,
        "prices": [
            LabeledPrice(
                label=tariff["title"],
                amount=tariff["stars"],
            )
        ],
    }


# =====================================================
# Platega — банковская карта, СБП и криптовалюта
# =====================================================
# Все три способа идут через один и тот же шлюз и один и тот же
# create_transaction(), различается только числовой payment_method и
# то, что мы пишем в PlategaPayment.method (нужно вебхуку, чтобы
# записать правильный Payment.method). Тарифы (цены) общие —
# используем то же поле tariff["card"] (сумма в RUB), отдельных полей
# "sbp"/"crypto" в TARIFFS нет и не требуется: Platega сама
# конвертирует RUB в криптовалюту по своему курсу и показывает точную
# сумму в крипте на странице оплаты.

async def _create_platega_payment(
    *,
    user: User,
    chat_id: int,
    tariff_key: str,
    tariff: dict,
    payment_method: int,
    method_label: str,
) -> str:
    """
    Создаёт транзакцию в Platega и локальную запись PlategaPayment
    (status=PENDING), возвращает ссылку на страницу оплаты (для СБП
    Platega показывает на этой же странице QR-код для сканирования,
    для крипты — адрес/сумму в выбранной криптовалюте).

    Подтверждение оплаты придёт отдельно, через POST на
    /webhooks/platega — там и выдаётся подписка.
    """

    amount = tariff["card"]

    response = await platega.create_transaction(
        amount=amount,
        currency="RUB",
        description=f"Маквин VPN — {tariff['title']}",
        return_url=f"{SUB_DOMAIN}/payments/platega/return",
        failed_url=f"{SUB_DOMAIN}/payments/platega/failed",
        payload=f"user:{user.tg_id}:tariff:{tariff_key}",
        payment_method=payment_method,
    )

    transaction_id = response["transactionId"]

    # v1 отдаёт ссылку в поле "redirect", более новый v2-эндпоинт —
    # в "url". Проверяем оба, чтобы не сломаться при смене API.
    redirect_url = response.get("redirect") or response.get("url")

    if not redirect_url:
        raise platega.PlategaError(200, f"Нет ссылки на оплату в ответе: {response}")

    async with async_session() as session:
        session.add(
            PlategaPayment(
                user_id=user.id,
                chat_id=chat_id,
                transaction_id=transaction_id,
                tariff_key=tariff_key,
                method=method_label,
                amount=amount,
                currency="RUB",
                status="PENDING",
            )
        )
        await session.commit()

    return redirect_url


async def create_card_payment(
    user: User,
    chat_id: int,
    tariff_key: str,
    tariff: dict,
) -> str:
    return await _create_platega_payment(
        user=user,
        chat_id=chat_id,
        tariff_key=tariff_key,
        tariff=tariff,
        payment_method=PLATEGA_CARD_METHOD,
        method_label="card",
    )


async def create_sbp_payment(
    user: User,
    chat_id: int,
    tariff_key: str,
    tariff: dict,
) -> str:
    return await _create_platega_payment(
        user=user,
        chat_id=chat_id,
        tariff_key=tariff_key,
        tariff=tariff,
        payment_method=PLATEGA_SBP_METHOD,
        method_label="sbp",
    )


async def create_crypto_payment(
    user: User,
    chat_id: int,
    tariff_key: str,
    tariff: dict,
) -> str:
    return await _create_platega_payment(
        user=user,
        chat_id=chat_id,
        tariff_key=tariff_key,
        tariff=tariff,
        payment_method=PLATEGA_CRYPTO_METHOD,
        method_label="crypto",
    )