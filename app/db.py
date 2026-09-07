from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def _ensure_column(conn, table: str, column: str, ddl_type: str) -> None:
    """Точечная замена Alembic-миграций для одного добавленного поля:
    SQLite (как и create_all()) не умеет сам добавлять недостающие
    колонки в уже существующую таблицу — create_all() создаёт только
    целиком отсутствующие таблицы. Проверяем через PRAGMA и добавляем
    колонку вручную, если её ещё нет (на свежей БД она уже будет —
    create_all() создал таблицу сразу по актуальной модели, и ALTER
    здесь просто ничего не найдёт и не сделает)."""
    result = await conn.execute(text(f"PRAGMA table_info({table})"))
    existing_columns = {row[1] for row in result.fetchall()}
    if column not in existing_columns:
        await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))


async def init_models() -> None:
    """Создаёт таблицы, если их ещё нет. Для MVP вместо Alembic-миграций.

    Ленивые импорты здесь — намеренно: некоторые таблицы (например,
    support_messages) ссылаются через ForeignKey на таблицы админки
    (admin_users), а процесс бота (app/bot.py) никогда не импортирует
    app.admin.* напрямую. Без явной регистрации обеих групп моделей
    здесь create_all() упадёт с NoReferencedTableError именно в
    бот-процессе (в API-процессе всё работало бы и без этого, т.к.
    app.admin.router и так их импортирует)."""
    from app import models as _models  # noqa: F401
    from app.admin import models as _admin_models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Реферальная программа: поля добавлены в существующую таблицу
        # users уже после того, как она могла быть создана на старых
        # установках — create_all() их сам не добавит.
        await _ensure_column(conn, "users", "referred_by_id", "INTEGER")
        await _ensure_column(
            conn, "users", "referral_reward_given", "BOOLEAN DEFAULT 0 NOT NULL"
        )

        # Выбор режима бонуса (дни/баланс) и сам бонусный баланс —
        # добавлены позже той же миграционной схемой.
        await _ensure_column(
            conn, "users", "referral_reward_mode", "TEXT DEFAULT 'days' NOT NULL"
        )
        await _ensure_column(conn, "users", "balance", "INTEGER DEFAULT 0 NOT NULL")

        # ReferralReward: раньше писали только bonus_days (режим "дни"
        # был единственным) — на существующих строках reward_type
        # проставится в дефолт 'days' автоматически (DEFAULT в DDL),
        # что и есть правильная история для тех начислений.
        await _ensure_column(
            conn, "referral_rewards", "reward_type", "TEXT DEFAULT 'days' NOT NULL"
        )
        await _ensure_column(conn, "referral_rewards", "bonus_balance", "INTEGER")

        # Отдельная переопределяемая цена тарифа для оплаты бонусным
        # балансом (по умолчанию совпадает с card_price, см.
        # app.services.tariffs.get_tariffs()).
        await _ensure_column(conn, "tariff_prices", "balance_price", "INTEGER")


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
