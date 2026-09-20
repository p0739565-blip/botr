from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from app.keyboards.reply import main_menu
from app.services.promo import RedeemResult, redeem_code
from app.services.users import get_or_create_user

router = Router()


class PromoStates(StatesGroup):
    waiting_code = State()


PROMO_REASON_TEXTS = {
    "empty": "Код не может быть пустым. Введите промокод ещё раз или нажмите «Отмена».",
    "not_found": "Такого промокода не существует. Проверьте, всё ли верно введено.",
    "inactive": "Этот промокод сейчас отключён.",
    "expired": "Срок действия этого промокода истёк.",
    "exhausted": "У этого промокода закончились активации.",
    "already_used": "Вы уже активировали этот промокод раньше — повторно его использовать нельзя.",
}


def _result_text(result: RedeemResult) -> str:
    if not result.ok:
        return "❌ " + PROMO_REASON_TEXTS.get(
            result.reason, "Не получилось активировать промокод."
        )

    parts = ["✅ Промокод активирован!"]

    if result.bonus_balance:
        parts.append(
            f"На баланс начислено {result.bonus_balance}₽ "
            f"(текущий баланс: {result.new_balance}₽)."
        )

    if result.discount_percent:
        parts.append(
            f"Скидка {result.discount_percent}% зарезервирована за вами и "
            "автоматически применится к следующей покупке подписки — "
            "любым способом оплаты."
        )

    return "\n\n".join(parts)


@router.message(F.text == "🎟 Промокод")
async def promo_entry(message: Message, state: FSMContext):
    await state.set_state(PromoStates.waiting_code)
    await message.answer(
        "Введите промокод (или нажмите «Отмена», чтобы вернуться в меню):",
    )


@router.message(PromoStates.waiting_code, F.text == "Отмена")
async def promo_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Ок, отменено.", reply_markup=main_menu())


@router.message(PromoStates.waiting_code, F.text)
async def promo_receive_code(message: Message, state: FSMContext):
    user = await get_or_create_user(message.from_user.id, message.from_user.username)

    result = await redeem_code(user.id, message.text)

    # Пустой/неверный код — не выходим из состояния ввода, чтобы можно
    # было сразу попробовать ещё раз, не нажимая кнопку заново.
    if not result.ok and result.reason == "empty":
        await message.answer(_result_text(result))
        return

    await state.clear()
    await message.answer(_result_text(result), reply_markup=main_menu())
