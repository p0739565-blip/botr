import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import String, select
from sqlalchemy.orm import selectinload

from app.admin.auth import require_permission
from app.admin.models import AdminUser, Permission
from app.db import async_session
from app.models import Payment, PlategaPayment, User
from app.settings.tariffs import TARIFFS

router = APIRouter(prefix="/payments", tags=["payments"])

# Единый справочник статусов для фильтра и бейджей в шаблоне.
# У Stars-платежей своего статуса нет (в Payment пишется только факт
# уже состоявшейся оплаты), поэтому им всегда присваивается "confirmed".
STATUS_LABELS: dict[str, str] = {
    "confirmed": "Подтверждён",
    "pending": "Ожидание",
    "canceled": "Отменён",
    "chargebacked": "Возврат",
}

METHOD_LABELS: dict[str, str] = {
    "card": "Карта",
    "sbp": "СБП",
    "stars": "Telegram Stars",
    "crypto": "Крипта",
}


def _tariff_title(tariff_key: str) -> str:
    tariff = TARIFFS.get(tariff_key)
    return tariff["title"] if tariff else tariff_key


@router.get("")
async def payments_list(
    request: Request,
    q: str = "",
    method: str = "",
    status: str = "",
    admin: AdminUser = Depends(require_permission(Permission.VIEW_PAYMENTS)),
):
    from app.admin.router import templates

    async with async_session() as session:
        # --- Карта/СБП: полная история попыток, статус ведёт Platega ---
        platega_stmt = select(PlategaPayment).options(selectinload(PlategaPayment.user))

        if q.strip():
            needle = f"%{q.strip()}%"
            platega_stmt = platega_stmt.join(User, PlategaPayment.user_id == User.id).where(
                (User.username.ilike(needle)) | (User.tg_id.cast(String).ilike(needle))
            )

        if method and method != "stars":
            platega_stmt = platega_stmt.where(PlategaPayment.method == method)

        if status:
            platega_stmt = platega_stmt.where(PlategaPayment.status == status.upper())

        platega_result = await session.execute(
            platega_stmt.order_by(PlategaPayment.created_at.desc()).limit(300)
        )
        platega_rows = platega_result.scalars().unique().all()

        rows = [
            {
                "created_at": p.created_at,
                "user": p.user,
                "method": p.method,
                "tariff_title": _tariff_title(p.tariff_key),
                "amount": p.amount,
                "currency": p.currency,
                "status": p.status.lower(),
                "transaction_id": p.transaction_id,
            }
            for p in platega_rows
        ]

        # --- Telegram Stars: только состоявшиеся оплаты (без "попыток") ---
        if not status or status == "confirmed":
            if not method or method == "stars":
                stars_stmt = (
                    select(Payment)
                    .options(selectinload(Payment.user))
                    .where(Payment.method == "stars")
                )

                if q.strip():
                    needle = f"%{q.strip()}%"
                    stars_stmt = stars_stmt.join(User, Payment.user_id == User.id).where(
                        (User.username.ilike(needle)) | (User.tg_id.cast(String).ilike(needle))
                    )

                stars_result = await session.execute(
                    stars_stmt.order_by(Payment.created_at.desc()).limit(300)
                )
                stars_rows = stars_result.scalars().unique().all()

                rows += [
                    {
                        "created_at": p.created_at,
                        "user": p.user,
                        "method": "stars",
                        "tariff_title": _tariff_title(p.tariff_key),
                        "amount": p.amount,
                        "currency": "XTR",
                        "status": "confirmed",
                        "transaction_id": None,
                    }
                    for p in stars_rows
                ]

    rows.sort(key=lambda r: r["created_at"], reverse=True)
    rows = rows[:300]

    counts = {"total": len(rows)}
    for key in STATUS_LABELS:
        counts[key] = sum(1 for r in rows if r["status"] == key)

    return templates.TemplateResponse(
        "payments.html",
        {
            "request": request,
            "admin": admin,
            "rows": rows,
            "q": q,
            "method": method,
            "status": status,
            "status_labels": STATUS_LABELS,
            "method_labels": METHOD_LABELS,
            "counts": counts,
        },
    )
