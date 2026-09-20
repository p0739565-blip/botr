from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.admin.auth import require_permission
from app.admin.models import AdminUser, AuditLog, Permission
from app.db import async_session

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
async def audit_log(
    request: Request,
    admin: AdminUser = Depends(require_permission(Permission.VIEW_AUDIT_LOG)),
):
    from app.admin.router import templates

    async with async_session() as session:
        result = await session.execute(
            select(AuditLog)
            .options(selectinload(AuditLog.admin))
            .order_by(AuditLog.created_at.desc())
            .limit(300)
        )
        entries = result.scalars().all()

    return templates.TemplateResponse(
        "audit.html",
        {"request": request, "admin": admin, "entries": entries},
    )
