from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.admin.auth import get_admin_by_id, hash_password, write_audit_log
from app.admin.auth import require_permission
from app.admin.models import (
    ROLE_DEFAULT_PERMISSIONS,
    ROLE_RANK,
    AdminPermission,
    AdminRole,
    AdminUser,
    Permission,
)
from app.db import async_session

router = APIRouter(prefix="/admins", tags=["admins"])


def _assignable_roles(admin: AdminUser) -> list[AdminRole]:
    """Роли, которые этот admin имеет право назначить (создать/сменить на)."""
    return [r for r in AdminRole if admin.can_grant_role(r)]


def _assignable_permissions(admin: AdminUser) -> list[Permission]:
    """Права, которые этот admin имеет право выдать другому."""
    return [p for p in Permission if admin.can_grant_permission(p)]


@router.get("")
async def admins_list(
    request: Request,
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_ADMINS)),
):
    from app.admin.router import templates

    async with async_session() as session:
        result = await session.execute(
            select(AdminUser)
            .options(selectinload(AdminUser.permissions))
            .order_by(AdminUser.created_at)
        )
        admins = result.scalars().all()

    return templates.TemplateResponse(
        "admins.html",
        {"request": request, "admin": admin, "admins": admins},
    )


@router.get("/new")
async def new_admin_form(
    request: Request,
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_ADMINS)),
):
    from app.admin.router import templates

    return templates.TemplateResponse(
        "admin_form.html",
        {
            "request": request,
            "admin": admin,
            "target": None,
            # Показываем только то, что этот admin реально может выдать —
            # бэкенд всё равно перепроверит на POST, но так UI не вводит
            # в заблуждение недостижимыми опциями.
            "all_permissions": _assignable_permissions(admin),
            "roles": _assignable_roles(admin),
            "error": None,
        },
    )


@router.post("/new")
async def create_admin(
    request: Request,
    login: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_ADMINS)),
):
    from app.admin.router import templates

    login = login.strip()

    if len(login) < 3 or len(password) < 8:
        return templates.TemplateResponse(
            "admin_form.html",
            {
                "request": request,
                "admin": admin,
                "target": None,
                "all_permissions": _assignable_permissions(admin),
                "roles": _assignable_roles(admin),
                "error": "Логин от 3 символов, пароль от 8 символов",
            },
            status_code=400,
        )

    try:
        role_enum = AdminRole(role)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неизвестная роль")

    # Нельзя создать админа с ролью равной своей или выше — иначе обычный
    # admin с правом MANAGE_ADMINS мог бы завести себе второго admin'а
    # или сразу super_admin'а в обход собственных ограничений.
    if not admin.can_grant_role(role_enum):
        raise HTTPException(
            status_code=403,
            detail="Нельзя создать админа с ролью, равной вашей или выше",
        )

    form = await request.form()
    selected_permissions = form.getlist("permissions")

    # Аналогично для прав: нельзя выдать право, которого не имеешь сам —
    # иначе можно было бы обойти собственные ограничения, выдав кому-то
    # (или себе на другом аккаунте) право, которым сам не обладаешь.
    try:
        requested_perms = [Permission(p) for p in selected_permissions]
    except ValueError:
        raise HTTPException(status_code=400, detail="Неизвестное право")

    not_owned = [p for p in requested_perms if not admin.can_grant_permission(p)]
    if not_owned:
        raise HTTPException(
            status_code=403,
            detail="Нельзя выдать права, которых нет у вас самого",
        )

    async with async_session() as session:
        existing = await session.execute(
            select(AdminUser).where(AdminUser.login == login)
        )
        if existing.scalar_one_or_none() is not None:
            return templates.TemplateResponse(
                "admin_form.html",
                {
                    "request": request,
                    "admin": admin,
                    "target": None,
                    "all_permissions": _assignable_permissions(admin),
                    "roles": _assignable_roles(admin),
                    "error": "Такой логин уже занят",
                },
                status_code=400,
            )

        new_admin = AdminUser(
            login=login,
            password_hash=hash_password(password),
            role=role_enum,
        )
        session.add(new_admin)
        await session.flush()  # получить new_admin.id до коммита

        final_perms = requested_perms or list(ROLE_DEFAULT_PERMISSIONS[role_enum])

        # Даже дефолтный набор роли может включать право, которого у
        # создающего admin'а нет (пресеты выбираются независимо от того,
        # кто их выдаёт) — фильтруем и здесь, а не только для явного
        # выбора чекбоксов выше.
        final_perms = [p for p in final_perms if admin.can_grant_permission(p)]

        for perm in final_perms:
            session.add(
                AdminPermission(admin_id=new_admin.id, permission=perm)
            )

        await session.commit()
        new_admin_id = new_admin.id

    await write_audit_log(
        admin,
        action="create_admin",
        target=f"login={login}",
        details=f"role={role_enum.value}",
    )

    return RedirectResponse(f"/admin/admins/{new_admin_id}/edit", status_code=303)


@router.get("/{admin_id}/edit")
async def edit_admin_form(
    request: Request,
    admin_id: int,
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_ADMINS)),
):
    from app.admin.router import templates

    target = await get_admin_by_id(admin_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Админ не найден")

    # Нельзя открыть форму редактирования того, кем не имеешь права
    # управлять (равный или более высокий ранг, кроме случая, когда
    # редактирующий сам super_admin). Проверяем и на GET, и на POST —
    # иначе прямой POST-запрос в обход формы обошёл бы эту защиту.
    if not admin.can_manage(target):
        raise HTTPException(
            status_code=403,
            detail="Недостаточно прав для управления этим админом",
        )

    return templates.TemplateResponse(
        "admin_form.html",
        {
            "request": request,
            "admin": admin,
            "target": target,
            "target_permissions": {p.permission for p in target.permissions},
            "all_permissions": _assignable_permissions(admin),
            "roles": _assignable_roles(admin),
            "error": None,
        },
    )


@router.post("/{admin_id}/edit")
async def edit_admin(
    request: Request,
    admin_id: int,
    role: str = Form(...),
    new_password: str = Form(""),
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_ADMINS)),
):
    try:
        role_enum = AdminRole(role)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неизвестная роль")

    form = await request.form()
    selected_permissions = form.getlist("permissions")

    try:
        requested_perms = [Permission(p) for p in selected_permissions]
    except ValueError:
        raise HTTPException(status_code=400, detail="Неизвестное право")

    async with async_session() as session:
        result = await session.execute(
            select(AdminUser)
            .options(selectinload(AdminUser.permissions))
            .where(AdminUser.id == admin_id)
        )
        target = result.scalar_one_or_none()

        if target is None:
            raise HTTPException(status_code=404, detail="Админ не найден")

        # Та же проверка иерархии, что и на GET — POST может прийти
        # напрямую (curl/Postman) в обход формы, GET-проверку это не
        # страхует.
        if not admin.can_manage(target):
            raise HTTPException(
                status_code=403,
                detail="Недостаточно прав для управления этим админом",
            )

        # Нельзя повысить цель до роли, равной своей или выше.
        if not admin.can_grant_role(role_enum):
            raise HTTPException(
                status_code=403,
                detail="Нельзя назначить роль, равную вашей или выше",
            )

        # Нельзя выдать право, которого нет у самого редактирующего.
        not_owned = [p for p in requested_perms if not admin.can_grant_permission(p)]
        if not_owned:
            raise HTTPException(
                status_code=403,
                detail="Нельзя выдать права, которых нет у вас самого",
            )

        target.role = role_enum

        if new_password.strip():
            if len(new_password.strip()) < 8:
                raise HTTPException(
                    status_code=400, detail="Пароль от 8 символов"
                )
            target.password_hash = hash_password(new_password.strip())

        # Пересобираем набор прав под выбранные галочки — но только в
        # пределах того, что редактор вообще контролирует. Права цели,
        # которые редактору не подконтрольны (чекбокс для них даже не
        # показывается в форме), молча сохраняем как есть — иначе они бы
        # незаметно терялись при любом сохранении формы менее
        # привилегированным редактором.
        controllable = set(_assignable_permissions(admin))
        existing_perms = {p.permission for p in target.permissions}
        kept = existing_perms - controllable
        final_perms = kept | set(requested_perms)

        for existing_perm in list(target.permissions):
            await session.delete(existing_perm)

        for perm in final_perms:
            session.add(
                AdminPermission(admin_id=admin_id, permission=perm)
            )

        await session.commit()

    await write_audit_log(
        admin,
        action="edit_admin",
        target=f"admin_id={admin_id}",
        details=f"role={role_enum.value}, permissions={selected_permissions}",
    )

    return RedirectResponse("/admin/admins", status_code=303)


@router.post("/{admin_id}/deactivate")
async def deactivate_admin(
    admin_id: int,
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_ADMINS)),
):
    if admin_id == admin.id:
        raise HTTPException(
            status_code=400, detail="Нельзя деактивировать самого себя"
        )

    async with async_session() as session:
        result = await session.execute(
            select(AdminUser).where(AdminUser.id == admin_id)
        )
        target = result.scalar_one_or_none()

        if target is None:
            raise HTTPException(status_code=404, detail="Админ не найден")

        # Та же иерархия, что и для edit: нельзя деактивировать
        # равного или более высокого по рангу, если сам не super_admin.
        if not admin.can_manage(target):
            raise HTTPException(
                status_code=403,
                detail="Недостаточно прав для управления этим админом",
            )

        # Нельзя выключить последнего активного super_admin — иначе
        # система остаётся вообще без владельца, способного всё
        # восстановить (и без пути обратно, кроме прямого доступа к БД).
        if target.role == AdminRole.SUPER_ADMIN and target.is_active:
            active_super_admins = await session.execute(
                select(AdminUser).where(
                    AdminUser.role == AdminRole.SUPER_ADMIN,
                    AdminUser.is_active.is_(True),
                )
            )
            if len(active_super_admins.scalars().all()) <= 1:
                raise HTTPException(
                    status_code=400,
                    detail="Нельзя деактивировать последнего активного супер-админа",
                )

        target.is_active = not target.is_active
        new_status = target.is_active

        await session.commit()

    await write_audit_log(
        admin,
        action="toggle_admin_active",
        target=f"admin_id={admin_id}",
        details=f"is_active={new_status}",
    )

    return RedirectResponse("/admin/admins", status_code=303)
