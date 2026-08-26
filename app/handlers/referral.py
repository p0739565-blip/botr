from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.services.referral import (
    build_referral_link,
    get_bot_username,
    get_referral_stats,
    set_referral_reward_mode,
)
from app.services.settings import get_setting_int
from app.services.users import get_or_create_user

router = Router()


def _referral_keyboard(current_mode: str) -> InlineKeyboardMarkup:
    days_mark = "✅ " if current_mode == "days" else ""
    balance_mark = "✅ " if current_mode == "balance" else ""

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{days_mark}📅 Дни к подписке",
                    callback_data="ref_mode_days",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"{balance_mark}💰 Бонусный баланс",
                    callback_data="ref_mode_balance",
                )
            ],
        ]
    )


async def _build_referral_text(bot: Bot, user_id: int, tg_id: int) -> tuple[str, InlineKeyboardMarkup]:
    bot_username = await get_bot_username(bot)
    link = build_referral_link(bot_username, tg_id)

    bonus_days = await get_setting_int("referral_bonus_days")
    bonus_percent = await get_setting_int("referral_bonus_percent")
    stats = await get_referral_stats(user_id)

    mode_label = "дни к подписке" if stats["reward_mode"] == "days" else "бонусный баланс"

    text = (
        "🤝 Реферальная программа\n\n"
        "Приглашайте друзей — за каждого, кто оформит платную подписку "
        "по вашей ссылке, вы получаете награду. Выберите ниже, какую именно:\n\n"
        f"📅 Дни к подписке — +{bonus_days} дн. за оплату реферала\n"
        f"💰 Бонусный баланс — {bonus_percent}% от суммы его первой оплаты\n\n"
        f"Сейчас выбрано: *{mode_label}*\n\n"
        f"Ваша ссылка:\n`{link}`\n\n"
        f"👥 Всего приглашено: {stats['total_invited']}\n"
        f"💰 Из них оплатили: {stats['paid_invited']}\n"
        f"🎁 Начислено дней: {stats['total_bonus_days']}\n"
        f"💵 Начислено на баланс: {stats['total_bonus_balance']}₽\n"
        f"💳 Текущий баланс: {stats['balance']}₽"
    )

    return text, _referral_keyboard(stats["reward_mode"])


@router.message(F.text == "🤝 Реферальная программа")
async def referral_program(message: Message, bot: Bot):
    user = await get_or_create_user(message.from_user.id, message.from_user.username)

    text, keyboard = await _build_referral_text(bot, user.id, user.tg_id)

    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard)


@router.callback_query(F.data.in_({"ref_mode_days", "ref_mode_balance"}))
async def switch_reward_mode(callback: CallbackQuery, bot: Bot):
    mode = "days" if callback.data == "ref_mode_days" else "balance"

    user = await get_or_create_user(callback.from_user.id, callback.from_user.username)
    await set_referral_reward_mode(user.id, mode)

    await callback.answer("Режим награды обновлён ✅")

    text, keyboard = await _build_referral_text(bot, user.id, user.tg_id)
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
