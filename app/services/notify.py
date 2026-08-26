"""
Отправка одиночного уведомления пользователю из процесса админки
(FastAPI/vpnapi.service), а не из основного бот-процесса (vpnbot.service).
Используется там, где действие инициирует администратор (выдача
бонусного баланса и т.п.) и нужно тут же сообщить об этом пользователю
в Telegram, но своего Bot-инстанса под рукой нет — те же процессы уже
делают так же для рассылок (app.services.broadcast) и для колбэка
Platega (app.webhooks.platega).
"""

import logging

from aiogram import Bot

from app.config import BOT_TOKEN

logger = logging.getLogger("notify")


async def notify_user(tg_id: int, text: str, **kwargs) -> bool:
    """Возвращает True, если сообщение доставлено. Никогда не бросает
    исключение наружу — например, пользователь мог заблокировать бота;
    вызывающий код (админ-действие) не должен из-за этого падать
    с ошибкой 500."""

    bot = Bot(token=BOT_TOKEN)
    try:
        await bot.send_message(tg_id, text, **kwargs)
        return True
    except Exception:
        logger.exception("notify_user: не удалось отправить сообщение tg_id=%s", tg_id)
        return False
    finally:
        await bot.session.close()
