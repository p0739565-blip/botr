import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import String, delete, select
from sqlalchemy.orm import selectinload

from app.admin.auth import require_permission, require_super_admin, write_audit_log
from app.admin.models import AdminUser, Permission
from app.db import async_session
from app.models import Payment, Subscription, User

router = APIRouter(prefix="/users", tags=["users"])

# Пресеты периода для массовой очистки — ключ уходит в форму, дни
# считаются здесь же на бэкенде (фронт не может подставить произвольное
# число, только один из этих вариантов).
PURGE_PERIODS: dict[str, int] = {
    "day": 1,
    "week": 7,
    "month": 30,
    "3months": 90,
    "12months": 365,
}

PURGE_PERIOD_LABELS: dict[str, str] = {
    "day": "старше суток",
    "week": "старше недели",
    "month": "старше месяца",
    "3months": "старше 3 месяцев",
    "12months": "старше 12 месяцев",
}


@router.get("")
async def users_list(
    request: Request,
    q: str = "",
    purged: int | None = None,
    admin: AdminUser = Depends(require_permission(Permission.VIEW_USERS)),
):
    from app.admin.router import templates

    async with async_session() as session:
        stmt = select(User).options(selectinload(User.subscriptions))

        if q.strip():
            needle = f"%{q.strip()}%"
            stmt = stmt.where(
                (User.username.ilike(needle)) | (User.tg_id.cast(String).ilike(needle))
            )

        stmt = stmt.order_by(User.created_at.desc()).limit(200)

        result = await session.execute(stmt)
        users = result.scalars().unique().all()

    rows = []
    now = datetime.datetime.now()
    for user in users:
        active_sub = next(
            (s for s in user.subscriptions if s.is_active and s.expiry > now),
            None,
        )
        rows.append({"user": user, "active_sub": active_sub})

    return templates.TemplateResponse(
        "users.html",
        {
            "request": request,
            "admin": admin,
            "rows": rows,
            "q": q,
            "purged": purged,
            "purge_periods": PURGE_PERIOD_LABELS,
        },
    )


@router.get("/{user_id}")
async def user_detail(
    request: Request,
    user_id: int,
    purged: int | None = None,
    admin: AdminUser = Depends(require_permission(Permission.VIEW_USERS)),
):
    from app.admin.router import templates

    async with async_session() as session:
        result = await session.execute(
            select(User)
            .options(selectinload(User.subscriptions))
            .where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if user is None:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        payments_result = await session.execute(
            select(Payment)
            .where(Payment.user_id == user_id)
            .order_by(Payment.created_at.desc())
        )
        payments = payments_result.scalars().all()

    subs_sorted = sorted(
        user.subscriptions, key=lambda s: s.created_at, reverse=True
    )

    now = datetime.datetime.now()

    can_activate = any(
        (not s.is_active) and s.expiry > now for s in subs_sorted
    )

    return templates.TemplateResponse(
        "user_detail.html",
        {
            "request": request,
            "admin": admin,
            "user": user,
            "subscriptions": subs_sorted,
            "payments": payments,
            "can_issue": admin.has_permission(Permission.ISSUE_SUBSCRIPTION),
            "can_revoke": admin.has_permission(Permission.REVOKE_SUBSCRIPTION),
            "can_manage_balance": admin.has_permission(Permission.MANAGE_USER_BALANCE),
            "can_activate": can_activate,
            "purged": purged,
            "purge_periods": PURGE_PERIOD_LABELS,
        },
    )


@router.post("/{user_id}/extend")
async def extend_subscription(
    user_id: int,
    days: int = Form(...),
    admin: AdminUser = Depends(require_permission(Permission.ISSUE_SUBSCRIPTION)),
):
    if days <= 0 or days > 3650:
        raise HTTPException(status_code=400, detail="Некорректное число дней")

    from app.services.subscription import issue_subscription

    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    await issue_subscription(user=user, days=days)

    await write_audit_log(
        admin,
        action="extend_subscription",
        target=f"user_id={user_id}",
        details=f"+{days} дней",
    )

    return RedirectResponse(f"/admin/users/{user_id}", status_code=303)


@router.post("/{user_id}/balance/grant")
async def grant_balance(
    user_id: int,
    amount: int = Form(...),
    reason: str = Form(""),
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_USER_BALANCE)),
):
    """Ручное начисление/списание бонусного баланса. amount может быть
    отрицательным (коррекция/списание) — итоговый баланс ниже нуля не
    допускаем. Пользователю приходит уведомление в бот."""

    if amount == 0:
        raise HTTPException(status_code=400, detail="Сумма не может быть нулевой")

    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if user is None:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        new_balance = user.balance + amount
        if new_balance < 0:
            raise HTTPException(
                status_code=400,
                detail=f"Недостаточно средств на балансе для списания "
                       f"(сейчас {user.balance}₽)",
            )

        user.balance = new_balance
        tg_id = user.tg_id
        final_balance = user.balance

        await session.commit()

    await write_audit_log(
        admin,
        action="grant_balance",
        target=f"user_id={user_id}",
        details=f"amount={amount:+d} reason={reason!r} итог={final_balance}",
    )

    from app.services.notify import notify_user

    if amount > 0:
        text = (
            f"💰 Вам начислено {amount}₽ на бонусный баланс администратором.\n"
            f"Текущий баланс: {final_balance}₽."
        )
    else:
        text = (
            f"💰 С вашего бонусного баланса списано {abs(amount)}₽ администратором.\n"
            f"Текущий баланс: {final_balance}₽."
        )
    if reason.strip():
        text += f"\n\nКомментарий: {reason.strip()}"

    await notify_user(tg_id, text)

    return RedirectResponse(f"/admin/users/{user_id}", status_code=303)


@router.post("/{user_id}/revoke")
async def revoke_subscription(
    user_id: int,
    admin: AdminUser = Depends(require_permission(Permission.REVOKE_SUBSCRIPTION)),
):
    async with async_session() as session:
        result = await session.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.is_active == True,  # noqa: E712
            )
            .order_by(Subscription.created_at.desc())
        )
        subscription = result.scalars().first()

        if subscription is not None:
            subscription.is_active = False
            await session.commit()

    await write_audit_log(
        admin,
        action="revoke_subscription",
        target=f"user_id={user_id}",
    )

    return RedirectResponse(f"/admin/users/{user_id}", status_code=303)


@router.post("/{user_id}/activate")
async def activate_subscription(
    user_id: int,
    admin: AdminUser = Depends(require_permission(Permission.REVOKE_SUBSCRIPTION)),
):
    now = datetime.datetime.now()

    async with async_session() as session:
        result = await session.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.is_active == False,  # noqa: E712
                Subscription.expiry > now,
            )
            .order_by(Subscription.created_at.desc())
        )
        subscription = result.scalars().first()

        if subscription is not None:
            subscription.is_active = True
            await session.commit()

    await write_audit_log(
        admin,
        action="activate_subscription",
        target=f"user_id={user_id}",
    )

    return RedirectResponse(f"/admin/users/{user_id}", status_code=303)


# ==========================
# Удаление записей — ТОЛЬКО супер-админ (require_super_admin, не через
# делегируемые Permission-чекбоксы)
# ==========================


@router.post("/{user_id}/subscriptions/delete")
async def delete_selected_subscriptions(
    request: Request,
    user_id: int,
    admin: AdminUser = Depends(require_super_admin),
):
    """Ручное удаление конкретно выбранных (чекбоксами) записей.
    Действующую (is_valid=True) подписку удалить нельзя — сначала нужно
    её отозвать; это защита от случайного обрыва живого доступа."""

    form = await request.form()
    sub_ids = [int(x) for x in form.getlist("sub_ids") if x.strip().isdigit()]

    if not sub_ids:
        return RedirectResponse(f"/admin/users/{user_id}", status_code=303)

    async with async_session() as session:
        result = await session.execute(
            select(Subscription).where(
                Subscription.id.in_(sub_ids),
                Subscription.user_id == user_id,
            )
        )
        subs = result.scalars().all()

        blocked = [s for s in subs if s.is_valid]
        if blocked:
            raise HTTPException(
                status_code=400,
                detail="Нельзя удалить действующую подписку — сначала отзовите её",
            )

        deleted_ids = [s.id for s in subs]
        for s in subs:
            await session.delete(s)
        await session.commit()

    await write_audit_log(
        admin,
        action="delete_subscriptions",
        target=f"user_id={user_id}",
        details=f"ids={deleted_ids}",
    )

    return RedirectResponse(
        f"/admin/users/{user_id}?purged={len(deleted_ids)}", status_code=303
    )


async def _purge_old_subscriptions(days: int, user_id: int | None) -> int:
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    now = datetime.datetime.now()

    stmt = delete(Subscription).where(
        Subscription.created_at < cutoff,
        (Subscription.is_active == False) | (Subscription.expiry <= now),  # noqa: E712
    )

    if user_id is not None:
        stmt = stmt.where(Subscription.user_id == user_id)

    async with async_session() as session:
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount or 0


@router.post("/purge")
async def purge_subscriptions_global(
    period: str = Form(...),
    admin: AdminUser = Depends(require_super_admin),
):
    if period not in PURGE_PERIODS:
        raise HTTPException(status_code=400, detail="Некорректный период")

    days = PURGE_PERIODS[period]
    count = await _purge_old_subscriptions(days=days, user_id=None)

    await write_audit_log(
        admin,
        action="purge_subscriptions",
        target="all_users",
        details=f"{PURGE_PERIOD_LABELS[period]}, deleted={count}",
    )

    return RedirectResponse(f"/admin/users?purged={count}", status_code=303)


@router.post("/{user_id}/purge")
async def purge_subscriptions_user(
    user_id: int,
    period: str = Form(...),
    admin: AdminUser = Depends(require_super_admin),
):
    if period not in PURGE_PERIODS:
        raise HTTPException(status_code=400, detail="Некорректный период")

    days = PURGE_PERIODS[period]
    count = await _purge_old_subscriptions(days=days, user_id=user_id)

    await write_audit_log(
        admin,
        action="purge_subscriptions",
        target=f"user_id={user_id}",
        details=f"{PURGE_PERIOD_LABELS[period]}, deleted={count}",
    )

    return RedirectResponse(f"/admin/users/{user_id}?purged={count}", status_code=303)
