import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Переменная окружения {name} не задана (см. .env)")
    return value.strip()


def _require_int(name: str) -> int:
    raw = _require(name)
    try:
        return int(raw)
    except ValueError:
        raise RuntimeError(
            f"Переменная окружения {name}={raw!r} должна быть целым числом (см. .env)"
        )


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError:
        raise RuntimeError(
            f"Переменная окружения {name}={raw!r} должна быть целым числом (см. .env)"
        )


# Telegram
BOT_TOKEN = _require("BOT_TOKEN")
CHANNEL_ID = _require_int("CHANNEL_ID")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "").strip().lstrip("@")

# Подписка
SUB_DOMAIN = _require("SUB_DOMAIN").strip().rstrip("/")


# ==========================
# Platega (оплата картой)
# ==========================
# https://docs.platega.io/ — X-MerchantId / X-Secret выдаются
# менеджером Platega и видны в личном кабинете на странице «Настройки».
# В личном кабинете (Настройки → Callback URLs) нужно указать
# {SUB_DOMAIN}/webhooks/platega — иначе бот не узнает об оплате.
PLATEGA_MERCHANT_ID = _require("PLATEGA_MERCHANT_ID")
PLATEGA_SECRET = _require("PLATEGA_SECRET")
PLATEGA_BASE_URL = os.getenv("PLATEGA_BASE_URL", "https://app.platega.io").strip().rstrip("/")

# Числовой код способа оплаты для кнопки "Банковская карта" (см.
# PaymentMethodInt в доках Platega). По умолчанию 11 (карта). Если
# Platega вернёт "No available card cascades" — картный каскад не
# подключен на вашем мерчанте, обратитесь к менеджеру Platega, либо
# временно смените на 2 (SBP QR) через .env.
PLATEGA_CARD_METHOD = _int_env("PLATEGA_CARD_METHOD", 11)

# Числовой код способа оплаты для кнопки "СБП" (оплата по QR-коду
# через Систему быстрых платежей). По умолчанию 2. Уточните у
# менеджера Platega, что СБП-каскад подключен на вашем мерчанте —
# иначе получите ту же ошибку "No available ... cascades", что и с
# картой.
PLATEGA_SBP_METHOD = _int_env("PLATEGA_SBP_METHOD", 2)

# Числовой код способа оплаты для кнопки "Криптовалюта" (см.
# PaymentMethodInt в доках Platega — 13). Как и с картой/СБП, сумма
# передаётся в RUB, Platega сама конвертирует по своему курсу
# (пользователь увидит курс и сумму в криптовалюте на их странице
# оплаты). Каскад может требовать отдельного подключения у менеджера
# Platega — тот же "No available ... cascades", что и с картой.
PLATEGA_CRYPTO_METHOD = _int_env("PLATEGA_CRYPTO_METHOD", 13)


# ==========================
# Локальная база SQLite
# ==========================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_FILE = DATA_DIR / "database.db"
DATABASE_URL = f"sqlite+aiosqlite:///{DB_FILE}"

SUPPORT_MEDIA_DIR = DATA_DIR / "support_media"
SUPPORT_MEDIA_DIR.mkdir(parents=True, exist_ok=True)

BROADCAST_MEDIA_DIR = DATA_DIR / "broadcast_media"
BROADCAST_MEDIA_DIR.mkdir(parents=True, exist_ok=True)

# ==========================
# Админ-панель
# ==========================

# Секрет для подписи сессионных cookie админки. Можно задать в .env
# (ADMIN_SESSION_SECRET=...) — тогда сессии переживут ЛЮБОЙ рестарт
# сервиса. Если не задан — генерируется один раз и сохраняется в файл
# рядом с базой, чтобы не разлогинивать всех при каждом перезапуске
# (но при переносе на новый сервер без переноса этого файла все
# сессии всё равно инвалидируются — это нормально и ожидаемо).
_admin_secret_env = os.getenv("ADMIN_SESSION_SECRET", "").strip()

if _admin_secret_env:
    ADMIN_SESSION_SECRET = _admin_secret_env
else:
    _secret_file = DATA_DIR / "admin_session.key"
    if _secret_file.exists():
        ADMIN_SESSION_SECRET = _secret_file.read_text().strip()
    else:
        import secrets as _secrets

        ADMIN_SESSION_SECRET = _secrets.token_hex(32)
        _secret_file.write_text(ADMIN_SESSION_SECRET)
