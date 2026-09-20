import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.admin.auth import require_permission, write_audit_log
from app.admin.models import AdminUser, Permission
from app.db import async_session
from app.models import PromoCode
from app.services.promo import get_promo_redemptions

router = APIRouter(prefix="/promo-codes", tags=["promo_codes"])


def _parse_int(value: str) -> int | None:
    value = value.strip()
    return int(value) if value else None


@router.get("")
async def list_promo_codes_view(
    request: Request,
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_PROMO_CODES)),
):
    from app.admin.router import templates

    async with async_session() as session:
        result = await session.execute(
            select(PromoCode).order_by(PromoCode.created_at.desc())
        )
        promo_codes = result.scalars().all()

    return templates.TemplateResponse(
        "promo_codes.html",
        {"request": request, "admin": admin, "promo_codes": promo_codes},
    )


@router.get("/new")
async def new_promo_code_form(
    request: Request,
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_PROMO_CODES)),
):
    from app.admin.router import templates

    return templates.TemplateResponse(
        "promo_code_form.html",
        {"request": request, "admin": admin, "target": None, "error": None},
    )


@router.post("/new")
async def create_promo_code(
    request: Request,
    code: str = Form(...),
    discount_percent: str = Form(""),
    bonus_balance: str = Form(""),
    max_activations: str = Form(""),
    expires_at: str = Form(""),
    comment: str = Form(""),
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_PROMO_CODES)),
):
    from app.admin.router import templates

    code = code.strip().upper()

    error = None
    if not code:
        error = "Код не может быть пустым"
    elif len(code) > 32:
        error = "Код слишком длинный (максимум 32 символа)"

    discount_val = _parse_int(discount_percent)
    if discount_val is not None and not (1 <= discount_val <= 100):
        error = "Скидка должна быть от 1 до 100%"

    bonus_val = _parse_int(bonus_balance)
    if bonus_val is not None and bonus_val <= 0:
        error = "Бонус на баланс должен быть больше нуля"

    max_act_val = _parse_int(max_activations)
    if max_act_val is not None and max_act_val <= 0:
        error = "Лимит активаций должен быть больше нуля"

    if discount_val is None and bonus_val is None:
        error = "Нужно указать скидку, бонус на баланс — или оба сразу"

    expires_dt = None
    if expires_at.strip():
        try:
            expires_dt = datetime.datetime.strptime(expires_at.strip(), "%Y-%m-%d")
        except ValueError:
            error = "Неверный формат даты окончания"

    if error:
        return templates.TemplateResponse(
            "promo_code_form.html",
            {"request": request, "admin": admin, "target": None, "error": error},
            status_code=400,
        )

    async with async_session() as session:
        existing = await session.execute(
            select(PromoCode).where(PromoCode.code == code)
        )
        if existing.scalar_one_or_none() is not None:
            return templates.TemplateResponse(
                "promo_code_form.html",
                {
                    "request": request,
                    "admin": admin,
                    "target": None,
                    "error": "Такой код уже существует",
                },
                status_code=400,
            )

        promo = PromoCode(
            code=code,
            discount_percent=discount_val,
            bonus_balance=bonus_val,
            max_activations=max_act_val,
            expires_at=expires_dt,
            comment=comment.strip() or None,
        )
        session.add(promo)
        await session.commit()

    await write_audit_log(
        admin,
        action="create_promo_code",
        target=f"code={code}",
        details=f"discount={discount_val} bonus_balance={bonus_val} max_activations={max_act_val}",
    )

    return RedirectResponse("/admin/promo-codes", status_code=303)


@router.get("/{promo_id}/edit")
async def edit_promo_code_form(
    request: Request,
    promo_id: int,
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_PROMO_CODES)),
):
    from app.admin.router import templates

    async with async_session() as session:
        target = await session.get(PromoCode, promo_id)

    if target is None:
        raise HTTPException(status_code=404, detail="Промокод не найден")

    redemptions = await get_promo_redemptions(promo_id)

    return templates.TemplateResponse(
        "promo_code_form.html",
        {
            "request": request,
            "admin": admin,
            "target": target,
            "redemptions": redemptions,
            "error": None,
        },
    )


@router.post("/{promo_id}/edit")
async def edit_promo_code(
    request: Request,
    promo_id: int,
    discount_percent: str = Form(""),
    bonus_balance: str = Form(""),
    max_activations: str = Form(""),
    expires_at: str = Form(""),
    comment: str = Form(""),
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_PROMO_CODES)),
):
    from app.admin.router import templates

    discount_val = _parse_int(discount_percent)
    if discount_val is not None and not (1 <= discount_val <= 100):
        raise HTTPException(status_code=400, detail="Скидка должна быть от 1 до 100%")

    bonus_val = _parse_int(bonus_balance)
    if bonus_val is not None and bonus_val <= 0:
        raise HTTPException(status_code=400, detail="Бонус на баланс должен быть больше нуля")

    max_act_val = _parse_int(max_activations)
    if max_act_val is not None and max_act_val <= 0:
        raise HTTPException(status_code=400, detail="Лимит активаций должен быть больше нуля")

    if discount_val is None and bonus_val is None:
        raise HTTPException(
            status_code=400,
            detail="Нужно указать скидку, бонус на баланс — или оба сразу",
        )

    expires_dt = None
    if expires_at.strip():
        try:
            expires_dt = datetime.datetime.strptime(expires_at.strip(), "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Неверный формат даты окончания")

    async with async_session() as session:
        target = await session.get(PromoCode, promo_id)
        if target is None:
            raise HTTPException(status_code=404, detail="Промокод не найден")

        # Уже выданные бонусы/скидки за прошлые активации это не
        # затрагивает (см. PromoRedemption.discount_percent_reserved —
        # копия на момент активации) — меняются условия только для
        # будущих активаций этого кода.
        target.discount_percent = discount_val
        target.bonus_balance = bonus_val
        target.max_activations = max_act_val
        target.expires_at = expires_dt
        target.comment = comment.strip() or None

        await session.commit()

    await write_audit_log(
        admin,
        action="edit_promo_code",
        target=f"promo_id={promo_id}",
        details=f"discount={discount_val} bonus_balance={bonus_val} max_activations={max_act_val}",
    )

    return RedirectResponse("/admin/promo-codes", status_code=303)


@router.post("/{promo_id}/toggle")
async def toggle_promo_code(
    promo_id: int,
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_PROMO_CODES)),
):
    async with async_session() as session:
        target = await session.get(PromoCode, promo_id)
        if target is None:
            raise HTTPException(status_code=404, detail="Промокод не найден")

        target.is_active = not target.is_active
        new_status = target.is_active

        await session.commit()

    await write_audit_log(
        admin,
        action="toggle_promo_code",
        target=f"promo_id={promo_id}",
        details=f"is_active={new_status}",
    )

    return RedirectResponse("/admin/promo-codes", status_code=303)


@router.post("/{promo_id}/delete")
async def delete_promo_code(
    promo_id: int,
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_PROMO_CODES)),
):
    async with async_session() as session:
        target = await session.get(PromoCode, promo_id)
        if target is None:
            raise HTTPException(status_code=404, detail="Промокод не найден")

        code = target.code
        # Удаление кода вместе с историей активаций (cascade,
        # см. PromoCode.redemptions) — если код когда-то реально
        # раздавал бонусы, сами начисления на баланс/зарезервированные
        # скидки уже применены или живут независимо, откатывать их
        # задним числом здесь не нужно.
        await session.delete(target)
        await session.commit()

    await write_audit_log(
        admin,
        action="delete_promo_code",
        target=f"code={code}",
        details=None,
    )

    return RedirectResponse("/admin/promo-codes", status_code=303)
