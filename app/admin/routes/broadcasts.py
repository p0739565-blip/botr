import asyncio
import datetime
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.admin.auth import require_permission, write_audit_log
from app.admin.models import AdminUser, Broadcast, BroadcastAudience, BroadcastStatus, Permission
from app.config import BROADCAST_MEDIA_DIR
from app.db import async_session
from app.services.broadcast import count_audience, run_broadcast, send_test_message
from app.settings.tariffs import TARIFFS

router = APIRouter(prefix="/broadcasts", tags=["broadcasts"])

AUDIENCE_LABELS: dict[BroadcastAudience, str] = {
    BroadcastAudience.ALL: "Все пользователи",
    BroadcastAudience.ACTIVE_SUBSCRIPTION: "С активной подпиской",
    BroadcastAudience.NO_ACTIVE_SUBSCRIPTION: "Без активной подписки (истекла или не было)",
    BroadcastAudience.NEVER_SUBSCRIBED: "Никогда не оформляли подписку",
    BroadcastAudience.PAYING: "Хотя бы раз платили",
}

STATUS_LABELS: dict[BroadcastStatus, str] = {
    BroadcastStatus.DRAFT: "черновик",
    BroadcastStatus.SENDING: "отправляется",
    BroadcastStatus.COMPLETED: "завершена",
}


def _parse_date(value: str) -> datetime.datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Некорректная дата: {value!r}")


async def _save_photo(photo: UploadFile | None) -> str | None:
    if photo is None or not photo.filename:
        return None

    content_type = (photo.content_type or "").lower()
    if content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(
            status_code=400,
            detail="Фото должно быть в формате JPEG, PNG или WebP",
        )

    extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[content_type]
    filename = f"{uuid.uuid4().hex}.{extension}"
    destination = BROADCAST_MEDIA_DIR / filename

    data = await photo.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Фото больше 10 МБ")

    destination.write_bytes(data)
    return filename


@router.get("")
async def broadcasts_list(
    request: Request,
    admin: AdminUser = Depends(require_permission(Permission.BROADCAST_MESSAGE)),
):
    from app.admin.router import templates

    async with async_session() as session:
        result = await session.execute(
            select(Broadcast)
            .options(selectinload(Broadcast.admin))
            .order_by(Broadcast.created_at.desc())
        )
        broadcasts = result.scalars().all()

    return templates.TemplateResponse(
        "broadcast_list.html",
        {
            "request": request,
            "admin": admin,
            "broadcasts": broadcasts,
            "audience_labels": AUDIENCE_LABELS,
            "status_labels": STATUS_LABELS,
        },
    )


@router.get("/new")
async def new_broadcast_form(
    request: Request,
    admin: AdminUser = Depends(require_permission(Permission.BROADCAST_MESSAGE)),
):
    from app.admin.router import templates

    return templates.TemplateResponse(
        "broadcast_form.html",
        {
            "request": request,
            "admin": admin,
            "audiences": BroadcastAudience,
            "audience_labels": AUDIENCE_LABELS,
            "tariffs": TARIFFS,
            "error": None,
            "form_values": {},
        },
    )


@router.post("")
async def create_broadcast(
    request: Request,
    text: str = Form(...),
    parse_mode: str = Form("plain"),
    audience: str = Form(...),
    tariff_filter: str = Form(""),
    registered_from: str = Form(""),
    registered_to: str = Form(""),
    button_text: str = Form(""),
    button_url: str = Form(""),
    photo: UploadFile | None = None,
    admin: AdminUser = Depends(require_permission(Permission.BROADCAST_MESSAGE)),
):
    from app.admin.router import templates

    def _form_error(message: str):
        return templates.TemplateResponse(
            "broadcast_form.html",
            {
                "request": request,
                "admin": admin,
                "audiences": BroadcastAudience,
                "audience_labels": AUDIENCE_LABELS,
                "tariffs": TARIFFS,
                "error": message,
                "form_values": {
                    "text": text,
                    "parse_mode": parse_mode,
                    "audience": audience,
                    "tariff_filter": tariff_filter,
                    "registered_from": registered_from,
                    "registered_to": registered_to,
                    "button_text": button_text,
                    "button_url": button_url,
                },
            },
            status_code=400,
        )

    text = text.strip()
    if not text:
        return _form_error("Текст сообщения не может быть пустым")
    if len(text) > 4096:
        return _form_error("Текст сообщения длиннее 4096 символов (лимит Telegram)")

    try:
        audience_enum = BroadcastAudience(audience)
    except ValueError:
        return _form_error("Некорректная аудитория")

    tariff_filter = tariff_filter.strip()
    if tariff_filter and tariff_filter not in TARIFFS:
        return _form_error("Некорректный тариф в фильтре")

    button_text = button_text.strip()
    button_url = button_url.strip()
    if bool(button_text) != bool(button_url):
        return _form_error("Для кнопки нужно заполнить и текст, и ссылку — или оставить оба поля пустыми")
    if button_url and not (button_url.startswith("http://") or button_url.startswith("https://")):
        return _form_error("Ссылка на кнопку должна начинаться с http:// или https://")

    try:
        from_dt = _parse_date(registered_from)
        to_dt = _parse_date(registered_to)
    except HTTPException as e:
        return _form_error(e.detail)

    if from_dt and to_dt and from_dt > to_dt:
        return _form_error("Дата «с» позже даты «по»")
    if to_dt:
        # Включаем весь день до 23:59:59, а не полночь начала дня.
        to_dt = to_dt + datetime.timedelta(days=1, seconds=-1)

    try:
        photo_path = await _save_photo(photo)
    except HTTPException as e:
        return _form_error(e.detail)

    broadcast = Broadcast(
        admin_id=admin.id,
        text=text,
        parse_mode="HTML" if parse_mode == "html" else None,
        photo_path=photo_path,
        button_text=button_text or None,
        button_url=button_url or None,
        audience=audience_enum,
        tariff_filter=tariff_filter or None,
        registered_from=from_dt,
        registered_to=to_dt,
        status=BroadcastStatus.DRAFT,
    )

    async with async_session() as session:
        session.add(broadcast)
        await session.flush()
        broadcast.total_recipients = await count_audience(session, broadcast)
        await session.commit()
        broadcast_id = broadcast.id

    await write_audit_log(
        admin,
        action="create_broadcast_draft",
        target=f"broadcast_id={broadcast_id}",
        details=f"audience={audience_enum.value}, recipients={broadcast.total_recipients}",
    )

    return RedirectResponse(f"/admin/broadcasts/{broadcast_id}", status_code=303)


@router.get("/media/{filename}")
async def serve_broadcast_media(
    filename: str,
    admin: AdminUser = Depends(require_permission(Permission.BROADCAST_MESSAGE)),
):
    safe_name = Path(filename).name
    file_path = BROADCAST_MEDIA_DIR / safe_name
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден")
    return FileResponse(file_path)


@router.get("/{broadcast_id}")
async def broadcast_detail(
    request: Request,
    broadcast_id: int,
    test_sent: int | None = None,
    admin: AdminUser = Depends(require_permission(Permission.BROADCAST_MESSAGE)),
):
    from app.admin.router import templates

    async with async_session() as session:
        result = await session.execute(
            select(Broadcast)
            .options(selectinload(Broadcast.admin))
            .where(Broadcast.id == broadcast_id)
        )
        broadcast = result.scalar_one_or_none()

    if broadcast is None:
        raise HTTPException(status_code=404, detail="Рассылка не найдена")

    return templates.TemplateResponse(
        "broadcast_detail.html",
        {
            "request": request,
            "admin": admin,
            "b": broadcast,
            "audience_labels": AUDIENCE_LABELS,
            "status_labels": STATUS_LABELS,
            "tariffs": TARIFFS,
            "test_sent": test_sent,
        },
    )


@router.post("/{broadcast_id}/send")
async def send_broadcast(
    broadcast_id: int,
    admin: AdminUser = Depends(require_permission(Permission.BROADCAST_MESSAGE)),
):
    async with async_session() as session:
        broadcast = await session.get(Broadcast, broadcast_id)
        if broadcast is None:
            raise HTTPException(status_code=404, detail="Рассылка не найдена")
        if broadcast.status != BroadcastStatus.DRAFT:
            raise HTTPException(
                status_code=400, detail="Эта рассылка уже отправлена или отправляется"
            )

    # Не ждём завершения здесь — рассылка может идти минуты для большой
    # аудитории, а HTTP-запрос админа должен ответить сразу. Прогресс
    # админ смотрит на странице деталей (она сама себя обновляет).
    asyncio.create_task(run_broadcast(broadcast_id))

    await write_audit_log(
        admin, action="start_broadcast", target=f"broadcast_id={broadcast_id}"
    )

    return RedirectResponse(f"/admin/broadcasts/{broadcast_id}", status_code=303)


@router.post("/{broadcast_id}/test")
async def test_broadcast(
    broadcast_id: int,
    test_tg_id: str = Form(...),
    admin: AdminUser = Depends(require_permission(Permission.BROADCAST_MESSAGE)),
):
    async with async_session() as session:
        broadcast = await session.get(Broadcast, broadcast_id)
        if broadcast is None:
            raise HTTPException(status_code=404, detail="Рассылка не найдена")

    try:
        chat_id = int(test_tg_id.strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Telegram ID должен быть числом")

    ok = await send_test_message(chat_id, broadcast)

    await write_audit_log(
        admin,
        action="test_broadcast",
        target=f"broadcast_id={broadcast_id}",
        details=f"tg_id={chat_id}, ok={ok}",
    )

    return RedirectResponse(
        f"/admin/broadcasts/{broadcast_id}?test_sent={1 if ok else 0}", status_code=303
    )


@router.post("/{broadcast_id}/delete")
async def delete_broadcast(
    broadcast_id: int,
    admin: AdminUser = Depends(require_permission(Permission.BROADCAST_MESSAGE)),
):
    """Удалить можно только черновик — уже запущенную или завершённую
    рассылку сознательно храним как историю (видно, что и кому уходило)."""

    async with async_session() as session:
        broadcast = await session.get(Broadcast, broadcast_id)
        if broadcast is None:
            raise HTTPException(status_code=404, detail="Рассылка не найдена")

        if broadcast.status != BroadcastStatus.DRAFT:
            raise HTTPException(
                status_code=400, detail="Нельзя удалить уже отправленную рассылку"
            )

        if broadcast.photo_path:
            (BROADCAST_MEDIA_DIR / broadcast.photo_path).unlink(missing_ok=True)

        await session.delete(broadcast)
        await session.commit()

    await write_audit_log(
        admin, action="delete_broadcast_draft", target=f"broadcast_id={broadcast_id}"
    )

    return RedirectResponse("/admin/broadcasts", status_code=303)
