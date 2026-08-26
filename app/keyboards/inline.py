from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import CHANNEL_USERNAME
from app.services.tariffs import get_tariffs


# ==========================
# Кнопка подписки на канал
# ==========================

def channel_keyboard() -> InlineKeyboardMarkup:

    buttons = []

    if CHANNEL_USERNAME:
        buttons.append([
            InlineKeyboardButton(
                text="📢 Открыть канал",
                url=f"https://t.me/{CHANNEL_USERNAME}",
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="✅ Я подписался",
            callback_data="check_sub",
        )
    ])

    return InlineKeyboardMarkup(
        inline_keyboard=buttons
    )


# ==========================
# Клавиатура выбора способа оплаты
# ==========================

def payment_method_keyboard() -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⭐ Telegram Stars",
                    callback_data="method_stars",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💳 Банковская карта",
                    callback_data="method_card",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📱 СБП (QR-код)",
                    callback_data="method_sbp",
                )
            ],
            [
                InlineKeyboardButton(
                    text="₿ Криптовалюта",
                    callback_data="method_crypto",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💰 Бонусный баланс",
                    callback_data="method_balance",
                )
            ],
        ]
    )


# ==========================
# Клавиатура покупки (список тарифов для выбранного способа оплаты)
# ==========================

def _discount_suffix(tariffs: dict, tariff: dict, field: str) -> str:
    """Считает скидку в % относительно цены тарифа "1m" за тот же месяц,
    чтобы бейдж (-10%/-20%/-40%) всегда соответствовал реальным ценам
    (в т.ч. переопределённым из админки), и не требовал ручной
    синхронизации с процентом отдельно от цены."""

    base_price = tariffs["1m"][field]
    price = tariff[field]

    if not base_price or not price:
        return ""

    months = round(tariff["days"] / 30)
    price_without_discount = base_price * months

    if price_without_discount <= 0:
        return ""

    discount = round((1 - price / price_without_discount) * 100)

    return f" (-{discount}%)" if discount > 0 else ""


async def payment_keyboard(payment_type: str = "stars", balance: int | None = None) -> InlineKeyboardMarkup:

    keyboard = []
    tariffs = await get_tariffs()

    for key, tariff in tariffs.items():

        # Пробный тариф не продаётся
        if tariff.get("is_trial"):
            continue

        if payment_type == "stars":
            price = tariff["stars"]

            if price is None:
                continue

            suffix = f"{price}⭐️{_discount_suffix(tariffs, tariff, 'stars')}"

        elif payment_type == "card":
            price = tariff["card"]

            if price is None:
                continue

            suffix = f"{price}р{_discount_suffix(tariffs, tariff, 'card')}"

        elif payment_type == "sbp":
            # Отдельного поля "sbp" в тарифах нет — те же тарифы/цены,
            # что и для карты (общий шлюз Platega, просто другой метод).
            price = tariff["card"]

            if price is None:
                continue

            suffix = f"{price}р{_discount_suffix(tariffs, tariff, 'card')}"

        elif payment_type == "crypto":
            # Аналогично СБП — те же рублёвые цены, Platega сама
            # показывает точную сумму в криптовалюте на своей странице.
            price = tariff["card"]

            if price is None:
                continue

            suffix = f"{price}р{_discount_suffix(tariffs, tariff, 'card')}"

        elif payment_type == "balance":
            price = tariff["balance"]

            if price is None:
                continue

            suffix = f"{price}р{_discount_suffix(tariffs, tariff, 'card')}"

            # Баланс — единственный способ, где реально важно, хватает
            # ли пользователю денег (остальные методы — внешний шлюз,
            # там платёжеспособность не наша забота). Недоступные по
            # балансу тарифы всё равно показываем, но помечаем и не
            # даём на них нажать — так понятно, куда расти, а не просто
            # пропадает часть тарифной сетки.
            if balance is not None and price > balance:
                keyboard.append([
                    InlineKeyboardButton(
                        text=f"🔒 {tariff['title']} — {suffix} (не хватает)",
                        callback_data="balance_insufficient",
                    )
                ])
                continue

        else:
            continue

        keyboard.append([
            InlineKeyboardButton(
                text=f"{tariff['title']} — {suffix}",
                callback_data=f"buy_{payment_type}_{key}",
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="payment_method_back",
        )
    ])

    return InlineKeyboardMarkup(
        inline_keyboard=keyboard
    )


# ==========================
# Клавиатуры техподдержки
# ==========================

def support_start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="📝 Создать заявку",
                callback_data="support_new_ticket",
            )
        ]]
    )


def support_attachments_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="✅ Отправить заявку",
                callback_data="support_submit_ticket",
            )
        ]]
    )


def support_conversation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="❌ Завершить чат с поддержкой",
                callback_data="support_exit_conversation",
            )
        ]]
    )

# ==========================
# Клавиатура документов
# ==========================

def documents_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📄 Политика конфиденциальности",
                    url="https://telegra.ph/Politika-konfidencialnosti-08-08-87",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📄 Пользовательское соглашение",
                    url="https://telegra.ph/Polzovatelskoe-soglashenie-08-08-51",
                )
            ],
        ]
    )