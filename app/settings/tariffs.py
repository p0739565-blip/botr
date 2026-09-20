"""
Единый список тарифов.

Каждый тариф содержит:
- title      — название для пользователя
- days       — срок действия подписки
- stars      — стоимость в Telegram Stars
- card       — стоимость при оплате картой/СБП/криптой (общий рублёвый
               шлюз Platega — все три метода используют это поле, см.
               app.services.payments)
- is_trial   — является ли тариф пробным

Цена при оплате бонусным балансом ("balance") здесь НЕ хранится статически —
по умолчанию равна card, но может быть переопределена отдельно через
админку (/admin/tariffs, TariffPrice.balance_price), см.
app.services.tariffs.get_tariffs().
"""

TARIFFS = {
    "trial": {
        "title": "🎁 Пробный период",
        "days": 3,
        "stars": 0,
        "card": None,
        "is_trial": True,
    },

    "1m": {
        "title": "📅1 месяц",
        "days": 30,
        "stars": 50,
        "card": 50,
    },

    "3m": {
        "title": "📅3 месяца",
        "days": 90,
        "stars": 135,
        "card": 135,
    },

    "6m": {
        "title": "📅6 месяцев",
        "days": 180,
        "stars": 240,
        "card": 240,
    },

    "12m": {
        "title": "📅12 месяцев",
        "days": 365,
        "stars": 360,
        "card": 360,
    },
}
