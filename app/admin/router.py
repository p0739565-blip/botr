from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

# Импорт регистрирует таблицы админки на том же Base, что и модели бота —
# нужно, чтобы init_models() создал их вместе с users/subscriptions/payments.
from app.admin import models as admin_models  # noqa: F401
from app.admin.auth import get_admin_by_login, verify_password
from app.admin.models import AdminRole, Permission

ADMIN_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(ADMIN_DIR / "templates"))

ROLE_LABELS = {
    AdminRole.SUPER_ADMIN: "Супер-админ",
    AdminRole.ADMIN: "Админ",
    AdminRole.OBSERVER: "Наблюдатель",
    AdminRole.SUPPORT: "Техподдержка",
}

PERMISSION_LABELS = {
    Permission.VIEW_DASHBOARD: "Просмотр дашборда",
    Permission.VIEW_USERS: "Просмотр пользователей",
    Permission.VIEW_SUBSCRIPTIONS: "Просмотр подписок",
    Permission.VIEW_PAYMENTS: "Просмотр платежей",
    Permission.ISSUE_SUBSCRIPTION: "Выдача/продление подписки",
    Permission.MANAGE_USER_BALANCE: "Выдача бонусного баланса",
    Permission.REVOKE_SUBSCRIPTION: "Отзыв/активация подписки",
    Permission.VIEW_SUPPORT_TICKETS: "Просмотр обращений поддержки",
    Permission.MANAGE_SUPPORT_TICKETS: "Ответы/закрытие обращений поддержки",
    Permission.MANAGE_TARIFFS: "Управление тарифами",
    Permission.MANAGE_VLESS_LINKS: "Управление VPN-ссылками",
    Permission.BROADCAST_MESSAGE: "Рассылки",
    Permission.MANAGE_REFERRALS: "Реферальная программа",
    Permission.MANAGE_ADMINS: "Управление админами",
    Permission.VIEW_AUDIT_LOG: "Просмотр журнала действий",
    Permission.MANAGE_SERVER_SETTINGS: "Серверные настройки",
}

templates.env.globals["perm"] = Permission
templates.env.globals["AdminRole"] = AdminRole
templates.env.globals["role_labels"] = ROLE_LABELS
templates.env.globals["permission_labels"] = PERMISSION_LABELS

router = APIRouter(prefix="/admin")


@router.get("/login")
async def login_form(request: Request):
    if request.session.get("admin_id"):
        return RedirectResponse("/admin/", status_code=303)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": None},
    )


@router.post("/login")
async def login_submit(
    request: Request,
    login: str = Form(...),
    password: str = Form(...),
):
    admin = await get_admin_by_login(login.strip())

    if (
        admin is None
        or not admin.is_active
        or not verify_password(password, admin.password_hash)
    ):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Неверный логин или пароль"},
            status_code=401,
        )

    request.session.clear()
    request.session["admin_id"] = admin.id

    return RedirectResponse("/admin/", status_code=303)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)


# Подроуты подключаются здесь, после определения login/logout,
# чтобы избежать циклических импортов (routes/*.py импортируют router
# только для APIRouter(), не наоборот).
from app.admin.routes import admins, audit, broadcasts, dashboard, payments, referrals, support, tariffs, users, vless_links  # noqa: E402

router.include_router(dashboard.router)
router.include_router(users.router)
router.include_router(payments.router)
router.include_router(admins.router)
router.include_router(audit.router)
router.include_router(support.router)
router.include_router(broadcasts.router)
router.include_router(vless_links.router)
router.include_router(tariffs.router)
router.include_router(referrals.router)


async def admin_exception_handler(request: Request, exc):
    """Подключается в app/api.py через app.add_exception_handler().
    Отдаёт красивую HTML-страницу для 403 внутри /admin/*, и штатно
    выполняет редирект на /login для 303 (незалогинен). Для путей вне
    /admin — отдаёт стандартное JSON-поведение FastAPI."""
    from starlette.responses import JSONResponse, RedirectResponse

    if not request.url.path.startswith("/admin"):
        return JSONResponse(
            {"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers
        )

    if exc.status_code == 303 and exc.headers and "Location" in exc.headers:
        return RedirectResponse(exc.headers["Location"], status_code=303)

    if exc.status_code == 403:
        return templates.TemplateResponse(
            "403.html", {"request": request}, status_code=403
        )

    return JSONResponse(
        {"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers
    )
