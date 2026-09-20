"""
Фоновая сверка зависших Platega-транзакций.

Это реализация того, на что уже ссылается докстринг
app.webhooks.platega.process_status_update ("...для фоновой сверки
(app.services.platega_reconciliation, вызывается по опросу API, когда
колбэк не дошёл — например, из-за смены адреса туннеля)"), но чего до
сих пор не было в репозитории — отсюда платежи, зависающие в PENDING
навсегда, даже если реально были отменены/подтверждены на стороне
Platega: без этого модуля их статус в нашей БД никто и никогда больше
не спрашивал повторно.

Частая причина, почему колбэк не доходит именно у вас: Callback URL в
настройках Platega указывает на Cloudflare Quick Tunnel
(*.trycloudflare.com) — такой адрес НЕ статичный, он выдаётся заново
при каждом перезапуске cloudflared (перезагрузка VM, падение процесса
и т.п.). Если адрес сменился, а Callback URL в личном кабинете Platega
руками не обновили — все колбэки с этого момента улетают в никуда,
молча, без единой ошибки с обеих сторон. Эта сверка не убирает саму
причину (для этого нужен статичный домен вместо Quick Tunnel — см.
README рядом), но не даёт зависшим из-за неё платежам оставаться
зависшими навсегда: рано или поздно (в течение MAX_AGE) они дойдут до
финального статуса через опрос API вместо колбэка.
"""

import asyncio
import datetime
import logging

from sqlalchemy import select

from app.db import async_session
from app.models import PlategaPayment
from app.services.platega import PlategaError, get_transaction_status
from app.webhooks.platega import process_status_update

logger = logging.getLogger("platega_reconciliation")

RECONCILE_INTERVAL = datetime.timedelta(minutes=5)

# Не проверяем совсем свежие PENDING — пользователь мог ещё физически
# не успеть перейти на страницу оплаты и заплатить.
MIN_AGE = datetime.timedelta(minutes=10)

# Совсем древние зависшие платежи (Platega сама давно "забыла" такую
# транзакцию) сверкой больше не трогаем — закрыть их можно только
# вручную из админки, чтобы не пытаться опрашивать API до бесконечности.
MAX_AGE = datetime.timedelta(days=2)

# Статусы, на которые реагирует process_status_update — если Platega
# вернёт что-то другое (в т.ч. по-прежнему PENDING, или незнакомый
# новый статус) — тихо пропускаем до следующего цикла сверки.
TERMINAL_STATUSES = {"CONFIRMED", "CANCELED", "CHARGEBACKED"}


async def reconcile_once() -> int:
    """Один проход сверки. Возвращает число платежей, для которых
    удалось получить финальный статус. Отдельная функция — чтобы можно
    было запустить разово вручную (например, из `python -m` в shell на
    сервере), не поднимая бесконечный цикл."""

    now = datetime.datetime.now()
    resolved = 0

    async with async_session() as session:
        result = await session.execute(
            select(PlategaPayment).where(
                PlategaPayment.status == "PENDING",
                PlategaPayment.created_at <= now - MIN_AGE,
                PlategaPayment.created_at >= now - MAX_AGE,
            )
        )
        pending = list(result.scalars().all())

    if not pending:
        return 0

    logger.info("reconciliation: проверяю зависших платежей: %d", len(pending))

    for payment in pending:
        try:
            data = await get_transaction_status(payment.transaction_id)
        except PlategaError as e:
            logger.warning(
                "reconciliation: не удалось получить статус transaction_id=%s: %s",
                payment.transaction_id, e,
            )
            continue
        except Exception:
            logger.exception(
                "reconciliation: неожиданная ошибка для transaction_id=%s",
                payment.transaction_id,
            )
            continue

        remote_status = data.get("status")

        if remote_status not in TERMINAL_STATUSES:
            # Всё ещё PENDING на стороне Platega (или новый незнакомый
            # статус — логируем сырой ответ, чтобы не потерять его молча).
            if remote_status not in (None, "PENDING"):
                logger.warning(
                    "reconciliation: незнакомый статус %r для transaction_id=%s: %s",
                    remote_status, payment.transaction_id, data,
                )
            continue

        # process_status_update сам идемпотентен (см. его докстринг) —
        # безопасно вызывать, даже если между нашим SELECT выше и этим
        # моментом колбэк всё же успел дойти и обработаться первым.
        await process_status_update(payment.transaction_id, remote_status, source="reconciliation")
        resolved += 1
        logger.info(
            "reconciliation: transaction_id=%s -> %s",
            payment.transaction_id, remote_status,
        )

    return resolved


async def reconciliation_loop() -> None:
    """Бесконечный цикл — запускается фоновой задачей на старте
    процесса app.api (см. app.api.on_startup). Падение одного прохода
    не останавливает цикл целиком — ошибка логируется, следующий
    проход всё равно случится по расписанию."""

    while True:
        try:
            await reconcile_once()
        except Exception:
            logger.exception("reconciliation: ошибка в цикле сверки")

        await asyncio.sleep(RECONCILE_INTERVAL.total_seconds())


if __name__ == "__main__":
    # Разовый ручной запуск сверки прямо сейчас, без ожидания рестарта
    # процесса и без пятиминутного интервала — удобно, чтобы разово
    # разобраться с уже зависшим платежом немедленно:
    #
    #   cd /opt/vpn-bot && .venv/bin/python -m app.services.platega_reconciliation
    async def _run_once() -> None:
        resolved = await reconcile_once()
        print(f"Обработано зависших платежей: {resolved}")

    asyncio.run(_run_once())

