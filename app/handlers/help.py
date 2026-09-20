from aiogram import F, Router
from aiogram.types import Message

from app.texts.messages import INSTRUCTION_TEXT

router = Router()


@router.message(F.text == "📖 Инструкция")
async def instruction(message: Message):

    await message.answer(INSTRUCTION_TEXT)
