import asyncio

from aiogram import Bot, Dispatcher

from app.config import BOT_TOKEN
from app.db import init_models

from app.handlers import help as help_handler
from app.handlers import payment
from app.handlers import referral
from app.handlers import start
from app.handlers import subscription
from app.handlers import support
from app.handlers import trial
from app.handlers import documents



bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

dp.include_router(start.router)
dp.include_router(trial.router)
dp.include_router(subscription.router)
dp.include_router(payment.router)
dp.include_router(referral.router)
dp.include_router(help_handler.router)
dp.include_router(support.router)
dp.include_router(documents.router)


async def main() -> None:
    await init_models()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
