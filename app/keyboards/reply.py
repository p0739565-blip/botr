from aiogram.types import KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder


def main_menu():

    kb = ReplyKeyboardBuilder()

    kb.row(
        KeyboardButton(text="🚀 Получить VPN")
    )

    kb.row(
        KeyboardButton(text="💳 Купить подписку"),
        KeyboardButton(text="📱 Моя подписка")
    )

    kb.row(
        KeyboardButton(text="🤝 Реферальная программа")
    )

    kb.row(
        KeyboardButton(text="📖 Инструкция"),
        KeyboardButton(text="🆘 Поддержка")
    )
    kb.row(
        KeyboardButton(text="📚 Документы")
    )

    return kb.as_markup(
        resize_keyboard=True
    )