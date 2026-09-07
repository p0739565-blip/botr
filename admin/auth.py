import bcrypt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.admin.models import AdminRole, AdminUser, AuditLog, Permission
from app.db import async_session


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        # Битый/пустой хэш в базе — считаем пароль неверным, а не 500-ю ошибку.
        return False


async def get_admin_by_login(login: str) -> AdminUser | None:
    async with async_session() as session:
        result = await session.execute(
            select(AdminUser)
            .options(selectinload(AdminUser.permissions))
            .where(AdminUser.login == login)
        )
        return result.scalar_one_or_none()


async def get_admin_by_id(admin_id: int) -> AdminUser | None:
    async with async_session() as session:
        result = await session.execute(
            select(AdminUser)
            .options(selectinload(AdminUser.permissions))
            .where(AdminUser.id == admin_id)
        )
        return result.scalar_one_or_none()


async def get_current_admin(request: Request) -> AdminUser:
    """Базовая зависимость: просто "залогинен ли кто-то вообще".
    Для проверки конкретных прав используйте require_permission()."""

    admin_id = request.session.get("admin_id")

    if admin_id is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/admin/login"},
        )

    admin = await get_admin_by_id(admin_id)

    if admin is None or not admin.is_active:
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/admin/login"},
        )

    return admin


def require_permission(permission: Permission):
    """Фабрика зависимостей: Depends(require_permission(Permission.X)).

    Права проверяются здесь, на бэкенде — независимо от того, что
    показывает или скрывает шаблон. Наблюдатель физически не сможет
    вызвать защищённый роут, даже зная прямой URL."""

    async def _checker(
        admin: AdminUser = Depends(get_current_admin),
    ) -> AdminUser:
        if not admin.has_permission(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав для этого действия",
            )
        return admin

    return _checker


async def require_super_admin(
    admin: AdminUser = Depends(get_current_admin),
) -> AdminUser:
    """Жёсткая проверка по роли, а не по выдаваемому праву — используется
    для необратимых операций удаления данных (записи подписок), которые
    сознательно НЕ должны быть делегируемыми: только тот, кто буквально
    супер-админ, может их выполнять, независимо от того, какие галочки
    прав ему выставлены."""

    if admin.role != AdminRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступно только супер-админу",
        )
    return admin


async def write_audit_log(
    admin: AdminUser,
    action: str,
    target: str | None = None,
    details: str | None = None,
) -> None:
    async with async_session() as session:
        session.add(
            AuditLog(
                admin_id=admin.id,
                action=action,
                target=target,
                details=details,
            )
        )
        await session.commit()
