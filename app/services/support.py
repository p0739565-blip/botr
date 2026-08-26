import uuid

from aiogram import Bot
from aiogram.types import Message
from sqlalchemy import select

from app.config import SUPPORT_MEDIA_DIR
from app.db import async_session
from app.models import SupportAttachment, SupportMessage, SupportTicket, User


async def get_open_ticket(user_id: int) -> SupportTicket | None:
    async with async_session() as session:
        result = await session.execute(
            select(SupportTicket)
            .where(
                SupportTicket.user_id == user_id,
                SupportTicket.status == "open",
            )
            .order_by(SupportTicket.created_at.desc())
        )
        return result.scalars().first()


async def create_ticket(user: User, description: str) -> SupportTicket:
    async with async_session() as session:
        ticket = SupportTicket(user_id=user.id, status="open")
        session.add(ticket)
        await session.flush()

        session.add(
            SupportMessage(
                ticket_id=ticket.id,
                sender_type="user",
                text=description,
            )
        )
        await session.commit()
        await session.refresh(ticket)
        return ticket


async def _download_attachment(bot: Bot, file_id: str, extension: str) -> str:
    """Скачивает файл с серверов Telegram на диск и возвращает имя файла
    (не полный путь) — так проще и безопаснее отдавать его потом через
    admin-панель по одному конкретному имени."""

    filename = f"{uuid.uuid4().hex}.{extension}"
    destination = SUPPORT_MEDIA_DIR / filename
    await bot.download(file_id, destination=destination)
    return filename


async def add_user_message(
    bot: Bot,
    ticket_id: int,
    text: str | None,
    photo_file_id: str | None = None,
    video_file_id: str | None = None,
) -> SupportMessage:
    """Добавляет сообщение от пользователя в существующее обращение,
    с необязательным одним фото или видео (вызывается один раз на
    каждое присланное вложение — по одному вызову на файл)."""

    async with async_session() as session:
        message = SupportMessage(
            ticket_id=ticket_id,
            sender_type="user",
            text=text,
        )
        session.add(message)
        await session.flush()

        if photo_file_id:
            filename = await _download_attachment(bot, photo_file_id, "jpg")
            session.add(
                SupportAttachment(
                    message_id=message.id,
                    media_type="photo",
                    file_path=filename,
                )
            )

        if video_file_id:
            filename = await _download_attachment(bot, video_file_id, "mp4")
            session.add(
                SupportAttachment(
                    message_id=message.id,
                    media_type="video",
                    file_path=filename,
                )
            )

        await session.commit()
        await session.refresh(message)
        return message
