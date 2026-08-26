"""
Простые key-value настройки, которым не нужна отдельная таблица со
своими полями — например, размер реферального бонуса. Значения всегда
хранятся строкой, парсинг (int и т.п.) — на стороне вызывающего кода.
"""

from app.db import async_session
from app.models import AppSetting

DEFAULTS: dict[str, str] = {
    "referral_bonus_days": "7",
    "referral_bonus_percent": "10",
}


async def get_setting(key: str) -> str:
    async with async_session() as session:
        row = await session.get(AppSetting, key)
        if row is not None:
            return row.value
    return DEFAULTS.get(key, "")


async def get_setting_int(key: str) -> int:
    raw = await get_setting(key)
    try:
        return int(raw)
    except ValueError:
        return int(DEFAULTS.get(key, "0"))


async def set_setting(key: str, value: str) -> None:
    async with async_session() as session:
        row = await session.get(AppSetting, key)
        if row is None:
            row = AppSetting(key=key, value=value)
            session.add(row)
        else:
            row.value = value
        await session.commit()
