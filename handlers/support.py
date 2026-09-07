from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.db import async_session
from app.keyboards.inline import (
    support_attachments_keyboard,
    support_conversation_keyboard,
    support_start_keyboard,
)
from app.keyboards.reply import main_menu
from app.models import SupportTicket
from app.services.support import add_user_message, create_ticket, get_open_ticket
from app.services.users import get_or_create_user
from app.texts.messages import (
    SUPPORT_TEXT,
    TICKET_ALREADY_OPEN_TEXT,
    TICKET_ASK_ATTACHMENTS_TEXT,
    TICKET_ASK_DESCRIPTION_TEXT,
    TICKET_ATTACHMENT_RECEIVED_TEXT,
    TICKET_CLOSED_NOTICE_TEXT,
    TICKET_CREATED_TEXT,
    TICKET_EXIT_TEXT,
    TICKET_MESSAGE_FORWARDED_TEXT,
)

router = Router()


class TicketStates(StatesGroup):
    waiting_description = State()
    collecting_attachments = State()
    in_conversation = State()


@router.message(F.text == "🆘 Поддержка")
async def support_entry(message: Message, state: FSMContext):
    user = await get_or_create_user(message.from_user.id, message.from_user.username)

    open_ticket = await get_open_ticket(user.id)

    if open_ticket is not None:
        await state.set_state(TicketStates.in_conversation)
        await state.update_data(ticket_id=open_ticket.id)
        await message.answer(
            TICKET_ALREADY_OPEN_TEXT.format(ticket_id=open_ticket.id),
            reply_markup=support_conversation_keyboard(),
        )
        return

    await message.answer(SUPPORT_TEXT, reply_markup=support_start_keyboard())


@router.callback_query(F.data == "support_new_ticket")
async def start_new_ticket(callback: CallbackQuery, state: FSMContext):
    user = await get_or_create_user(
        callback.from_user.id, callback.from_user.username
    )

    # Повторная проверка на случай, если заявка уже была создана в
    # другом сообщении, пока пользователь смотрел на эту кнопку.
    open_ticket = await get_open_ticket(user.id)
    if open_ticket is not None:
        await state.set_state(TicketStates.in_conversation)
        await state.update_data(ticket_id=open_ticket.id)
        await callback.message.answer(
            TICKET_ALREADY_OPEN_TEXT.format(ticket_id=open_ticket.id),
            reply_markup=support_conversation_keyboard(),
        )
        await callback.answer()
        return

    await state.set_state(TicketStates.waiting_description)
    await callback.message.answer(TICKET_ASK_DESCRIPTION_TEXT)
    await callback.answer()


@router.message(TicketStates.waiting_description, F.text)
async def receive_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text, attachments=[])
    await state.set_state(TicketStates.collecting_attachments)
    await message.answer(
        TICKET_ASK_ATTACHMENTS_TEXT,
        reply_markup=support_attachments_keyboard(),
    )


@router.message(TicketStates.waiting_description)
async def receive_description_wrong_type(message: Message):
    await message.answer(TICKET_ASK_DESCRIPTION_TEXT)


@router.message(TicketStates.collecting_attachments, F.photo)
async def collect_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    attachments = data.get("attachments", [])
    attachments.append({"type": "photo", "file_id": message.photo[-1].file_id})
    await state.update_data(attachments=attachments)

    await message.answer(
        TICKET_ATTACHMENT_RECEIVED_TEXT,
        reply_markup=support_attachments_keyboard(),
    )


@router.message(TicketStates.collecting_attachments, F.video)
async def collect_video(message: Message, state: FSMContext):
    data = await state.get_data()
    attachments = data.get("attachments", [])
    attachments.append({"type": "video", "file_id": message.video.file_id})
    await state.update_data(attachments=attachments)

    await message.answer(
        TICKET_ATTACHMENT_RECEIVED_TEXT,
        reply_markup=support_attachments_keyboard(),
    )


@router.message(TicketStates.collecting_attachments)
async def collect_attachments_wrong_type(message: Message):
    await message.answer(
        TICKET_ASK_ATTACHMENTS_TEXT,
        reply_markup=support_attachments_keyboard(),
    )


@router.callback_query(
    TicketStates.collecting_attachments, F.data == "support_submit_ticket"
)
async def submit_ticket(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    description = data.get("description", "")
    attachments = data.get("attachments", [])

    user = await get_or_create_user(
        callback.from_user.id, callback.from_user.username
    )

    ticket = await create_ticket(user, description)

    for att in attachments:
        await add_user_message(
            bot,
            ticket.id,
            text=None,
            photo_file_id=att["file_id"] if att["type"] == "photo" else None,
            video_file_id=att["file_id"] if att["type"] == "video" else None,
        )

    await state.set_state(TicketStates.in_conversation)
    await state.update_data(ticket_id=ticket.id)

    await callback.message.answer(
        TICKET_CREATED_TEXT.format(ticket_id=ticket.id),
        reply_markup=support_conversation_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "support_exit_conversation")
async def exit_conversation(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer(TICKET_EXIT_TEXT, reply_markup=main_menu())
    await callback.answer()


async def _get_ticket_status(ticket_id: int) -> str | None:
    async with async_session() as session:
        result = await session.execute(
            select(SupportTicket.status).where(SupportTicket.id == ticket_id)
        )
        return result.scalar_one_or_none()


@router.message(TicketStates.in_conversation)
async def forward_message_to_ticket(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    ticket_id = data.get("ticket_id")

    if ticket_id is None:
        # Состояние потеряно (например, рестарт бота без персистентного
        # FSM-хранилища) — выходим в главное меню, не пытаясь угадать.
        await state.clear()
        await message.answer(TICKET_EXIT_TEXT, reply_markup=main_menu())
        return

    status = await _get_ticket_status(ticket_id)

    if status != "open":
        await state.clear()
        await message.answer(
            TICKET_CLOSED_NOTICE_TEXT.format(ticket_id=ticket_id),
            reply_markup=main_menu(),
        )
        return

    photo_file_id = message.photo[-1].file_id if message.photo else None
    video_file_id = message.video.file_id if message.video else None
    text = message.text or message.caption

    if not text and not photo_file_id and not video_file_id:
        # Стикеры, голосовые и т.п. пока не поддерживаем как вложения.
        await message.answer(
            TICKET_ASK_ATTACHMENTS_TEXT,
            reply_markup=support_conversation_keyboard(),
        )
        return

    await add_user_message(
        bot,
        ticket_id,
        text=text,
        photo_file_id=photo_file_id,
        video_file_id=video_file_id,
    )

    await message.answer(
        TICKET_MESSAGE_FORWARDED_TEXT,
        reply_markup=support_conversation_keyboard(),
    )
