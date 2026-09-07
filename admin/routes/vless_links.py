from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.admin.auth import require_permission, write_audit_log
from app.admin.link_names import extract_link_name, set_link_name, strip_link_name
from app.admin.models import AdminUser, Permission
from app.db import async_session
from app.models import VlessLink, VlessLinkGroup

router = APIRouter(prefix="/vless-links", tags=["vless-links"])

LINK_PREFIXES = ("vless://", "vmess://", "hy2://", "hysteria2://", "trojan://", "ss://")


def _apply_name(url: str, name: str) -> str:
    """Если имя задано отдельным полем — впечатывает его в ссылку как
    фрагмент, заменяя то, что там было. Если поле пустое — ссылка
    остаётся как есть (со своим собственным фрагментом, если он был)."""
    name = name.strip()
    return set_link_name(url, name) if name else url


async def _next_position(session, is_dead: bool, group_id: int | None) -> int:
    """Следующая позиция — в пределах своей группы (или в пределах
    ссылок без группы), а не всего набора рабочих/запасных целиком,
    иначе новая ссылка внутри группы уезжала бы в конец всего списка."""
    result = await session.execute(
        select(VlessLink.position)
        .where(
            VlessLink.is_dead.is_(is_dead),
            VlessLink.group_id == group_id,
        )
        .order_by(VlessLink.position.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()
    return (last + 1) if last is not None else 0


async def _next_group_position(session, is_dead: bool) -> int:
    result = await session.execute(
        select(VlessLinkGroup.position)
        .where(VlessLinkGroup.is_dead.is_(is_dead))
        .order_by(VlessLinkGroup.position.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()
    return (last + 1) if last is not None else 0


async def _groups_for(session, is_dead: bool) -> list[VlessLinkGroup]:
    result = await session.execute(
        select(VlessLinkGroup)
        .where(VlessLinkGroup.is_dead.is_(is_dead))
        .options(selectinload(VlessLinkGroup.links))
        .order_by(VlessLinkGroup.position, VlessLinkGroup.id)
    )
    return result.scalars().all()


async def _ungrouped_links(session, is_dead: bool) -> list[VlessLink]:
    result = await session.execute(
        select(VlessLink)
        .where(VlessLink.is_dead.is_(is_dead), VlessLink.group_id.is_(None))
        .order_by(VlessLink.position, VlessLink.id)
    )
    return result.scalars().all()


# ==========================================
# Список
# ==========================================

@router.get("")
async def list_links(
    request: Request,
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_VLESS_LINKS)),
):
    from app.admin.router import templates

    async with async_session() as session:
        working_groups = await _groups_for(session, False)
        working_ungrouped = await _ungrouped_links(session, False)

        dead_groups = await _groups_for(session, True)
        dead_ungrouped = await _ungrouped_links(session, True)

        all_working = (
            await session.execute(
                select(VlessLink).where(VlessLink.is_dead.is_(False))
            )
        ).scalars().all()

    return templates.TemplateResponse(
        "vless_links.html",
        {
            "request": request,
            "admin": admin,
            "working_groups": working_groups,
            "working_ungrouped": working_ungrouped,
            "dead_groups": dead_groups,
            "dead_ungrouped": dead_ungrouped,
            "working_active_count": sum(1 for link in all_working if link.is_active),
            "link_name": extract_link_name,
        },
    )


# ==========================================
# Ссылки — создание / редактирование
# ==========================================

@router.get("/new")
async def new_link_form(
    request: Request,
    dead: int = 0,
    group_id: int | None = None,
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_VLESS_LINKS)),
):
    from app.admin.router import templates

    is_dead_bool = bool(dead)

    async with async_session() as session:
        groups = await _groups_for(session, is_dead_bool)

    return templates.TemplateResponse(
        "vless_link_form.html",
        {
            "request": request,
            "admin": admin,
            "link": None,
            "is_dead": is_dead_bool,
            "groups": groups,
            "selected_group_id": group_id,
            "error": None,
        },
    )


@router.post("/new")
async def create_link(
    request: Request,
    url: str = Form(...),
    name: str = Form(""),
    note: str = Form(""),
    group_id: str = Form(""),
    is_dead: str = Form("0"),
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_VLESS_LINKS)),
):
    from app.admin.router import templates

    url = url.strip()
    is_dead_bool = is_dead == "1"
    group_id_int = int(group_id) if group_id.strip() else None

    if not url.startswith(LINK_PREFIXES):
        async with async_session() as session:
            groups = await _groups_for(session, is_dead_bool)
        return templates.TemplateResponse(
            "vless_link_form.html",
            {
                "request": request,
                "admin": admin,
                "link": None,
                "is_dead": is_dead_bool,
                "groups": groups,
                "selected_group_id": group_id_int,
                "error": "Похоже, это не ссылка-конфиг (ожидается vless://, hy2:// и т.п.)",
            },
            status_code=400,
        )

    final_url = _apply_name(url, name)

    async with async_session() as session:
        if group_id_int is not None:
            group = await session.get(VlessLinkGroup, group_id_int)
            if group is None or group.is_dead != is_dead_bool:
                group_id_int = None

        position = await _next_position(session, is_dead_bool, group_id_int)
        link = VlessLink(
            url=final_url,
            note=note.strip() or None,
            group_id=group_id_int,
            is_dead=is_dead_bool,
            is_active=True,
            position=position,
        )
        session.add(link)
        await session.commit()
        link_id = link.id

    await write_audit_log(
        admin,
        action="create_vless_link",
        target=f"vless_link_id={link_id}",
        details=f"is_dead={is_dead_bool}",
    )

    return RedirectResponse("/admin/vless-links", status_code=303)


@router.get("/{link_id}/edit")
async def edit_link_form(
    request: Request,
    link_id: int,
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_VLESS_LINKS)),
):
    from app.admin.router import templates

    async with async_session() as session:
        link = await session.get(VlessLink, link_id)
        if link is None:
            raise HTTPException(status_code=404, detail="Ссылка не найдена")
        groups = await _groups_for(session, link.is_dead)

    return templates.TemplateResponse(
        "vless_link_form.html",
        {
            "request": request,
            "admin": admin,
            "link": link,
            "is_dead": link.is_dead,
            "groups": groups,
            "selected_group_id": link.group_id,
            "current_name": extract_link_name(link.url),
            "current_base_url": strip_link_name(link.url),
            "error": None,
        },
    )


@router.post("/{link_id}/edit")
async def edit_link(
    request: Request,
    link_id: int,
    url: str = Form(...),
    name: str = Form(""),
    note: str = Form(""),
    group_id: str = Form(""),
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_VLESS_LINKS)),
):
    from app.admin.router import templates

    url = url.strip()

    async with async_session() as session:
        link = await session.get(VlessLink, link_id)
        if link is None:
            raise HTTPException(status_code=404, detail="Ссылка не найдена")
        groups = await _groups_for(session, link.is_dead)

    if not url.startswith(LINK_PREFIXES):
        return templates.TemplateResponse(
            "vless_link_form.html",
            {
                "request": request,
                "admin": admin,
                "link": link,
                "is_dead": link.is_dead,
                "groups": groups,
                "selected_group_id": link.group_id,
                "current_name": name,
                "current_base_url": url,
                "error": "Похоже, это не ссылка-конфиг (ожидается vless://, hy2:// и т.п.)",
            },
            status_code=400,
        )

    final_url = _apply_name(url, name)
    group_id_int = int(group_id) if group_id.strip() else None

    async with async_session() as session:
        link = await session.get(VlessLink, link_id)
        if link is None:
            raise HTTPException(status_code=404, detail="Ссылка не найдена")

        if group_id_int is not None:
            group = await session.get(VlessLinkGroup, group_id_int)
            if group is None or group.is_dead != link.is_dead:
                group_id_int = None

        link.url = final_url
        link.note = note.strip() or None
        link.group_id = group_id_int
        await session.commit()

    await write_audit_log(
        admin, action="edit_vless_link", target=f"vless_link_id={link_id}"
    )

    return RedirectResponse("/admin/vless-links", status_code=303)


@router.post("/{link_id}/toggle")
async def toggle_link(
    link_id: int,
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_VLESS_LINKS)),
):
    async with async_session() as session:
        link = await session.get(VlessLink, link_id)
        if link is None:
            raise HTTPException(status_code=404, detail="Ссылка не найдена")

        link.is_active = not link.is_active
        new_status = link.is_active
        await session.commit()

    await write_audit_log(
        admin,
        action="toggle_vless_link",
        target=f"vless_link_id={link_id}",
        details=f"is_active={new_status}",
    )

    return RedirectResponse("/admin/vless-links", status_code=303)


@router.post("/{link_id}/delete")
async def delete_link(
    link_id: int,
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_VLESS_LINKS)),
):
    async with async_session() as session:
        link = await session.get(VlessLink, link_id)
        if link is None:
            raise HTTPException(status_code=404, detail="Ссылка не найдена")

        await session.delete(link)
        await session.commit()

    await write_audit_log(
        admin, action="delete_vless_link", target=f"vless_link_id={link_id}"
    )

    return RedirectResponse("/admin/vless-links", status_code=303)


@router.post("/{link_id}/move")
async def move_link(
    link_id: int,
    direction: str = Form(...),
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_VLESS_LINKS)),
):
    """Меняет местами позицию ссылки с соседней — в пределах своей же
    группы (или в пределах "без группы"), не всего набора целиком,
    иначе перемещение "выдёргивало" бы ссылку из группы визуально."""
    if direction not in ("up", "down"):
        raise HTTPException(status_code=400, detail="Неизвестное направление")

    async with async_session() as session:
        link = await session.get(VlessLink, link_id)
        if link is None:
            raise HTTPException(status_code=404, detail="Ссылка не найдена")

        siblings = (
            await session.execute(
                select(VlessLink)
                .where(
                    VlessLink.is_dead.is_(link.is_dead),
                    VlessLink.group_id == link.group_id,
                )
                .order_by(VlessLink.position, VlessLink.id)
            )
        ).scalars().all()

        idx = next((i for i, s in enumerate(siblings) if s.id == link.id), None)
        if idx is None:
            raise HTTPException(status_code=404, detail="Ссылка не найдена")

        swap_idx = idx - 1 if direction == "up" else idx + 1
        if 0 <= swap_idx < len(siblings):
            other = siblings[swap_idx]
            link.position, other.position = other.position, link.position
            await session.commit()

    return RedirectResponse("/admin/vless-links", status_code=303)


# ==========================================
# Группы
# ==========================================

@router.post("/groups/new")
async def create_group(
    name: str = Form(...),
    description: str = Form(""),
    is_dead: str = Form("0"),
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_VLESS_LINKS)),
):
    is_dead_bool = is_dead == "1"
    name = name.strip()

    if not name:
        return RedirectResponse("/admin/vless-links", status_code=303)

    async with async_session() as session:
        position = await _next_group_position(session, is_dead_bool)
        group = VlessLinkGroup(
            name=name,
            description=description.strip() or None,
            is_dead=is_dead_bool,
            position=position,
        )
        session.add(group)
        await session.commit()
        group_id = group.id

    await write_audit_log(
        admin,
        action="create_vless_link_group",
        target=f"vless_link_group_id={group_id}",
        details=f"is_dead={is_dead_bool}",
    )

    return RedirectResponse("/admin/vless-links", status_code=303)


@router.get("/groups/{group_id}/edit")
async def edit_group_form(
    request: Request,
    group_id: int,
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_VLESS_LINKS)),
):
    from app.admin.router import templates

    async with async_session() as session:
        group = await session.get(VlessLinkGroup, group_id)

    if group is None:
        raise HTTPException(status_code=404, detail="Группа не найдена")

    return templates.TemplateResponse(
        "vless_link_group_form.html",
        {"request": request, "admin": admin, "group": group, "error": None},
    )


@router.post("/groups/{group_id}/edit")
async def edit_group(
    request: Request,
    group_id: int,
    name: str = Form(...),
    description: str = Form(""),
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_VLESS_LINKS)),
):
    from app.admin.router import templates

    name = name.strip()

    async with async_session() as session:
        group = await session.get(VlessLinkGroup, group_id)
        if group is None:
            raise HTTPException(status_code=404, detail="Группа не найдена")

        if not name:
            return templates.TemplateResponse(
                "vless_link_group_form.html",
                {
                    "request": request,
                    "admin": admin,
                    "group": group,
                    "error": "Название группы не может быть пустым",
                },
                status_code=400,
            )

        group.name = name
        group.description = description.strip() or None
        await session.commit()

    await write_audit_log(
        admin, action="edit_vless_link_group", target=f"vless_link_group_id={group_id}"
    )

    return RedirectResponse("/admin/vless-links", status_code=303)


@router.post("/groups/{group_id}/delete")
async def delete_group(
    group_id: int,
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_VLESS_LINKS)),
):
    """Удаляет группу, но НЕ трогает ссылки внутри — они просто
    становятся "без группы" (group_id=None), а не удаляются."""
    async with async_session() as session:
        group = await session.get(VlessLinkGroup, group_id)
        if group is None:
            raise HTTPException(status_code=404, detail="Группа не найдена")

        result = await session.execute(
            select(VlessLink).where(VlessLink.group_id == group_id)
        )
        for link in result.scalars().all():
            link.group_id = None

        await session.delete(group)
        await session.commit()

    await write_audit_log(
        admin, action="delete_vless_link_group", target=f"vless_link_group_id={group_id}"
    )

    return RedirectResponse("/admin/vless-links", status_code=303)


@router.post("/groups/{group_id}/move")
async def move_group(
    group_id: int,
    direction: str = Form(...),
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_VLESS_LINKS)),
):
    if direction not in ("up", "down"):
        raise HTTPException(status_code=400, detail="Неизвестное направление")

    async with async_session() as session:
        group = await session.get(VlessLinkGroup, group_id)
        if group is None:
            raise HTTPException(status_code=404, detail="Группа не найдена")

        siblings = (
            await session.execute(
                select(VlessLinkGroup)
                .where(VlessLinkGroup.is_dead.is_(group.is_dead))
                .order_by(VlessLinkGroup.position, VlessLinkGroup.id)
            )
        ).scalars().all()

        idx = next((i for i, s in enumerate(siblings) if s.id == group.id), None)
        if idx is None:
            raise HTTPException(status_code=404, detail="Группа не найдена")

        swap_idx = idx - 1 if direction == "up" else idx + 1
        if 0 <= swap_idx < len(siblings):
            other = siblings[swap_idx]
            group.position, other.position = other.position, group.position
            await session.commit()

    return RedirectResponse("/admin/vless-links", status_code=303)
