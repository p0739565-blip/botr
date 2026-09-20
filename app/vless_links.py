"""Источник списка конфигов (vless/hy2), которые сервер отдаёт по
/sub/<token>. Раньше список был статичным списком в этом файле —
теперь он хранится в таблице vless_links и правится через админку
(/admin/vless-links), без правки кода и перезапуска процессов.

Старые захардкоженные списки (если нужно перенести их в БД разово)
лежат в app/vless_links_seed.py — см. инструкцию там.
"""

from sqlalchemy import select

from app.db import async_session
from app.models import VlessLink, VlessLinkGroup


def _ordered_links_query(is_dead: bool):
    """Ссылки, отсортированные так же, как их видно в админке: сначала
    по позиции группы (группы без ссылок вне выборки не влияют),
    ссылки без группы — в самом конце (как раздел «Без группы» в
    /admin/vless-links), внутри группы/раздела — по позиции ссылки.

    VlessLink.position считается ОТДЕЛЬНО в каждой группе (см.
    _next_position в админке) — поэтому сортировать только по нему,
    без учёта группы, нельзя: у ссылок из разных групп значения
    position совпадают, и итоговый список перемешивается. Раньше здесь
    не было order_by группы вообще — это и есть причина хаотичного
    порядка ссылок в клиенте.
    """
    return (
        select(VlessLink.url)
        .outerjoin(VlessLinkGroup, VlessLink.group_id == VlessLinkGroup.id)
        .where(VlessLink.is_dead.is_(is_dead), VlessLink.is_active.is_(True))
        .order_by(
            VlessLink.group_id.is_(None),  # сгруппированные ссылки — раньше «без группы»
            VlessLinkGroup.position,
            VlessLink.group_id,
            VlessLink.position,
            VlessLink.id,
        )
    )


async def render_links(uuid: str) -> list[str]:
    """Возвращает активные рабочие ссылки в заданном порядке.

    Аргумент uuid оставлен для обратной совместимости сигнатуры (раньше
    подставлялся в шаблон ссылки) — сейчас ссылки статичны и одинаковы
    для всех, как было и в старой версии, поэтому не используется.
    """
    async with async_session() as session:
        result = await session.execute(_ordered_links_query(is_dead=False))
        return list(result.scalars().all())


async def get_dead_links() -> list[str]:
    """Заглушечные ссылки, которые отдаются вместо обычного списка,
    если токен не найден или подписка истекла."""
    async with async_session() as session:
        result = await session.execute(_ordered_links_query(is_dead=True))
        return list(result.scalars().all())
