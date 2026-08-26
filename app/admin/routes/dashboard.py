import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.admin.auth import require_permission
from app.admin.models import AdminRole, AdminUser, AuditLog, Permission
from app.db import async_session
from app.models import Payment, PlategaPayment, ReferralReward, Subscription, SupportTicket, User
from app.settings.tariffs import TARIFFS

router = APIRouter(tags=["dashboard"])

# Способы оплаты, которые реально приходят деньгами в рублях —
# используются для "выручки", в отличие от Stars (отдельная валюта,
# считается и показывается отдельно, как и раньше).
RUB_METHODS = ("card", "sbp", "crypto", "balance")

METHOD_LABELS = {
    "card": "Карта",
    "sbp": "СБП",
    "crypto": "Крипта",
    "balance": "Баланс",
    "stars": "Stars",
}

# Зависшим считаем PENDING старше этого порога — тот же порог
# (MIN_AGE), что использовала фоновая сверка платежей, чтобы виджет
# на дашборде и сама сверка (если/когда включена) были согласованы.
STUCK_PAYMENT_AGE = datetime.timedelta(minutes=10)

# "Скоро истекает" — подписки, которые перестанут работать в этом окне.
EXPIRING_SOON_WINDOW = datetime.timedelta(hours=48)


@router.get("/")
async def dashboard(
    request: Request,
    admin: AdminUser = Depends(require_permission(Permission.VIEW_DASHBOARD)),
):
    from app.admin.router import templates

    now = datetime.datetime.now()
    today_start = datetime.datetime(now.year, now.month, now.day)
    week_start = today_start - datetime.timedelta(days=7)

    async with async_session() as session:
        total_users = (
            await session.execute(select(func.count(User.id)))
        ).scalar_one()

        active_subs = (
            await session.execute(
                select(func.count(Subscription.id)).where(
                    Subscription.is_active == True,  # noqa: E712
                    Subscription.expiry > now,
                )
            )
        ).scalar_one()

        subs_today = (
            await session.execute(
                select(func.count(Subscription.id)).where(
                    Subscription.created_at >= today_start,
                )
            )
        ).scalar_one()

        subs_week = (
            await session.execute(
                select(func.count(Subscription.id)).where(
                    Subscription.created_at >= week_start,
                )
            )
        ).scalar_one()

        stars_today = (
            await session.execute(
                select(func.coalesce(func.sum(Payment.amount), 0)).where(
                    Payment.method == "stars",
                    Payment.created_at >= today_start,
                )
            )
        ).scalar_one()

        stars_total = (
            await session.execute(
                select(func.coalesce(func.sum(Payment.amount), 0)).where(
                    Payment.method == "stars",
                )
            )
        ).scalar_one()

        payments_total = (
            await session.execute(select(func.count(Payment.id)))
        ).scalar_one()

        # ---- Выручка в рублях (карта+СБП+крипта+баланс) ----
        revenue_today = (
            await session.execute(
                select(func.coalesce(func.sum(Payment.amount), 0)).where(
                    Payment.method.in_(RUB_METHODS),
                    Payment.created_at >= today_start,
                )
            )
        ).scalar_one()

        revenue_week = (
            await session.execute(
                select(func.coalesce(func.sum(Payment.amount), 0)).where(
                    Payment.method.in_(RUB_METHODS),
                    Payment.created_at >= week_start,
                )
            )
        ).scalar_one()

        revenue_total = (
            await session.execute(
                select(func.coalesce(func.sum(Payment.amount), 0)).where(
                    Payment.method.in_(RUB_METHODS),
                )
            )
        ).scalar_one()

        # ---- Разбивка по способу оплаты (за всё время) ----
        method_rows = (
            await session.execute(
                select(
                    Payment.method,
                    func.count(Payment.id),
                    func.coalesce(func.sum(Payment.amount), 0),
                ).group_by(Payment.method)
            )
        ).all()
        by_method = [
            {
                "method": method,
                "label": METHOD_LABELS.get(method, method),
                "count": count,
                "amount": amount,
                "is_rub": method in RUB_METHODS,
            }
            for method, count, amount in method_rows
        ]
        by_method.sort(key=lambda r: r["amount"] if r["is_rub"] else 0, reverse=True)

        # ---- График выручки за 7 дней (только рублёвые методы) ----
        chart_labels = []
        chart_values = []
        for i in range(6, -1, -1):
            day_start = today_start - datetime.timedelta(days=i)
            day_end = day_start + datetime.timedelta(days=1)
            day_sum = (
                await session.execute(
                    select(func.coalesce(func.sum(Payment.amount), 0)).where(
                        Payment.method.in_(RUB_METHODS),
                        Payment.created_at >= day_start,
                        Payment.created_at < day_end,
                    )
                )
            ).scalar_one()
            chart_labels.append(day_start.strftime("%d.%m"))
            chart_values.append(day_sum)

        # ---- "Требует внимания" ----
        stuck_payments = (
            await session.execute(
                select(func.count(PlategaPayment.id)).where(
                    PlategaPayment.status == "PENDING",
                    PlategaPayment.created_at <= now - STUCK_PAYMENT_AGE,
                )
            )
        ).scalar_one()

        open_tickets = (
            await session.execute(
                select(func.count(SupportTicket.id)).where(
                    SupportTicket.status == "open",
                )
            )
        ).scalar_one()

        expiring_soon = (
            await session.execute(
                select(func.count(Subscription.id)).where(
                    Subscription.is_active == True,  # noqa: E712
                    Subscription.expiry > now,
                    Subscription.expiry <= now + EXPIRING_SOON_WINDOW,
                )
            )
        ).scalar_one()

        # ---- Сводка по рефералам ----
        invited_today = (
            await session.execute(
                select(func.count(User.id)).where(
                    User.referred_by_id.is_not(None),
                    User.created_at >= today_start,
                )
            )
        ).scalar_one()

        invited_total = (
            await session.execute(
                select(func.count(User.id)).where(User.referred_by_id.is_not(None))
            )
        ).scalar_one()

        referral_rewards_total = (
            await session.execute(select(func.count(ReferralReward.id)))
        ).scalar_one()

        top_referrer_row = (
            await session.execute(
                select(User, func.count(ReferralReward.id).label("cnt"))
                .join(ReferralReward, ReferralReward.referrer_id == User.id)
                .group_by(User.id)
                .order_by(func.count(ReferralReward.id).desc())
                .limit(1)
            )
        ).first()
        top_referrer = None
        if top_referrer_row:
            top_referrer_user, top_referrer_count = top_referrer_row
            top_referrer = {
                "user": top_referrer_user,
                "count": top_referrer_count,
            }

        # ---- Популярность тарифов (по числу платежей, все способы) ----
        tariff_rows = (
            await session.execute(
                select(Payment.tariff_key, func.count(Payment.id))
                .group_by(Payment.tariff_key)
                .order_by(func.count(Payment.id).desc())
            )
        ).all()
        tariff_popularity = [
            {
                "title": TARIFFS.get(key, {}).get("title", key),
                "count": count,
            }
            for key, count in tariff_rows
        ]

        last_cleanups = []
        if admin.role == AdminRole.SUPER_ADMIN:
            cleanups_result = await session.execute(
                select(AuditLog)
                .options(selectinload(AuditLog.admin))
                .where(AuditLog.action == "purge_subscriptions")
                .order_by(AuditLog.created_at.desc())
                .limit(3)
            )
            last_cleanups = cleanups_result.scalars().all()

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "admin": admin,
            "stats": {
                "total_users": total_users,
                "active_subs": active_subs,
                "subs_today": subs_today,
                "subs_week": subs_week,
                "stars_today": stars_today,
                "stars_total": stars_total,
                "payments_total": payments_total,
                "revenue_today": revenue_today,
                "revenue_week": revenue_week,
                "revenue_total": revenue_total,
            },
            "by_method": by_method,
            "chart_labels": chart_labels,
            "chart_values": chart_values,
            "stuck_payments": stuck_payments,
            "open_tickets": open_tickets,
            "expiring_soon": expiring_soon,
            "referral_summary": {
                "invited_today": invited_today,
                "invited_total": invited_total,
                "rewards_total": referral_rewards_total,
                "top_referrer": top_referrer,
            },
            "tariff_popularity": tariff_popularity,
            "last_cleanups": last_cleanups,
        },
    )
