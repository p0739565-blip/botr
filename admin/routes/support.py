import datetime
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.admin.auth import require_permission, write_audit_log
from app.admin.models import AdminUser, Permission
from app.config import SUPPORT_MEDIA_DIR
from app.db import async_session
from app.models import SupportAttachment, SupportMessage, SupportTicket

router = APIRouter(prefix="/support", tags=["support"])

CLOSE_PURGE_PERIODS: dict[str, int] = {
    "week": 7,
    "2weeks": 14,
    "month": 30,
    "3months": 90,
}
CLOSE_PURGE_LABELS: dict[str, str] = {
    "week": "закрыты более недели назад",
    "2weeks": "закрыты более 2 недель назад",
    "month": "закрыты более месяца назад",
    "3months": "закрыты более 3 месяцев назад",
}


@router.get("")
async def tickets_list(
    request: Request,
    status_filter: str = "open",
    purged: int | None = None,
    admin: AdminUser = Depends(require_permission(Permission.VIEW_SUPPORT_TICKETS)),
):
    from app.admin.router import templates

    async with async_session() as session:
        stmt = (
            select(SupportTicket)
            .options(selectinload(SupportTicket.user), selectinload(SupportTicket.messages))
            .order_by(SupportTicket.created_at.desc())
        )
        if status_filter in ("open", "closed"):
            stmt = stmt.where(SupportTicket.status == status_filter)

        result = await session.execute(stmt)
        tickets = result.scalars().unique().all()

    return templates.TemplateResponse(
        "support_list.html",
        {
            "request": request,
            "admin": admin,
            "tickets": tickets,
            "status_filter": status_filter,
            "purged": purged,
            "can_manage": admin.has_permission(Permission.MANAGE_SUPPORT_TICKETS),
            "close_purge_periods": CLOSE_PURGE_LABELS,
        },
    )


@router.get("/{ticket_id}")
async def ticket_detail(
    request: Request,
    ticket_id: int,
    delivery_failed: bool = False,
    admin: AdminUser = Depends(require_permission(Permission.VIEW_SUPPORT_TICKETS)),
):
    from app.admin.router import templates

    async with async_session() as session:
        result = await session.execute(
            select(SupportTicket)
            .options(
                selectinload(SupportTicket.user),
                selectinload(SupportTicket.messages).selectinload(
                    SupportMessage.attachments
                ),
                selectinload(SupportTicket.messages).selectinload(SupportMessage.admin),
            )
            .where(SupportTicket.id == ticket_id)
        )
        ticket = result.scalar_one_or_none()

    if ticket is None:
        raise HTTPException(status_code=404, detail="Обращение не найдено")

    return templates.TemplateResponse(
        "support_detail.html",
        {
            "request": request,
            "admin": admin,
            "ticket": ticket,
            "can_manage": admin.has_permission(Permission.MANAGE_SUPPORT_TICKETS),
            "delivery_failed": delivery_failed,
        },
    )


@router.get("/media/{filename}")
async def serve_media(
    filename: str,
    admin: AdminUser = Depends(require_permission(Permission.VIEW_SUPPORT_TICKETS)),
):
    # Защита от path traversal — работаем только с самим именем файла,
    # без вложенных директорий.
    safe_name = Path(filename).name
    file_path = SUPPORT_MEDIA_DIR / safe_name

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден")

    return FileResponse(file_path)


@router.post("/{ticket_id}/reply")
async def reply_to_ticket(
    ticket_id: int,
    text: str = Form(""),
    photo: UploadFile | None = File(None),
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_SUPPORT_TICKETS)),
):
    text = text.strip()
    has_photo = photo is not None and bool(photo.filename)

    if not text and not has_photo:
        raise HTTPException(
            status_code=400,
            detail="Нужно указать текст ответа или приложить скриншот",
        )

    photo_bytes: bytes | None = None
    if has_photo:
        if not (photo.content_type or "").startswith("image/"):
            raise HTTPException(status_code=400, detail="Можно приложить только изображение")
        photo_bytes = await photo.read()
        # Тот же потолок, что Telegram Bot API допускает для фото по
        # multipart-загрузке — смысла принимать больше нет, всё равно
        # не отправится пользователю.
        if len(photo_bytes) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Скриншот слишком большой (максимум 10 МБ)")

    async with async_session() as session:
        result = await session.execute(
            select(SupportTicket)
            .options(selectinload(SupportTicket.user))
            .where(SupportTicket.id == ticket_id)
        )
        ticket = result.scalar_one_or_none()

        if ticket is None:
            raise HTTPException(status_code=404, detail="Обращение не найдено")

        message = SupportMessage(
            ticket_id=ticket.id,
            sender_type="admin",
            admin_id=admin.id,
            text=text or None,
        )
        session.add(message)
        await session.flush()

        if photo_bytes is not None:
            # Тот же паттерн имени файла, что и для вложений от
            # пользователя (см. app.services.support._download_attachment) —
            # случайное имя на диске, оригинальное имя файла нигде не
            # хранится и не используется.
            saved_filename = f"{uuid.uuid4().hex}.jpg"
            (SUPPORT_MEDIA_DIR / saved_filename).write_bytes(photo_bytes)
            session.add(
                SupportAttachment(
                    message_id=message.id,
                    media_type="photo",
                    file_path=saved_filename,
                )
            )

        await session.commit()

        user_tg_id = ticket.user.tg_id

    # Отправляем ответ пользователю в Telegram. Отдельный Bot() здесь —
    # это нормально: одноразовый вызов API, не требует поллинга/диспетчера.
    # Ответ уже сохранён в БД выше — если сама отправка не удастся
    # (пользователь заблокировал бота, сеть и т.п.), это не должно
    # ронять запрос: админ увидит ответ (и вложенный скриншот) в истории
    # обращения в любом случае, просто уведомление могло не дойти.
    from aiogram import Bot
    from aiogram.types import BufferedInputFile

    from app.config import BOT_TOKEN

    caption = f"💬 Ответ поддержки по вашему обращению #{ticket_id}:\n\n{text}" if text \
        else f"💬 Ответ поддержки по вашему обращению #{ticket_id}"

    delivery_failed = False
    bot = Bot(token=BOT_TOKEN)
    try:
        if photo_bytes is not None:
            await bot.send_photo(
                chat_id=user_tg_id,
                photo=BufferedInputFile(photo_bytes, filename="screenshot.jpg"),
                # Telegram обрезает подпись к фото на 1024 символах —
                # текст ответа и так короткий, но на всякий случай режем
                # сами, чтобы не словить ошибку API вместо тихой обрезки.
                caption=caption[:1024],
            )
        else:
            await bot.send_message(chat_id=user_tg_id, text=caption)
    except Exception:
        delivery_failed = True
    finally:
        await bot.session.close()

    await write_audit_log(
        admin,
        action="reply_support_ticket",
        target=f"ticket_id={ticket_id}",
        details="delivery_failed" if delivery_failed else ("with_photo" if photo_bytes else None),
    )

    return RedirectResponse(
        f"/admin/support/{ticket_id}"
        + ("?delivery_failed=1" if delivery_failed else ""),
        status_code=303,
    )


@router.post("/{ticket_id}/close")
async def close_ticket(
    ticket_id: int,
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_SUPPORT_TICKETS)),
):
    async with async_session() as session:
        result = await session.execute(
            select(SupportTicket).where(SupportTicket.id == ticket_id)
        )
        ticket = result.scalar_one_or_none()

        if ticket is None:
            raise HTTPException(status_code=404, detail="Обращение не найдено")

        ticket.status = "closed"
        ticket.closed_at = datetime.datetime.now()
        await session.commit()

    await write_audit_log(
        admin, action="close_support_ticket", target=f"ticket_id={ticket_id}"
    )

    return RedirectResponse(f"/admin/support/{ticket_id}", status_code=303)


@router.post("/{ticket_id}/reopen")
async def reopen_ticket(
    ticket_id: int,
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_SUPPORT_TICKETS)),
):
    async with async_session() as session:
        result = await session.execute(
            select(SupportTicket).where(SupportTicket.id == ticket_id)
        )
        ticket = result.scalar_one_or_none()

        if ticket is None:
            raise HTTPException(status_code=404, detail="Обращение не найдено")

        ticket.status = "open"
        ticket.closed_at = None
        await session.commit()

    await write_audit_log(
        admin, action="reopen_support_ticket", target=f"ticket_id={ticket_id}"
    )

    return RedirectResponse(f"/admin/support/{ticket_id}", status_code=303)


@router.post("/{ticket_id}/delete")
async def delete_ticket(
    ticket_id: int,
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_SUPPORT_TICKETS)),
):
    """Удалить можно только уже закрытое обращение — открытое сначала
    нужно закрыть, чтобы не потерять активный диалог по ошибке."""

    async with async_session() as session:
        result = await session.execute(
            select(SupportTicket)
            .options(
                selectinload(SupportTicket.messages).selectinload(
                    SupportMessage.attachments
                )
            )
            .where(SupportTicket.id == ticket_id)
        )
        ticket = result.scalar_one_or_none()

        if ticket is None:
            raise HTTPException(status_code=404, detail="Обращение не найдено")

        if ticket.status != "closed":
            raise HTTPException(
                status_code=400, detail="Сначала закройте обращение, потом удаляйте"
            )

        # Удаляем файлы вложений с диска перед удалением строк из БД.
        for message in ticket.messages:
            for att in message.attachments:
                file_path = SUPPORT_MEDIA_DIR / Path(att.file_path).name
                file_path.unlink(missing_ok=True)

        await session.delete(ticket)
        await session.commit()

    await write_audit_log(
        admin, action="delete_support_ticket", target=f"ticket_id={ticket_id}"
    )

    return RedirectResponse("/admin/support?status_filter=closed", status_code=303)


@router.post("/purge-closed")
async def purge_closed_tickets(
    period: str = Form(...),
    admin: AdminUser = Depends(require_permission(Permission.MANAGE_SUPPORT_TICKETS)),
):
    if period not in CLOSE_PURGE_PERIODS:
        raise HTTPException(status_code=400, detail="Некорректный период")

    cutoff = datetime.datetime.now() - datetime.timedelta(
        days=CLOSE_PURGE_PERIODS[period]
    )

    async with async_session() as session:
        result = await session.execute(
            select(SupportTicket)
            .options(
                selectinload(SupportTicket.messages).selectinload(
                    SupportMessage.attachments
                )
            )
            .where(
                SupportTicket.status == "closed",
                SupportTicket.closed_at < cutoff,
            )
        )
        tickets = result.scalars().unique().all()

        for ticket in tickets:
            for message in ticket.messages:
                for att in message.attachments:
                    file_path = SUPPORT_MEDIA_DIR / Path(att.file_path).name
                    file_path.unlink(missing_ok=True)
            await session.delete(ticket)

        count = len(tickets)
        await session.commit()

    await write_audit_log(
        admin,
        action="purge_support_tickets",
        target="all",
        details=f"{CLOSE_PURGE_LABELS[period]}, deleted={count}",
    )

    return RedirectResponse(
        f"/admin/support?status_filter=closed&purged={count}", status_code=303
    )
