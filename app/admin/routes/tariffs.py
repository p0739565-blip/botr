from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.admin.auth import require_permission, write_audit_log
from app.admin.models import AdminUser, Permission
from app.services.tariffs import get_tariffs, set_tariff_override
from app.settings.tariffs import TARIFFS as DEFAULT_TARIFFS

router = APIRouter(prefix="/tariffs", tags=["tariffs"])


@router.get("")
async def list_tariffs(
    request: Request,
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_TARIFFS)),
):
    from app.admin.router import templates

    tariffs = await get_tariffs()

    return templates.TemplateResponse(
        "tariffs.html",
        {
            "request": request,
            "admin": admin,
            "tariffs": tariffs,
            "defaults": DEFAULT_TARIFFS,
        },
    )


@router.get("/{tariff_key}/edit")
async def edit_tariff_form(
    request: Request,
    tariff_key: str,
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_TARIFFS)),
):
    from app.admin.router import templates

    tariffs = await get_tariffs()
    tariff = tariffs.get(tariff_key)

    if tariff is None:
        raise HTTPException(status_code=404, detail="Тариф не найден")

    return templates.TemplateResponse(
        "tariff_form.html",
        {
            "request": request,
            "admin": admin,
            "tariff_key": tariff_key,
            "tariff": tariff,
            "default": DEFAULT_TARIFFS[tariff_key],
        },
    )


@router.post("/{tariff_key}/edit")
async def edit_tariff(
    tariff_key: str,
    card_price: str = Form(""),
    stars_price: str = Form(""),
    balance_price: str = Form(""),
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_TARIFFS)),
):
    if tariff_key not in DEFAULT_TARIFFS:
        raise HTTPException(status_code=404, detail="Тариф не найден")

    # Пустое поле = сброс на дефолтную цену (см. докстринг
    # set_tariff_override / модель TariffPrice).
    card_price_int = int(card_price) if card_price.strip() else None
    stars_price_int = int(stars_price) if stars_price.strip() else None
    balance_price_int = int(balance_price) if balance_price.strip() else None

    await set_tariff_override(
        tariff_key,
        card_price=card_price_int,
        stars_price=stars_price_int,
        balance_price=balance_price_int,
    )

    await write_audit_log(
        admin,
        action="edit_tariff_price",
        target=f"tariff_key={tariff_key}",
        details=f"card={card_price_int} stars={stars_price_int} balance={balance_price_int}",
    )

    return RedirectResponse("/admin/tariffs", status_code=303)
