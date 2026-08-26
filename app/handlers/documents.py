from aiogram import F, Router
from aiogram.types import Message

from app.keyboards.inline import documents_keyboard

router = Router()


@router.message(F.text == "📚 Документы")
async def documents(message: Message):
    await message.answer(
        "📚 Документы\n\n"
        "Выберите нужный документ:",
        reply_markup=documents_keyboard()
    )