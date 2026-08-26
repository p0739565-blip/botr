import base64
import re
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.admin.router import admin_exception_handler, router as admin_router
from app.config import ADMIN_SESSION_SECRET, CHANNEL_USERNAME
from app.db import async_session, init_models
from app.decoy import render_decoy_page
from app.models import Subscription
from app.vless_links import get_dead_links, render_links
from app.webhooks.platega import router as platega_webhook_router

app = FastAPI(title="VPN subscription server")

app.add_middleware(SessionMiddleware, secret_key=ADMIN_SESSION_SECRET, session_cookie="admin_session")
app.add_exception_handler(StarletteHTTPException, admin_exception_handler)
app.mount(
    "/admin/static",
    StaticFiles(directory=str(Path(__file__).resolve().parent / "admin" / "static")),
    name="admin_static",
)
app.include_router(admin_router)
app.include_router(platega_webhook_router)

TELEGRAM_LINK = f"https://t.me/{CHANNEL_USERNAME}" if CHANNEL_USERNAME else "https://t.me/"

# Заголовок для профиля — намеренно латиницей: HTTP-заголовки должны быть
# ASCII/latin-1, кириллица и эмодзи в них могут привести к ошибке кодирования
# на уровне ASGI-сервера.
PROFILE_TITLE = "Macwin VPN"

CLIENT_UA_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"v2rayN", r"v2rayNG", r"Clash", r"ClashforWindows", r"sing-box",
        r"Shadowrocket", r"Quantumult", r"Surge", r"Stash", r"NekoBox",
        r"NekoRay", r"Hiddify", r"FairVPN", r"Streisand", r"Loon",
        r"Karing", r"Happ", r"okhttp",
    ]
]

# ВАЖНО: одиночное "Mozilla/5.0" НЕ считаем признаком браузера — эту
# строку исторически вставляют в свой User-Agent множество не-браузерных
# HTTP-библиотек (в т.ч. внутри VPN-клиентов) просто для совместимости.
# Настоящий браузер всегда шлёт полный набор токенов вместе — этим и
# отличаем, чтобы не блокировать реальных клиентов по ошибке.
FULL_BROWSER_RE = re.compile(
    r"Mozilla/5\.0.*(AppleWebKit|Gecko).*(Chrome/|Safari/|Firefox/|Edg/|OPR/)",
    re.IGNORECASE,
)


def is_vpn_client(user_agent: str) -> bool:
    if not user_agent:
        return True
    if any(p.search(user_agent) for p in CLIENT_UA_PATTERNS):
        return True
    if FULL_BROWSER_RE.search(user_agent):
        return False
    return True


def build_subscription_response(
    expiry_unix: int,
    device_limit: int | None,
    links: list[str],
) -> Response:
    """Стандартный формат v2ray-подписки: тело — base64 от списка ссылок
    через \\n, метаданные — в заголовках (а не внутри тела как раньше).
    Именно смешивание комментариев с base64 в одном теле чаще всего и
    ломает парсер клиента вроде Happ."""
    raw = "\n".join(links)
    body = base64.b64encode(raw.encode("utf-8")).decode("ascii")

    headers = {
        "Profile-Title": PROFILE_TITLE,
        "Profile-Update-Interval": "6",
        "Subscription-Userinfo": (
            f"upload=0; download=0; total=0; expire={expiry_unix}"
        ),
        "Support-Url": TELEGRAM_LINK,
    }
    if device_limit:
        headers["Device-Limit"] = str(device_limit)

    return Response(content=body, media_type="text/plain; charset=utf-8", headers=headers)


@app.on_event("startup")
async def on_startup() -> None:
    await init_models()


@app.get("/")
async def root(request: Request):
    user_agent = request.headers.get("user-agent", "")
    if not is_vpn_client(user_agent):
        return HTMLResponse(render_decoy_page(TELEGRAM_LINK), status_code=404)
    return Response("Not found", status_code=404)


@app.get("/sub/{token}")
async def get_subscription(token: str, request: Request):
    user_agent = request.headers.get("user-agent", "")
    # Временный лог для диагностики — смотрите через
    # journalctl -u vpnapi.service -f
    print(f"[sub] token={token} user-agent={user_agent!r} is_vpn_client={is_vpn_client(user_agent)}")

    if not is_vpn_client(user_agent):
        return HTMLResponse(render_decoy_page(TELEGRAM_LINK), status_code=404)

    async with async_session() as session:
        result = await session.execute(
            select(Subscription)
            .options(joinedload(Subscription.user))
            .where(Subscription.token == token)
        )
        subscription = result.scalar_one_or_none()

    if subscription is None or not subscription.is_valid:
        return build_subscription_response(0, None, await get_dead_links())

    links = await render_links(subscription.user.vless_uuid)
    expiry_unix = int(subscription.expiry.timestamp())
    return build_subscription_response(
        expiry_unix, subscription.device_limit, links
    )


_PLATEGA_RETURN_PAGE = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title></head>
<body style="font-family: sans-serif; text-align: center; padding-top: 15vh;">
<h2>{title}</h2>
<p>{message}</p>
<p><a href="{bot_link}">Вернуться в бота</a></p>
</body></html>"""


@app.get("/payments/platega/return")
async def platega_return():
    """Страница, на которую Platega редиректит после успешной оплаты.
    Подписка выдаётся не здесь, а по вебхуку (см. app.webhooks.platega) —
    эта страница чисто информационная, чтобы пользователь не застрял
    на пустом экране."""
    return HTMLResponse(
        _PLATEGA_RETURN_PAGE.format(
            title="Оплата прошла",
            message="Подписка придёт в чат с ботом в течение пары минут.",
            bot_link=TELEGRAM_LINK,
        )
    )


@app.get("/payments/platega/failed")
async def platega_failed():
    return HTMLResponse(
        _PLATEGA_RETURN_PAGE.format(
            title="Оплата не прошла",
            message="Попробуйте ещё раз или выберите другой способ оплаты в боте.",
            bot_link=TELEGRAM_LINK,
        )
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
