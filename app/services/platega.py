"""
Клиент Platega API (https://docs.platega.io/).

Используем aiohttp, а не httpx — он уже тянется транзитивно через
aiogram, так что новая зависимость в requirements.txt не нужна.

Авторизация — два заголовка на каждый запрос:
X-MerchantId и X-Secret (см. app.config).
"""

import aiohttp

from app.config import PLATEGA_BASE_URL, PLATEGA_MERCHANT_ID, PLATEGA_SECRET

HEADERS = {
    "X-MerchantId": PLATEGA_MERCHANT_ID,
    "X-Secret": PLATEGA_SECRET,
    "Content-Type": "application/json",
}

TIMEOUT = aiohttp.ClientTimeout(total=15)


class PlategaError(RuntimeError):
    """Ошибка при обращении к Platega API (сетевая или ответ != 2xx)."""

    def __init__(self, status: int, body: str):
        self.status = status
        self.body = body
        super().__init__(f"Platega API error {status}: {body}")


async def create_transaction(
    *,
    amount: int,
    currency: str,
    description: str,
    return_url: str,
    failed_url: str,
    payload: str,
    payment_method: int | None = None,
) -> dict:
    """Создаёт транзакцию и возвращает данные для оплаты (см.
    CreateTransactionResponse в доках). Ключевое поле для нас —
    redirect (ссылка на страницу оплаты) и transactionId.

    ID транзакции НЕ передаём — генерируется Platega автоматически."""

    body = {
        "paymentDetails": {
            "amount": amount,
            "currency": currency,
        },
        "description": description,
        "return": return_url,
        "failedUrl": failed_url,
        "payload": payload,
    }

    if payment_method is not None:
        body["paymentMethod"] = payment_method

    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        async with session.post(
            f"{PLATEGA_BASE_URL}/transaction/process",
            json=body,
            headers=HEADERS,
        ) as resp:
            text = await resp.text()

            if resp.status != 200:
                raise PlategaError(resp.status, text)

            return await resp.json()


async def get_transaction_status(transaction_id: str) -> dict:
    """Возвращает TransactionStatusResponse — актуальный статус
    транзакции. Используется как резервная сверка (на случай, если
    callback не дошёл), не как основной механизм."""

    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        async with session.get(
            f"{PLATEGA_BASE_URL}/transaction/{transaction_id}",
            headers=HEADERS,
        ) as resp:
            text = await resp.text()

            if resp.status != 200:
                raise PlategaError(resp.status, text)

            return await resp.json()
