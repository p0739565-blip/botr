from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import case, func, select

from app.admin.auth import require_permission, write_audit_log
from app.admin.models import AdminUser, Permission
from app.db import async_session
from app.models import ReferralReward, User
from app.services.settings import get_setting_int, set_setting

router = APIRouter(prefix="/referrals", tags=["referrals"])


async def _top_referrers(limit: int = 20) -> list[dict]:
    """Топ рефереров по числу оплативших приглашённых — считаем по
    ReferralReward (запись создаётся только при реальном начислении,
    т.е. только за оплативших), не по всем приглашённым подряд.
    Отдельно суммируем начисления по каждому режиму — у одного
    реферера в истории могут быть строки обоих типов, если он
    переключал режим."""

    async with async_session() as session:
        result = await session.execute(
            select(
                User,
                func.count(ReferralReward.id).label("rewarded_count"),
                func.coalesce(
                    func.sum(
                        case((ReferralReward.reward_type == "days", ReferralReward.bonus_days), else_=0)
                    ),
                    0,
                ).label("total_days"),
                func.coalesce(
                    func.sum(
                        case((ReferralReward.reward_type == "balance", ReferralReward.bonus_balance), else_=0)
                    ),
                    0,
                ).label("total_balance"),
            )
            .join(ReferralReward, ReferralReward.referrer_id == User.id)
            .group_by(User.id)
            .order_by(func.count(ReferralReward.id).desc())
            .limit(limit)
        )
        rows = result.all()

    return [
        {
            "user": user,
            "rewarded_count": rewarded_count,
            "total_days": total_days,
            "total_balance": total_balance,
        }
        for user, rewarded_count, total_days, total_balance in rows
    ]


@router.get("")
async def referral_settings(
    request: Request,
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_REFERRALS)),
):
    from app.admin.router import templates

    bonus_days = await get_setting_int("referral_bonus_days")
    bonus_percent = await get_setting_int("referral_bonus_percent")

    async with async_session() as session:
        total_referred = (
            await session.execute(
                select(func.count(User.id)).where(User.referred_by_id.is_not(None))
            )
        ).scalar_one()

        total_rewarded = (
            await session.execute(select(func.count(ReferralReward.id)))
        ).scalar_one()

        total_bonus_days_given = (
            await session.execute(
                select(func.coalesce(func.sum(ReferralReward.bonus_days), 0)).where(
                    ReferralReward.reward_type == "days"
                )
            )
        ).scalar_one()

        total_bonus_balance_given = (
            await session.execute(
                select(func.coalesce(func.sum(ReferralReward.bonus_balance), 0)).where(
                    ReferralReward.reward_type == "balance"
                )
            )
        ).scalar_one()

        days_mode_users = (
            await session.execute(
                select(func.count(User.id)).where(User.referral_reward_mode == "days")
            )
        ).scalar_one()

        balance_mode_users = (
            await session.execute(
                select(func.count(User.id)).where(User.referral_reward_mode == "balance")
            )
        ).scalar_one()

    top = await _top_referrers()

    return templates.TemplateResponse(
        "referrals.html",
        {
            "request": request,
            "admin": admin,
            "bonus_days": bonus_days,
            "bonus_percent": bonus_percent,
            "total_referred": total_referred,
            "total_rewarded": total_rewarded,
            "total_bonus_days_given": total_bonus_days_given,
            "total_bonus_balance_given": total_bonus_balance_given,
            "days_mode_users": days_mode_users,
            "balance_mode_users": balance_mode_users,
            "top": top,
        },
    )


@router.post("")
async def save_referral_settings(
    bonus_days: str = Form(...),
    bonus_percent: str = Form(...),
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_REFERRALS)),
):
    try:
        days_int = max(0, int(bonus_days))
    except ValueError:
        days_int = 0

    try:
        percent_int = max(0, min(100, int(bonus_percent)))
    except ValueError:
        percent_int = 0

    await set_setting("referral_bonus_days", str(days_int))
    await set_setting("referral_bonus_percent", str(percent_int))

    await write_audit_log(
        admin,
        action="edit_referral_settings",
        target="referral_bonus_days,referral_bonus_percent",
        details=f"bonus_days={days_int} bonus_percent={percent_int}",
    )

    return RedirectResponse("/admin/referrals", status_code=303)
