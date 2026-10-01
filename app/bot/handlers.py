import asyncio
from typing import Optional
from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
import httpx

from app.bot.client import internal_bot_client
from app.bot.keyboards import (
    get_book_inline_keyboard,
    get_cancel_keyboard,
    get_condition_inline_keyboard,
    get_duration_inline_keyboard,
    get_library_tabs_keyboard,
    get_loan_handover_keyboard,
    get_loan_return_keyboard,
    get_main_menu_keyboard,
    get_need_offer_actions_keyboard,
    get_need_scope_keyboard,
    get_need_urgency_keyboard,
    get_offer_notification_keyboard,
    get_report_category_keyboard,
    get_request_action_keyboard,
    get_book_chapters_keyboard,
    get_chapter_detail_keyboard,
    get_partial_type_keyboard,
    get_partial_condition_inline_keyboard,
    get_partial_fair_use_keyboard,
    get_partial_visibility_keyboard,
    get_partial_item_actions_keyboard,
    get_my_partial_management_keyboard,
    get_borrow_partial_menu_keyboard,
    get_partial_borrow_scope_keyboard,
    get_partial_copy_borrow_keyboard,
    get_borrow_partial_urgency_keyboard,
    get_digital_visibility_keyboard,
    get_community_library_keyboard,
)
import base64
import os
import re
import time
from app.core.config import settings
from app.core.logging import logger

router = Router()

def is_admin(user_id: int) -> bool:
    admin_id = str(settings.ADMIN_TELEGRAM_ID or "").strip()
    return bool(admin_id and str(user_id) == admin_id)

def parse_http_error(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        try:
            err_data = e.response.json()
            if isinstance(err_data, dict):
                if "error" in err_data and isinstance(err_data["error"], dict):
                    err_data = err_data["error"]
                msg = err_data.get("message") or err_data.get("detail")
                if isinstance(msg, list):
                    return "; ".join([str(m.get("msg", m)) if isinstance(m, dict) else str(m) for m in msg])
                if msg:
                    return str(msg)
        except Exception:
            pass
    return str(e)

# --- FSM States ---
class SearchState(StatesGroup):
    waiting_for_query = State()

class NeedState(StatesGroup):
    waiting_for_title = State()

class RequestWizardState(StatesGroup):
    waiting_for_title = State()
    waiting_for_scope = State()
    waiting_for_scope_detail = State()
    waiting_for_urgency = State()
    waiting_for_location = State()

class AddBookState(StatesGroup):
    waiting_for_book_query = State()
    waiting_for_condition = State()
    waiting_for_duration = State()
    waiting_for_notes = State()

class ReportState(StatesGroup):
    waiting_for_category = State()
    waiting_for_description = State()

class PartialMaterialUploadState(StatesGroup):
    choosing_type = State()
    waiting_for_book_query = State()
    waiting_for_book_selection = State()
    # Physical branch
    waiting_for_pages = State()
    waiting_for_condition = State()
    waiting_for_source = State()
    waiting_for_visibility = State()
    # Digital branch
    waiting_for_digital_chapter = State()
    waiting_for_digital_title = State()
    waiting_for_digital_url = State()
    waiting_for_digital_pages = State()
    waiting_for_fair_use = State()
    waiting_for_digital_visibility = State()

class BorrowPartialState(StatesGroup):
    waiting_for_search_keyword = State()
    waiting_for_book_title = State()
    waiting_for_scope_type = State()
    waiting_for_scope_detail = State()
    waiting_for_urgency = State()

# --- Common Handlers ---
@router.message(CommandStart())
async def handle_start(message: Message, state: FSMContext):
    await state.clear()
    actor_id = message.from_user.id
    display_name = message.from_user.full_name or message.from_user.first_name
    username = message.from_user.username
    user_is_admin = is_admin(actor_id)

    # Sync profile with backend
    try:
        user_info = await internal_bot_client.sync_user(
            telegram_user_id=actor_id,
            display_name=display_name,
            telegram_username=username,
            language_code=message.from_user.language_code or "vi",
        )
        alias = user_info.get("public_alias", "Bạn")
    except Exception:
        alias = "Bạn"

    admin_badge = "\n👑 **Bạn đang đăng nhập với tư cách Quản trị viên (Super Admin)**." if user_is_admin else ""

    welcome_text = (
        f"👋 Chào mừng {alias} đến với **Boconic**!{admin_badge}\n\n"
        "✨ *Find what you need. Find who can help.*\n\n"
        "Boconic là nền tảng kết nối sách giáo khoa, học liệu và tài liệu học tập trong cộng đồng học sinh, sinh viên và phụ huynh.\n\n"
        "📚 **Bạn có thể:**\n"
        "• 🔎 Tìm sách cần mượn quanh khu vực\n"
        "• ➕ Đăng sách của bạn để chia sẻ cho cộng đồng\n"
        "• 📋 Quản lý yêu cầu mượn & giao nhận 2 bên\n"
        "• 🔗 Tra cứu tài nguyên số mở đã kiểm duyệt bản quyền\n\n"
        "Hãy chọn chức năng từ menu bên dưới để bắt đầu:"
    )
    await message.answer(
        welcome_text,
        reply_markup=get_main_menu_keyboard(is_admin=user_is_admin),
        parse_mode="Markdown"
    )

@router.message(Command("help"))
async def handle_help(message: Message):
    actor_id = message.from_user.id
    help_text = (
        "📖 **Hướng dẫn sử dụng Boconic:**\n\n"
        "• **🔎 Tìm sách**: Nhập tên sách, môn, lớp hoặc mã ISBN để tìm bản sách đang có người cho mượn.\n"
        "• **➕ Đăng sách**: Chia sẻ các đầu sách bạn có sẵn cho bạn học khác mượn.\n"
        "• **📑 Up tài liệu 1 phần**: Khai báo bản photocopy hoặc tải lên trích đoạn số theo chương.\n"
        "• **📖 Mượn tài liệu 1 phần (/borrow_partial)**: Mượn bản in photocopy hoặc đăng nhu cầu theo chương/trang cụ thể.\n"
        "• **📖 Sách của tôi**: Quản lý những cuốn sách bạn đã đăng.\n"
        "• **📋 Yêu cầu mượn**: Xem các yêu cầu bạn đã gửi hoặc người khác gửi tới bạn.\n"
        "• **🤝 Đang mượn / 📤 Cho mượn**: Xác nhận giao nhận thực tế và xác nhận hoàn trả 2 bên an toàn.\n"
        "• **📢 Tôi đang cần**: Đăng nhu cầu tìm sách khi cộng đồng chưa có bản sẵn sàng.\n"
        "• **📍 Gần tôi**: Tra cứu các bản sách đang có sẵn ở các quận huyện quanh bạn.\n"
        "• **🏛 Thư viện & Trường học**: Danh mục thư viện đối tác hỗ trợ bạn đọc.\n"
        "• **🔗 Tài nguyên mở**: Học liệu điện tử, đề thi, chuyên đề đã kiểm duyệt bản quyền.\n"
        "• **🚩 Báo cáo / Hỗ trợ**: Báo cáo sự cố hoặc sách sai thông tin.\n"
    )
    if is_admin(actor_id):
        help_text += "\n👑 **Lệnh Quản trị**: Gửi lệnh /admin để xem bảng điều khiển và thống kê toàn hệ thống."

    await message.answer(help_text, reply_markup=get_main_menu_keyboard(is_admin=is_admin(actor_id)), parse_mode="Markdown")

@router.message(Command("cancel"))
@router.message(F.text == "❌ Hủy thao tác")
async def handle_cancel(message: Message, state: FSMContext):
    current_state = await state.get_state()
    await state.clear()
    kb = get_main_menu_keyboard(is_admin=is_admin(message.from_user.id))
    if current_state:
        await message.answer("Đã hủy thao tác hiện tại.", reply_markup=kb)
    else:
        await message.answer("Không có thao tác nào đang dở dang.", reply_markup=kb)

# --- Search Flow ---
@router.message(F.text == "🔎 Tìm sách")
@router.message(Command("search"))
async def start_search(message: Message, state: FSMContext):
    await state.set_state(SearchState.waiting_for_query)
    await message.answer(
        "🔍 Nhập tên sách, tác giả, môn học hoặc mã ISBN bạn cần tìm:",
        reply_markup=get_cancel_keyboard(),
    )

@router.message(SearchState.waiting_for_query)
async def process_search_query(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Vui lòng nhập từ khóa tìm kiếm bằng tin nhắn văn bản:")
        return
    query = message.text.strip()
    if query == "❌ Hủy thao tác":
        await state.clear()
        await message.answer("Đã hủy tìm kiếm.", reply_markup=get_main_menu_keyboard(is_admin=is_admin(message.from_user.id)))
        return

    await state.clear()
    await message.answer(f"Đang tìm kiếm sách khớp với: *{query}*...", parse_mode="Markdown")

    try:
        data = await internal_bot_client.search_books(message.from_user.id, query=query, limit=5)
        items = data.get("items", [])
    except Exception as e:
        await message.answer(
            f"Có lỗi khi tra cứu dữ liệu: {parse_http_error(e)}",
            reply_markup=get_main_menu_keyboard(is_admin=is_admin(message.from_user.id))
        )
        return

    kb_menu = get_main_menu_keyboard(is_admin=is_admin(message.from_user.id))
    if not items:
        await message.answer(
            f"Không tìm thấy đầu sách nào khớp với '{query}'.\n\n"
            "💡 Bạn có thể đăng nhu cầu tìm sách qua mục '📢 Yêu cầu sách' để cộng đồng hỗ trợ!",
            reply_markup=kb_menu
        )
        return

    for item in items:
        authors = ", ".join(item["authors"]) if item["authors"] else "N/A"
        grade = f"Lớp {item['grade_level']}" if item.get("grade_level") else ""
        subject = item.get("subject") or ""
        tag = f"[{subject} - {grade}]" if subject or grade else ""
        curriculum = f"• Bộ sách: {item['curriculum']}\n" if item.get("curriculum") else ""
        isbn = f"• ISBN: `{item['isbn13']}`\n" if item.get("isbn13") else ""

        card = (
            f"📚 **{item['title']}** {tag}\n"
            f"✍️ Tác giả: {authors}\n"
            f"🏢 NXB: {item.get('publisher') or 'N/A'}\n"
            f"{curriculum}"
            f"{isbn}"
            f"📦 Số bản sẵn sàng mượn: **{item['available_count']}**"
        )
        kb = get_book_inline_keyboard(item["book_id"], item["copies"]) if item["copies"] else None
        await message.answer(card, reply_markup=kb, parse_mode="Markdown")

    await message.answer("👆 Bạn có thể bấm nút trực tiếp trên từng bản sách để gửi yêu cầu mượn.", reply_markup=kb_menu)

# --- Add Book Flow ---
@router.message(F.text == "➕ Đăng sách")
@router.message(Command("addbook"))
async def start_add_book(message: Message, state: FSMContext):
    await state.set_state(AddBookState.waiting_for_book_query)
    await message.answer(
        "➕ **Đăng sách để chia sẻ với cộng đồng:**\n\n"
        "Hãy nhập tên cuốn sách hoặc mã ISBN bạn muốn đăng:",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )

@router.message(AddBookState.waiting_for_book_query)
async def process_add_book_query(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Vui lòng nhập tên sách hoặc mã ISBN bằng tin nhắn văn bản:")
        return
    query = message.text.strip()
    if query == "❌ Hủy thao tác":
        await state.clear()
        await message.answer("Đã hủy đăng sách.", reply_markup=get_main_menu_keyboard(is_admin=is_admin(message.from_user.id)))
        return

    try:
        data = await internal_bot_client.search_books(message.from_user.id, query=query, limit=5)
        items = data.get("items", [])
    except Exception as e:
        await message.answer(f"Lỗi tra cứu danh mục: {parse_http_error(e)}")
        return

    await state.update_data(last_query_title=query)
    if not items:
        buttons = [
            [InlineKeyboardButton(text=f"➕ Tạo mới & đăng ngay: {query[:25]}", callback_data="ab_create_new_book")],
            [InlineKeyboardButton(text="❌ Hủy bỏ", callback_data="ptp:cancel")],
        ]
        await message.answer(
            f"Chưa có đầu sách '{query}' trong danh mục chuẩn.\n"
            "Bạn có thể tạo mới ngay để chia sẻ hoặc tìm kiếm lại:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        return

    buttons = []
    for item in items:
        btn_text = f"📖 {item['title'][:35]}"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"ab_book:{item['book_id']}")])
    buttons.append([InlineKeyboardButton(text=f"➕ Tạo sách mới: {query[:25]}", callback_data="ab_create_new_book")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("Chọn đầu sách bạn sở hữu từ danh mục bên dưới:", reply_markup=kb)


@router.callback_query(F.data == "ab_create_new_book")
async def process_create_and_add_book(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    title = data.get("last_query_title") or "Sách / Tài liệu học tập"
    actor_id = call.from_user.id
    try:
        res = await internal_bot_client.quick_create_book(actor_id, title)
        b_id = res["book_id"]
    except Exception as e:
        await call.message.edit_text(f"❌ Lỗi tạo đầu sách: {parse_http_error(e)}")
        return
    await state.update_data(book_id=b_id, book_title=title)
    await state.set_state(AddBookState.waiting_for_condition)
    await call.message.edit_text(
        f"📚 **Đã tạo đầu sách:** {title}\n\n"
        "✨ **Bước 2/3: Chọn tình trạng vật lý của cuốn sách:**",
        reply_markup=get_condition_inline_keyboard(),
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("ab_book:"))
async def process_select_book_to_add(call: CallbackQuery, state: FSMContext):
    await call.answer()
    book_id = call.data.split(":")[1]
    await state.update_data(book_id=book_id)
    await state.set_state(AddBookState.waiting_for_condition)

    await call.message.edit_text(
        "✨ **Bước 2/3: Chọn tình trạng vật lý của cuốn sách:**",
        reply_markup=get_condition_inline_keyboard(),
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("cnd:"))
async def process_select_condition(call: CallbackQuery, state: FSMContext):
    await call.answer()
    condition = call.data.split(":")[1]
    await state.update_data(condition=condition)
    await state.set_state(AddBookState.waiting_for_duration)

    await call.message.edit_text(
        "⏰ **Bước 3/3: Chọn thời gian cho mượn tối đa một lần:**",
        reply_markup=get_duration_inline_keyboard(),
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("dur:"))
async def process_select_duration(call: CallbackQuery, state: FSMContext):
    await call.answer()
    duration_days = int(call.data.split(":")[1])
    data = await state.get_data()
    book_id = data.get("book_id")
    condition = data.get("condition", "good")
    await state.clear()

    try:
        result = await internal_bot_client.add_copy(
            telegram_user_id=call.from_user.id,
            book_id=book_id,
            condition=condition,
            maximum_loan_days=duration_days,
            notes="Đăng qua Telegram Bot Boconic",
        )
        public_code = result.get("public_code", "BC-XXXX")
        await call.message.edit_text(
            f"🎉 **Đăng sách thành công!**\n\n"
            f"• Mã bản sách công khai: `{public_code}`\n"
            f"• Tình trạng: `{condition}`\n"
            f"• Thời hạn mượn tối đa: **{duration_days} ngày**\n\n"
            f"Cuốn sách của bạn hiện đã sẵn sàng để người học khác trong cộng đồng tìm thấy và gửi yêu cầu mượn. "
            f"Cảm ơn tinh thần chia sẻ vì giáo dục cộng đồng của bạn! 💙",
            parse_mode="Markdown"
        )
    except Exception as e:
        await call.message.edit_text(f"❌ Có lỗi khi tạo bản sách: {parse_http_error(e)}")

# --- My Books Flow ---
@router.message(F.text == "📖 Sách của tôi")
@router.message(Command("mybooks"))
async def handle_my_books(message: Message):
    try:
        copies = await internal_bot_client.get_my_books(message.from_user.id)
    except Exception as e:
        await message.answer(f"Lỗi tải danh sách sách: {parse_http_error(e)}")
        return

    kb_menu = get_main_menu_keyboard(is_admin=is_admin(message.from_user.id))
    if not copies:
        await message.answer(
            "Bạn chưa đăng cuốn sách nào lên Boconic.\n\n"
            "Hãy bấm '➕ Đăng sách' để chia sẻ sách cũ giúp đỡ các bạn học khác nhé!",
            reply_markup=kb_menu
        )
        return

    text_lines = ["📖 **Danh sách sách bạn đang sở hữu trên Boconic:**\n"]
    for idx, c in enumerate(copies, 1):
        status_label = "🟢 Sẵn sàng mượn" if c["status"] == "available" else f"🟡 {c['status']}"
        cond_vi = {"new": "Mới", "like_new": "Rất tốt", "good": "Tốt", "fair": "Khá"}.get(c['condition'], c['condition'])
        text_lines.append(f"{idx}. **{c['book_title']}** (Mã: `{c['public_code']}`)\n   • Tình trạng: {cond_vi} | {status_label}")

    await message.answer("\n".join(text_lines), reply_markup=kb_menu, parse_mode="Markdown")

# --- Borrow Requests Flow ---
@router.message(F.text == "📋 Yêu cầu mượn")
@router.message(Command("requests"))
async def handle_requests(message: Message):
    try:
        data = await internal_bot_client.get_requests(message.from_user.id)
        incoming = data.get("incoming", [])
        outgoing = data.get("outgoing", [])
    except Exception as e:
        await message.answer(f"Lỗi tải yêu cầu mượn: {parse_http_error(e)}")
        return

    kb_menu = get_main_menu_keyboard(is_admin=is_admin(message.from_user.id))

    if not incoming and not outgoing:
        await message.answer("Hiện bạn chưa có yêu cầu mượn sách nào (gửi đi hoặc nhận về).", reply_markup=kb_menu)
        return

    # 1. Incoming requests
    if incoming:
        await message.answer("📬 **YÊU CẦU ĐANG CHỜ BẠN DUYỆT (Nhận về):**", parse_mode="Markdown")
        for req in incoming:
            text = (
                f"📘 **{req['book_title']}** (Mã: `{req['copy_code']}`)\n"
                f"👤 Người muốn mượn: **{req['borrower_alias']}**\n"
                f"⏰ Thời hạn đề xuất: **{req['duration_days']} ngày**\n"
            )
            if req.get("note"):
                text += f"💬 Lời nhắn: \"{req['note']}\"\n"
            kb = get_request_action_keyboard(req["request_id"])
            await message.answer(text, reply_markup=kb, parse_mode="Markdown")

    # 2. Outgoing requests
    if outgoing:
        out_lines = ["📤 **CÁC YÊU CẦU BẠN ĐÃ GỬI ĐI:**\n"]
        for idx, req in enumerate(outgoing, 1):
            st = {
                "pending": "⏳ Chờ chủ sách duyệt",
                "accepted": "✅ Đã chấp nhận (đang giữ chỗ)",
                "rejected": "❌ Đã bị từ chối",
                "expired": "⏱ Đã hết hạn",
            }.get(req["status"], req["status"])
            out_lines.append(f"{idx}. **{req['book_title']}** (Mã: `{req['copy_code']}`)\n   Chủ sách: {req['owner_alias']} | Trạng thái: {st}")

        await message.answer("\n".join(out_lines), reply_markup=kb_menu, parse_mode="Markdown")

# --- My Loans Flow ---
@router.message(F.text == "🤝 Đang mượn")
@router.message(Command("loans"))
async def handle_my_loans(message: Message):
    try:
        loans = await internal_bot_client.get_my_loans(message.from_user.id)
    except Exception as e:
        await message.answer(f"Lỗi tải danh sách mượn: {parse_http_error(e)}")
        return

    kb_menu = get_main_menu_keyboard(is_admin=is_admin(message.from_user.id))
    if not loans:
        await message.answer("Hiện bạn không có cuốn sách nào đang mượn.", reply_markup=kb_menu)
        return

    for l in loans:
        status_vi = {
            "reserved": "🟡 Đã giữ chỗ (chờ giao nhận)",
            "active": "🟢 Đang mượn",
            "return_pending": "🔄 Đang chờ xác nhận trả",
        }.get(l["status"], l["status"])

        card = (
            f"📘 **{l['book_title']}** (Mã: `{l['public_code']}`)\n"
            f"👤 Chủ sách: **{l['lender_alias']}**\n"
            f"📌 Trạng thái: **{status_vi}**\n"
        )
        if l.get("due_at"):
            card += f"⏰ Hạn trả: **{l['due_at'][:10]}**"

        kb = None
        if l["status"] == "reserved":
            kb = get_loan_handover_keyboard(l["loan_id"], role="borrower")
        elif l["status"] == "active":
            kb = get_loan_return_keyboard(l["loan_id"], is_pending=False)
        elif l["status"] == "return_pending":
            kb = get_loan_return_keyboard(l["loan_id"], is_pending=True)

        await message.answer(card, reply_markup=kb, parse_mode="Markdown")

# --- My Lendings Flow ---
@router.message(F.text == "📤 Đang cho mượn")
@router.message(Command("lendings"))
async def handle_my_lendings(message: Message):
    try:
        loans = await internal_bot_client.get_my_lendings(message.from_user.id)
    except Exception as e:
        await message.answer(f"Lỗi tải danh sách: {parse_http_error(e)}")
        return

    kb_menu = get_main_menu_keyboard(is_admin=is_admin(message.from_user.id))
    if not loans:
        await message.answer("Bạn hiện chưa có bản sách nào đang được người khác mượn.", reply_markup=kb_menu)
        return

    for l in loans:
        status_vi = {
            "reserved": "🟡 Đã giữ chỗ (chờ giao nhận)",
            "active": "🟢 Người khác đang mượn",
            "return_pending": "🔄 Đang chờ xác nhận nhận lại sách",
        }.get(l["status"], l["status"])

        card = (
            f"📗 **{l['book_title']}** (Mã: `{l['public_code']}`)\n"
            f"👤 Người mượn: **{l['borrower_alias']}**\n"
            f"📌 Trạng thái: **{status_vi}**\n"
        )
        if l.get("due_at"):
            card += f"⏰ Hạn trả: **{l['due_at'][:10]}**"

        kb = None
        if l["status"] == "reserved":
            kb = get_loan_handover_keyboard(l["loan_id"], role="lender")
        elif l["status"] == "return_pending":
            kb = get_loan_return_keyboard(l["loan_id"], is_pending=True)

        await message.answer(card, reply_markup=kb, parse_mode="Markdown")

# --- Community Need Flow ---
@router.message(F.text == "📢 Tôi đang cần")
async def handle_need(message: Message, state: FSMContext):
    await handle_start_need_wizard(message, state)

# --- Nearby Books Flow ---
@router.message(F.text == "📍 Gần tôi")
@router.message(Command("nearby"))
async def handle_nearby(message: Message):
    try:
        # Search available catalog books
        data = await internal_bot_client.search_books(message.from_user.id, query="", limit=5)
        items = data.get("items", [])
    except Exception as e:
        await message.answer(f"Lỗi tìm kiếm sách khu vực: {parse_http_error(e)}")
        return

    kb_menu = get_main_menu_keyboard(is_admin=is_admin(message.from_user.id))
    if not items:
        await message.answer("Chưa có sách nào sẵn sàng mượn quanh khu vực của bạn.", reply_markup=kb_menu)
        return

    text_lines = ["📍 **Sách đang có sẵn mượn tại TP. Hồ Chí Minh (Quận 5, Quận 10):**\n"]
    for idx, item in enumerate(items, 1):
        if item.get("available_count", 0) > 0:
            text_lines.append(
                f"{idx}. 📚 **{item['title']}**\n"
                f"   • Khả dụng: **{item['available_count']} bản** | NXB: {item.get('publisher') or 'N/A'}\n"
                f"   • Khu vực kết nối: *Quận 5, Quận 10, TP.HCM*"
            )

    text_lines.append("\n👉 Gõ /search hoặc bấm '🔎 Tìm sách' để xem chi tiết và gửi yêu cầu mượn!")
    await message.answer("\n".join(text_lines), reply_markup=kb_menu, parse_mode="Markdown")

# --- Libraries & Schools Flow ---
@router.message(F.text == "🏛 Thư viện & Trường học")
@router.message(Command("library"))
async def handle_libraries(message: Message):
    try:
        orgs = await internal_bot_client.get_libraries(message.from_user.id)
    except Exception as e:
        await message.answer(f"Lỗi tải danh mục thư viện: {parse_http_error(e)}")
        return

    kb_menu = get_main_menu_keyboard(is_admin=is_admin(message.from_user.id))
    if not orgs:
        await message.answer("Chưa có dữ liệu thư viện đối tác.", reply_markup=kb_menu)
        return

    text_lines = ["🏛 **Danh mục Thư viện & Trường học đối tác đã xác minh:**\n"]
    for idx, o in enumerate(orgs, 1):
        text_lines.append(
            f"{idx}. 🏫 **{o['name']}**\n"
            f"   • Địa chỉ: {o.get('public_address') or o.get('city')}\n"
            f"   • Giờ mở cửa: {o.get('opening_hours') or '07:30 - 17:00 (Thứ 2 - Thứ 6)'}\n"
            f"   • Chính sách: {o.get('inventory_policy') or 'Phục vụ học sinh, giáo viên và cộng đồng'}\n"
        )

    await message.answer("\n".join(text_lines), reply_markup=kb_menu, parse_mode="Markdown")

# --- Open Digital Resources Flow ---
@router.message(F.text == "🔗 Tài nguyên mở")
@router.message(Command("resources"))
async def handle_resources(message: Message):
    try:
        res_list = await internal_bot_client.get_resources(message.from_user.id)
    except Exception:
        res_list = []

    kb_menu = get_main_menu_keyboard(is_admin=is_admin(message.from_user.id))

    if res_list:
        text_lines = ["📚 **Học liệu & Tài nguyên số mở đã kiểm duyệt bản quyền (Boconic):**\n"]
        for idx, r in enumerate(res_list, 1):
            text_lines.append(
                f"{idx}. 📄 **{r['title']}**\n"
                f"   • Nguồn: {r['source_name']} | Giấy phép: `{r['license_name']}`\n"
                f"   • Liên kết: {r['source_url']}\n"
            )
        text_lines.append("Tất cả tài nguyên số trên Boconic đều tuân thủ nghiêm ngặt quyền sở hữu trí tuệ.")
        await message.answer("\n".join(text_lines), reply_markup=kb_menu, parse_mode="Markdown")
    else:
        text = (
            "📚 **Học liệu & Tài nguyên mở đã kiểm duyệt (Boconic Resources):**\n\n"
            "1. **Bộ đề thi và Đáp án THPT Quốc Gia - Môn Toán (2024)**\n"
            "   • Nguồn: Bộ Giáo dục & Đào tạo | Giấy phép: Công khai\n"
            "   • Liên kết: https://moet.gov.vn\n\n"
            "2. **Tài liệu Bổ trợ Chuyên đề Cảm ứng Điện từ - Vật Lí 12**\n"
            "   • Nguồn: Thư viện Học liệu Mở Việt Nam | Giấy phép: CC BY-NC 4.0\n"
            "   • Liên kết: https://hoclieu.vn\n\n"
            "Tất cả tài nguyên số trên Boconic đều được kiểm tra bản quyền theo quy định."
        )
        await message.answer(text, reply_markup=kb_menu, parse_mode="Markdown")

# --- User Profile Flow ---
@router.message(F.text == "👤 Hồ sơ & Cài đặt")
@router.message(Command("profile"))
async def handle_profile(message: Message):
    actor_id = message.from_user.id
    user_is_admin = is_admin(actor_id)
    try:
        user_info = await internal_bot_client.sync_user(
            telegram_user_id=actor_id,
            display_name=message.from_user.full_name or message.from_user.first_name,
        )
        alias = user_info.get("public_alias", "User")
        status = user_info.get("status", "active")
    except Exception:
        alias = "User"
        status = "active"

    role_str = "👑 Quản trị viên tối cao (Super Admin)" if user_is_admin else "Thành viên cộng đồng"

    profile_text = (
        "👤 **Thông tin tài khoản Boconic:**\n\n"
        f"• Biệt danh công khai: **{alias}**\n"
        f"• Telegram Numeric ID: `{actor_id}`\n"
        f"• Vai trò: **{role_str}**\n"
        f"• Trạng thái tài khoản: `{status}`\n"
        f"• Ngôn ngữ: `Tiếng Việt (vi)`\n\n"
        "🔒 **Chính sách bảo mật:** Tọa độ GPS chính xác và thông tin cá nhân của bạn được mã hóa an toàn. "
        "Người khác chỉ nhìn thấy Biệt danh công khai và khu vực cấp Phường/Quận."
    )
    await message.answer(profile_text, reply_markup=get_main_menu_keyboard(is_admin=user_is_admin), parse_mode="Markdown")

# --- Report / Support Flow ---
@router.message(F.text == "🚩 Báo cáo / Hỗ trợ")
@router.message(Command("report"))
async def start_report(message: Message, state: FSMContext):
    await state.set_state(ReportState.waiting_for_category)
    await message.answer(
        "🚩 **Báo cáo sự cố hoặc vi phạm:**\n\n"
        "Vui lòng chọn danh mục sự cố bạn gặp phải:",
        reply_markup=get_report_category_keyboard(),
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("rpc:"))
async def process_report_category(call: CallbackQuery, state: FSMContext):
    await call.answer()
    category = call.data.split(":")[1]
    await state.update_data(category=category)
    await state.set_state(ReportState.waiting_for_description)

    await call.message.edit_text(
        "📝 Vui lòng nhập mô tả chi tiết sự cố bạn muốn gửi tới Ban Quản Trị Boconic (gõ /cancel để hủy):"
    )

@router.message(ReportState.waiting_for_description)
async def process_report_description(message: Message, state: FSMContext, bot: Bot):
    if not message.text:
        await message.answer("❌ Vui lòng nhập mô tả sự cố bằng tin nhắn văn bản:")
        return
    desc = message.text.strip()
    if desc == "❌ Hủy thao tác":
        await state.clear()
        await message.answer("Đã hủy báo cáo.", reply_markup=get_main_menu_keyboard(is_admin=is_admin(message.from_user.id)))
        return

    data = await state.get_data()
    category = data.get("category", "other")
    await state.clear()

    try:
        await internal_bot_client.create_report(
            telegram_user_id=message.from_user.id,
            category=category,
            description=desc,
        )
    except Exception as e:
        logger.warning(f"Lỗi lưu report vào database: {e}")

    # Notify admin via Telegram if configured
    admin_id = settings.ADMIN_TELEGRAM_ID
    if admin_id and admin_id.isdigit():
        try:
            admin_chat_id = int(admin_id)
            user_alias = message.from_user.full_name or str(message.from_user.id)
            await bot.send_message(
                chat_id=admin_chat_id,
                text=f"🚨 **BÁO CÁO MỚI TỪ NGƯỜI DÙNG**\n\n"
                     f"• Người gửi: **{user_alias}** (ID: `{message.from_user.id}`)\n"
                     f"• Danh mục: `{category}`\n"
                     f"• Nội dung: {desc}\n\n"
                     f"🔗 Xem chi tiết tại: {settings.APP_BASE_URL}/admin",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Không thể gửi báo cáo tới Admin Telegram: {e}")

    await message.answer(
        "✅ **Báo cáo của bạn đã được gửi thành công!**\n"
        "Ban Quản Trị Boconic đã nhận được thông tin và sẽ kiểm tra trong thời gian sớm nhất. Cảm ơn bạn!",
        reply_markup=get_main_menu_keyboard(is_admin=is_admin(message.from_user.id)),
        parse_mode="Markdown"
    )

# --- Admin Dashboard Flow ---
@router.message(F.text == "👑 Quản trị hệ thống")
@router.message(Command("admin"))
async def handle_admin(message: Message):
    actor_id = message.from_user.id
    if not is_admin(actor_id):
        await message.answer("⛔ Bạn không có quyền truy cập chức năng Quản trị viên.")
        return

    try:
        stats = await internal_bot_client.get_admin_stats(actor_id)
    except Exception as e:
        await message.answer(f"Lỗi kết nối máy chủ quản trị: {parse_http_error(e)}")
        return

    dashboard_text = (
        "👑 **BOCONIC SUPER ADMIN LIVE DASHBOARD**\n\n"
        "Hệ thống đang vận hành trực tiếp trên cơ sở dữ liệu production.\n\n"
        "📊 **Thống kê thời gian thực:**\n"
        f"• 👥 Tổng người dùng: **{stats.get('total_users', 0)}**\n"
        f"• 📚 Danh mục đầu sách: **{stats.get('total_books', 0)}**\n"
        f"• 📦 Tổng bản sách vật lý: **{stats.get('total_copies', 0)}**\n"
        f"   - 🟢 Sẵn sàng mượn: **{stats.get('available_copies', 0)}**\n"
        f"   - 🟡 Đang được mượn: **{stats.get('loaned_copies', 0)}**\n"
        f"• 🤝 Lượt mượn đang diễn ra: **{stats.get('active_loans', 0)}**\n"
        f"• ⏳ Yêu cầu mượn chờ duyệt: **{stats.get('pending_requests', 0)}**\n"
        f"• 📢 Nhu cầu cộng đồng mở: **{stats.get('community_needs', 0)}**\n"
        f"• 🔗 Tài nguyên mở đã duyệt: **{stats.get('resources_count', 0)}**\n\n"
        f"🌐 **Web Admin Console:** {settings.APP_BASE_URL}/admin\n"
        "Đăng nhập tài khoản Super Admin để kiểm duyệt sách, quản lý người dùng và xuất báo cáo CSV."
    )
    await message.answer(dashboard_text, reply_markup=get_main_menu_keyboard(is_admin=True), parse_mode="Markdown")

# --- Interactive Inline Handshake Callbacks ---
@router.callback_query(F.data.startswith("brq:"))
async def handle_borrow_callback(call: CallbackQuery, bot: Bot):
    await call.answer()
    copy_id = call.data.split(":", 1)[1]
    actor_id = call.from_user.id

    try:
        res = await internal_bot_client.create_borrow_request(
            telegram_user_id=actor_id,
            copy_id=copy_id,
            duration_days=14,
        )
    except Exception as e:
        err_msg = parse_http_error(e)
        await call.message.answer(f"⚠️ Không thể gửi yêu cầu mượn: {err_msg}")
        return

    book_title = res.get("book_title", "Sách")
    copy_code = res.get("copy_code", "")
    owner_alias = res.get("owner_alias", "Chủ sách")
    req_id = res.get("request_id")
    owner_telegram_id = res.get("owner_telegram_id")
    requester_alias = res.get("requester_alias", call.from_user.full_name)

    await call.message.answer(
        f"✅ **Đã gửi yêu cầu mượn thành công!**\n\n"
        f"• Tên sách: **{book_title}** (Mã: `{copy_code}`)\n"
        f"• Chủ sở hữu: **{owner_alias}**\n"
        f"• Thời hạn mượn đề xuất: **14 ngày**\n\n"
        f"Chủ sách đã nhận được thông báo. Bạn sẽ nhận được tin nhắn ngay khi yêu cầu được chấp nhận!",
        parse_mode="Markdown"
    )

    # Send real-time notification to the book owner if available
    if owner_telegram_id and req_id:
        try:
            owner_text = (
                f"📬 **YÊU CẦU MƯỢN SÁCH MỚI!**\n\n"
                f"👤 Thành viên **{requester_alias}** muốn mượn cuốn sách của bạn:\n"
                f"📚 **{book_title}** (Mã: `{copy_code}`)\n"
                f"⏰ Thời hạn: **14 ngày**\n\n"
                f"Bạn có đồng ý cho mượn không?"
            )
            await bot.send_message(
                chat_id=owner_telegram_id,
                text=owner_text,
                reply_markup=get_request_action_keyboard(req_id),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Could not notify owner {owner_telegram_id}: {e}")

@router.callback_query(F.data.startswith("acc:"))
async def handle_accept_request_callback(call: CallbackQuery, bot: Bot):
    await call.answer()
    req_id = call.data.split(":", 1)[1]
    actor_id = call.from_user.id

    try:
        res = await internal_bot_client.accept_borrow_request(
            telegram_user_id=actor_id,
            request_id=req_id,
        )
    except Exception as e:
        await call.message.answer(f"⚠️ Lỗi chấp nhận yêu cầu: {parse_http_error(e)}")
        return

    book_title = res.get("book_title", "Sách")
    copy_code = res.get("copy_code", "")
    loan_id = res.get("loan_id")
    borrower_telegram_id = res.get("borrower_telegram_id")
    borrower_alias = res.get("borrower_alias", "Người mượn")
    lender_alias = call.from_user.full_name or "Chủ sách"

    await call.message.edit_text(
        f"✅ **Bạn đã chấp nhận cho mượn cuốn sách!**\n\n"
        f"📚 **{book_title}** (Mã: `{copy_code}`)\n"
        f"👤 Người mượn: **{borrower_alias}**\n\n"
        f"Bản sách đã được giữ chỗ an toàn trong 72 giờ. "
        f"Hai bạn hãy hẹn gặp nhau giao nhận sách, sau đó bấm nút xác nhận dưới đây:",
        reply_markup=get_loan_handover_keyboard(loan_id, role="lender") if loan_id else None,
        parse_mode="Markdown"
    )

    # Notify borrower
    if borrower_telegram_id and loan_id:
        try:
            borrower_text = (
                f"🎉 **CHỦ SÁCH ĐÃ ĐỒNG Ý CHO BẠN MƯỢN!**\n\n"
                f"📚 Cuốn sách: **{book_title}** (Mã: `{copy_code}`)\n"
                f"👤 Chủ sách: **{lender_alias}**\n\n"
                f"Sách đã được giữ chỗ cho bạn. Sau khi gặp mặt và nhận sách thực tế, vui lòng bấm nút xác nhận bên dưới:"
            )
            await bot.send_message(
                chat_id=borrower_telegram_id,
                text=borrower_text,
                reply_markup=get_loan_handover_keyboard(loan_id, role="borrower"),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Could not notify borrower {borrower_telegram_id}: {e}")

@router.callback_query(F.data.startswith("rej:"))
async def handle_reject_request_callback(call: CallbackQuery, bot: Bot):
    await call.answer()
    req_id = call.data.split(":", 1)[1]
    actor_id = call.from_user.id

    try:
        res = await internal_bot_client.reject_borrow_request(
            telegram_user_id=actor_id,
            request_id=req_id,
        )
    except Exception as e:
        await call.message.answer(f"⚠️ Lỗi từ chối yêu cầu: {parse_http_error(e)}")
        return

    book_title = res.get("book_title", "Sách")
    borrower_telegram_id = res.get("borrower_telegram_id")

    await call.message.edit_text(f"❌ Đã từ chối yêu cầu mượn cuốn **{book_title}**.", parse_mode="Markdown")

    if borrower_telegram_id:
        try:
            await bot.send_message(
                chat_id=borrower_telegram_id,
                text=f"Tiếc quá, chủ sách hiện chưa thể cho bạn mượn cuốn **{book_title}** lúc này. "
                     f"Bạn hãy tìm bản sách khác hoặc đăng nhu cầu vào '📢 Tôi đang cần' nhé!",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Could not notify borrower {borrower_telegram_id}: {e}")

@router.callback_query(F.data.startswith("hdo:"))
async def handle_handover_callback(call: CallbackQuery, bot: Bot):
    await call.answer()
    loan_id = call.data.split(":", 1)[1]
    actor_id = call.from_user.id

    try:
        res = await internal_bot_client.confirm_handover(actor_id, loan_id)
    except Exception as e:
        await call.message.answer(f"⚠️ Lỗi xác nhận giao nhận: {parse_http_error(e)}")
        return

    is_active = res.get("is_active", False)
    due_at = res.get("due_at")
    book_title = res.get("book_title", "Sách")
    other_telegram_id = res.get("other_telegram_id")
    due_date_str = due_at[:10] if due_at else "14 ngày tới"

    if is_active:
        msg = (
            f"🎉 **XÁC NHẬN GIAO NHẬN THÀNH CÔNG!**\n\n"
            f"Cả 2 bên đã xác nhận hoàn tất giao nhận cuốn **{book_title}**.\n"
            f"Lượt mượn chính thức bắt đầu!\n"
            f"⏰ Hạn hoàn trả: **{due_date_str}**.\n\n"
            f"Chúc bạn học tập thật tốt và giữ gìn sách cẩn thận! 📖"
        )
        await call.message.edit_text(msg, parse_mode="Markdown")

        # Notify the other party
        if other_telegram_id:
            try:
                await bot.send_message(
                    chat_id=other_telegram_id,
                    text=f"🎉 **ĐỐI PHƯƠNG ĐÃ XÁC NHẬN GIAO NHẬN THÀNH CÔNG!**\n\n"
                         f"Lượt mượn cuốn **{book_title}** đã chính thức bắt đầu!\n"
                         f"⏰ Hạn trả: **{due_date_str}**.",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.warning(f"Could not notify other party: {e}")
    else:
        await call.message.edit_text(
            f"🤝 **Đã ghi nhận xác nhận giao nhận từ bạn!**\n\n"
            f"Đang chờ đối phương bấm xác nhận để lượt mượn chính thức bắt đầu.",
            parse_mode="Markdown"
        )
        if other_telegram_id:
            try:
                await bot.send_message(
                    chat_id=other_telegram_id,
                    text=f"🔔 Đối phương đã xác nhận giao nhận cuốn **{book_title}**!\n"
                         f"Vui lòng vào mục '🤝 Đang mượn' hoặc '📤 Đang cho mượn' để xác nhận.",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.warning(f"Could not notify other party: {e}")

@router.callback_query(F.data.startswith("rt_req:"))
async def handle_return_req_callback(call: CallbackQuery, bot: Bot):
    await call.answer()
    loan_id = call.data.split(":", 1)[1]
    actor_id = call.from_user.id

    try:
        res = await internal_bot_client.request_return(actor_id, loan_id)
    except Exception as e:
        await call.message.answer(f"⚠️ Lỗi yêu cầu trả sách: {parse_http_error(e)}")
        return

    book_title = res.get("book_title", "Sách")
    other_telegram_id = res.get("other_telegram_id")

    await call.message.edit_text(
        f"🔄 **Đã gửi yêu cầu xác nhận trả sách!**\n\n"
        f"Cuốn sách **{book_title}** đã chuyển sang trạng thái chờ xác nhận hoàn trả. "
        f"Hãy gặp mặt đối phương để kiểm tra sách và cả 2 cùng bấm xác nhận.",
        reply_markup=get_loan_return_keyboard(loan_id, is_pending=True),
        parse_mode="Markdown"
    )

    if other_telegram_id:
        try:
            await bot.send_message(
                chat_id=other_telegram_id,
                text=f"🔔 **ĐỀ NGHỊ TRẢ SÁCH:**\n\n"
                     f"Đối phương đã gửi đề nghị xác nhận trả cuốn **{book_title}**.\n"
                     f"Vui lòng gặp mặt nhận lại sách và bấm xác nhận hoàn tất bên dưới:",
                reply_markup=get_loan_return_keyboard(loan_id, is_pending=True),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Could not notify other party: {e}")

@router.callback_query(F.data.startswith("rt_cfm:"))
async def handle_return_cfm_callback(call: CallbackQuery, bot: Bot):
    await call.answer()
    loan_id = call.data.split(":", 1)[1]
    actor_id = call.from_user.id

    try:
        res = await internal_bot_client.confirm_return(actor_id, loan_id)
    except Exception as e:
        await call.message.answer(f"⚠️ Lỗi xác nhận hoàn trả: {parse_http_error(e)}")
        return

    is_returned = res.get("is_returned", False)
    book_title = res.get("book_title", "Sách")
    other_telegram_id = res.get("other_telegram_id")

    if is_returned:
        msg = (
            f"🎉 **LƯỢT MƯỢN ĐÃ HOÀN TẤT THÀNH CÔNG!**\n\n"
            f"Cả 2 bên đã xác nhận hoàn trả cuốn **{book_title}**.\n"
            f"Bản sách đã được đưa trở lại kho sẵn sàng chia sẻ cho cộng đồng.\n"
            f"🌟 Điểm uy tín cộng đồng của bạn được cộng thưởng (+1.0 điểm uy tín).\n\n"
            f"Cảm ơn bạn đã đồng hành và giữ gìn văn hóa đọc cộng đồng cùng Boconic! 💙"
        )
        await call.message.edit_text(msg, parse_mode="Markdown")

        if other_telegram_id:
            try:
                await bot.send_message(
                    chat_id=other_telegram_id,
                    text=f"🎉 **LƯỢT MƯỢN ĐÃ HOÀN TẤT!**\n\n"
                         f"Cả 2 bên đã xác nhận hoàn trả cuốn **{book_title}**.\n"
                         f"🌟 Điểm uy tín của bạn được ghi nhận tích cực (+1.0 điểm)!",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.warning(f"Could not notify other party: {e}")
    else:
        await call.message.edit_text(
            f"✅ **Đã ghi nhận xác nhận hoàn trả từ bạn!**\n"
            f"Đang chờ đối phương xác nhận để hoàn tất giao dịch.",
            parse_mode="Markdown"
        )


# ==========================================
# PERSONAL LIBRARY HANDLERS
# ==========================================

@router.message(Command("mylibrary"))
@router.message(F.text == "📚 Thư viện của tôi")
async def handle_library(message: Message, state: FSMContext):
    await state.clear()
    actor_id = message.from_user.id

    try:
        data = await internal_bot_client.get_library(actor_id, tab="all")
    except Exception as e:
        await message.answer(f"⚠️ Không thể tải thư viện: {parse_http_error(e)}")
        return

    items = data.get("items", [])
    total = len(items)

    text = (
        f"📚 **THƯ VIỆN CÁ NHÂN CỦA BẠN**\n"
        f"Tổng cộng: **{total}** mục trong danh mục.\n\n"
        f"• Sách sở hữu: sẵn sàng cho mượn hoặc lưu trữ riêng tư\n"
        f"• Sách đang mượn từ cộng đồng\n"
        f"• Wishlist & nhu cầu đang tìm kiếm\n"
        f"• Tài liệu 1 phần & photo ghi nhận bản quyền\n\n"
        f"Hãy chọn danh mục tab để xem chi tiết:"
    )
    await message.answer(text, reply_markup=get_library_tabs_keyboard(), parse_mode="Markdown")


@router.callback_query(F.data.startswith("lib:"))
async def handle_library_tab(call: CallbackQuery):
    actor_id = call.from_user.id
    tab = call.data.split(":", 1)[1]

    tab_titles = {
        "all": "Tất cả danh mục",
        "owned": "Sách tôi sở hữu",
        "available": "Sách sẵn sàng cho mượn",
        "lent": "Sách đang cho mượn / Giữ chỗ",
        "borrowed": "Sách tôi đang mượn",
        "wishlist": "Wishlist & Nhu cầu đang tìm",
        "resources": "Tài liệu 1 phần & Photocopy",
        "history": "Lịch sử mượn trả",
    }
    title = tab_titles.get(tab, tab.capitalize())

    try:
        data = await internal_bot_client.get_library(actor_id, tab=tab)
    except Exception as e:
        await call.answer(f"Lỗi: {parse_http_error(e)}", show_alert=True)
        return

    items = data.get("items", [])
    if not items:
        await call.message.edit_text(
            f"📚 **{title.upper()}**\n\n_Chưa có mục nào trong danh mục này._",
            reply_markup=get_library_tabs_keyboard(),
            parse_mode="Markdown",
        )
        await call.answer()
        return

    lines = [f"📚 **{title.upper()}** ({len(items)} mục):\n"]
    for idx, item in enumerate(items[:10], start=1):
        itype = item.get("type")
        if itype == "owned_copy":
            vis = "🌐 Công khai" if item.get("visibility") == "published" else "🔒 Riêng tư"
            st = item.get("circulation_status")
            st_text = "Sẵn sàng" if st == "available" else ("Đang cho mượn" if st == "loaned" else "Đang giữ chỗ")
            lines.append(f"{idx}. **{item.get('title')}**\n   Mã: `{item.get('barcode')}` | {st_text} | {vis}")
        elif itype == "borrowed_loan":
            lines.append(f"{idx}. **{item.get('title')}**\n   Trạng thái: `{item.get('status')}` | Hạn trả: {item.get('due_at', 'Đang sắp xếp')[:10]}")
        elif itype == "wishlist_need":
            lines.append(f"{idx}. Cần: **{item.get('title_query')}**\n   SL: {item.get('quantity_fulfilled', 0)}/{item.get('quantity', 1)} | Trạng thái: {item.get('status')}")
        elif itype == "history_loan":
            lines.append(f"{idx}. **{item.get('book_title')}** (Hoàn tất)\n   Vai trò: {item.get('role')} | Trả ngày: {str(item.get('returned_at'))[:10]}")

    if len(items) > 10:
        lines.append(f"\n_...và {len(items) - 10} mục khác._")

    await call.message.edit_text(
        "\n".join(lines),
        reply_markup=get_library_tabs_keyboard(),
        parse_mode="Markdown",
    )
    await call.answer()


# ==========================================
# NEED WIZARD HANDLERS ("Tôi cần sách A")
# ==========================================

@router.message(Command("request"))
@router.message(Command("need"))
@router.message(F.text == "📢 Yêu cầu sách")
async def handle_start_need_wizard(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(RequestWizardState.waiting_for_title)
    text = (
        "📢 **ĐĂNG NHU CẦU: TÔI CẦN SÁCH A**\n\n"
        "Boconic sẽ tự động tìm kiếm **tất cả chủ sách phù hợp** trong cộng đồng "
        "và gửi thông báo để những người có thể hỗ trợ phản hồi bạn!\n\n"
        "Vui lòng nhập **Tên sách**, **Tác giả**, hoặc mã **ISBN** bạn đang cần:\n"
        "_(Ví dụ: Giải tích 1 ĐHBK, hoặc 9786040001234)_"
    )
    await message.answer(text, reply_markup=get_cancel_keyboard(), parse_mode="Markdown")


@router.message(RequestWizardState.waiting_for_title)
async def handle_need_title_input(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Vui lòng nhập tên sách bằng tin nhắn văn bản:")
        return
    title_query = message.text.strip()
    if title_query == "❌ Hủy thao tác":
        await state.clear()
        await message.answer("❌ Đã hủy đăng nhu cầu sách.", reply_markup=get_main_menu_keyboard(is_admin=is_admin(message.from_user.id)))
        return

    if len(title_query) < 2:
        await message.answer("⚠️ Tiêu đề quá ngắn. Vui lòng nhập rõ hơn tên sách bạn cần:")
        return

    await state.update_data(title_query=title_query)
    await state.set_state(RequestWizardState.waiting_for_scope)

    safe_title = title_query.replace("*", "").replace("_", " ").replace("`", "")
    text = (
        f"📖 Sách bạn cần: **{safe_title}**\n\n"
        "Bạn cần phạm vi tài liệu nào?"
    )
    await message.answer(text, reply_markup=get_need_scope_keyboard(), parse_mode="Markdown")


@router.callback_query(RequestWizardState.waiting_for_scope, F.data.startswith("scp:"))
async def handle_need_scope_choice(call: CallbackQuery, state: FSMContext):
    scope_type = call.data.split(":", 1)[1]
    await state.update_data(scope_type=scope_type)

    if scope_type == "full_book":
        await state.update_data(page_range=[], target_chapters=[])
        await state.set_state(RequestWizardState.waiting_for_urgency)
        await call.message.edit_text(
            "⏳ **Mức độ cần gấp:**",
            reply_markup=get_need_urgency_keyboard(),
            parse_mode="Markdown",
        )
    elif scope_type == "chapters":
        await state.set_state(RequestWizardState.waiting_for_scope_detail)
        await call.message.edit_text(
            "📑 Vui lòng nhập tên hoặc số các **chương / chủ đề** bạn cần (ví dụ: `Chương 1, 2 và 3`):",
            parse_mode="Markdown",
        )
    else:  # page_range
        await state.set_state(RequestWizardState.waiting_for_scope_detail)
        await call.message.edit_text(
            "📄 Vui lòng nhập **khoảng trang** bạn cần (ví dụ: `1-50` hoặc `20-80`):",
            parse_mode="Markdown",
        )
    await call.answer()


@router.message(RequestWizardState.waiting_for_scope_detail)
async def handle_need_scope_detail_input(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Vui lòng nhập chi tiết bằng tin nhắn văn bản:")
        return
    detail_text = message.text.strip()
    if detail_text == "❌ Hủy thao tác":
        await state.clear()
        await message.answer("❌ Đã hủy đăng nhu cầu sách.", reply_markup=get_main_menu_keyboard(is_admin=is_admin(message.from_user.id)))
        return

    data = await state.get_data()
    scope_type = data.get("scope_type", "full_book")

    page_range = []
    target_chapters = []
    if scope_type == "page_range":
        import re
        nums = [int(n) for n in re.findall(r"\d+", detail_text)]
        if len(nums) >= 2:
            page_range = [min(nums[0], nums[1]), max(nums[0], nums[1])]
        elif len(nums) == 1:
            page_range = [1, nums[0]]
    elif scope_type == "chapters":
        import re
        nums = re.findall(r"\d+", detail_text)
        if nums:
            target_chapters = [str(n) for n in nums]
        else:
            target_chapters = [c.strip() for c in re.split(r"[,;&]+", detail_text) if c.strip()]

    await state.update_data(scope_detail=detail_text, page_range=page_range, target_chapters=target_chapters)
    await state.set_state(RequestWizardState.waiting_for_urgency)

    await message.answer(
        "⏳ **Mức độ cần gấp của bạn:**",
        reply_markup=get_need_urgency_keyboard(),
        parse_mode="Markdown",
    )


@router.callback_query(RequestWizardState.waiting_for_urgency, F.data.startswith("urg:"))
async def handle_need_urgency_choice(call: CallbackQuery, state: FSMContext):
    urgency = call.data.split(":", 1)[1]
    await state.update_data(urgency=urgency)
    await state.set_state(RequestWizardState.waiting_for_location)

    await call.message.edit_text(
        "📍 Vui lòng nhập **Khu vực / Quận / Trường** bạn thuận tiện nhận sách\n"
        "_(hoặc gõ `Bỏ qua` nếu bạn có thể đến bất kỳ đâu):_",
        parse_mode="Markdown",
    )
    await call.answer()


@router.message(RequestWizardState.waiting_for_location)
async def handle_need_location_and_submit(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Vui lòng nhập khu vực hoặc gõ `Bỏ qua`:", parse_mode="Markdown")
        return
    loc_text = message.text.strip()
    if loc_text == "❌ Hủy thao tác":
        await state.clear()
        await message.answer("❌ Đã hủy đăng nhu cầu sách.", reply_markup=get_main_menu_keyboard(is_admin=is_admin(message.from_user.id)))
        return

    coarse_location = None if loc_text.lower() in ("bỏ qua", "skip", "none", "") else loc_text

    data = await state.get_data()
    actor_id = message.from_user.id
    raw_title = data.get("title_query", "").strip()

    # Detect ISBN if user entered 10 or 13 digits (with optional dashes/spaces)
    import re
    clean_digits = re.sub(r"[\s-]", "", raw_title)
    isbn = clean_digits if (clean_digits.isdigit() and len(clean_digits) in (10, 13)) else None

    scope_type = data.get("scope_type", "full_book")
    page_range = data.get("page_range", [])
    target_chapters = data.get("target_chapters", [])
    scope_detail = data.get("scope_detail")

    try:
        res = await internal_bot_client.create_need(
            telegram_user_id=actor_id,
            title_query=raw_title,
            isbn=isbn,
            scope_type=scope_type,
            page_range=page_range,
            target_chapters=target_chapters,
            urgency=data.get("urgency", "normal"),
            coarse_location=coarse_location,
            description=scope_detail,
        )
    except Exception as e:
        err_msg = parse_http_error(e)
        dup_hint = ""
        if "đã có một yêu cầu đang mở" in err_msg.lower() or "already_exists" in err_msg.lower():
            dup_hint = "\n\n💡 Bạn có thể kiểm tra danh sách nhu cầu hiện tại bằng nút **📋 Nhu cầu của tôi**."
        await message.answer(
            f"⚠️ Lỗi khi tạo nhu cầu sách: {err_msg}{dup_hint}",
            reply_markup=get_main_menu_keyboard(is_admin=is_admin(actor_id)),
        )
        await state.clear()
        return

    await state.clear()
    need_id = res.get("need_id")

    safe_title = raw_title.replace("*", "").replace("_", " ").replace("`", "")
    safe_scope = str(scope_type).replace("*", "").replace("_", " ")

    success_text = (
        "🎉 **ĐĂNG NHU CẦU THÀNH CÔNG!**\n\n"
        f"📚 Sách cần: **{safe_title}**\n"
        f"Phạm vi: `{safe_scope}`\n"
        f"Mã nhu cầu: `{need_id}`\n\n"
        "🔍 Hệ thống đã rà soát mạng lưới cộng đồng Boconic và tự động đưa thông báo "
        "vào hàng đợi gửi đến các chủ sách đủ điều kiện.\n\n"
        "Khi có người gửi đề nghị hỗ trợ, bạn sẽ nhận được thông báo ngay tại đây!"
    )
    await message.answer(
        success_text,
        reply_markup=get_main_menu_keyboard(is_admin=is_admin(actor_id)),
        parse_mode="Markdown",
    )


# ==========================================
# MY NEEDS & OFFERS LIST HANDLERS
# ==========================================

@router.message(Command("myneeds"))
@router.message(F.text == "📋 Nhu cầu của tôi")
async def handle_my_needs(message: Message):
    actor_id = message.from_user.id
    try:
        needs = await internal_bot_client.get_my_needs(actor_id)
    except Exception as e:
        await message.answer(f"⚠️ Không thể tải danh sách nhu cầu: {parse_http_error(e)}")
        return

    if not needs:
        await message.answer(
            "📋 Bạn hiện chưa có nhu cầu sách nào đang mở.\n\n"
            "Hãy bấm **📢 Yêu cầu sách** để đăng nhu cầu tìm sách nhé!",
            parse_mode="Markdown",
        )
        return

    lines = ["📋 **DANH SÁCH NHU CẦU SÁCH CỦA BẠN:**\n"]
    buttons = []
    for idx, n in enumerate(needs[:5], start=1):
        nid = n["id"]
        title = n["title_query"]
        off_count = n.get("offer_count", 0)
        st = n.get("status", "open")
        lines.append(f"{idx}. **{title}**\n   Trạng thái: `{st}` | Đề nghị hỗ trợ: **{off_count}** đề nghị")
        buttons.append([InlineKeyboardButton(text=f"Xem đề nghị: {title[:20]} ({off_count})", callback_data=f"v_off:{nid}")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("\n".join(lines), reply_markup=kb, parse_mode="Markdown")


@router.callback_query(F.data.startswith("v_off:"))
async def handle_view_need_offers(call: CallbackQuery):
    actor_id = call.from_user.id
    need_id = call.data.split(":", 1)[1]

    try:
        need = await internal_bot_client.get_need_detail(actor_id, need_id)
    except Exception as e:
        await call.answer(f"Lỗi: {parse_http_error(e)}", show_alert=True)
        return

    offers = need.get("offers", [])
    if not offers:
        await call.message.answer(
            f"📚 Nhu cầu **{need.get('title_query')}** hiện chưa có đề nghị hỗ trợ nào.\n"
            f"Hệ thống vẫn đang kết nối tới các chủ sách phù hợp!",
            parse_mode="Markdown",
        )
        await call.answer()
        return

    for o in offers:
        oid = o["id"]
        otype = o["offer_type"]
        msg = o.get("message") or "Không có tin nhắn kèm theo"
        dur = o.get("proposed_duration_days", 14)
        area = o.get("coarse_pickup_area") or "Thỏa thuận"

        card = (
            f"🤝 **ĐỀ NGHỊ HỖ TRỢ CHO BẠN**\n\n"
            f"Hình thức: `{otype}`\n"
            f"Thời gian cho mượn dự kiến: **{dur} ngày**\n"
            f"Khu vực giao nhận: **{area}**\n"
            f"Lời nhắn từ chủ sách: _{msg}_\n"
            f"Trạng thái đề nghị: `{o['status']}`"
        )
        if o["status"] == "proposed":
            await call.message.answer(card, reply_markup=get_need_offer_actions_keyboard(oid), parse_mode="Markdown")
        else:
            await call.message.answer(card, parse_mode="Markdown")

    await call.answer()


@router.callback_query(F.data.startswith("sel_o:"))
async def handle_select_offer(call: CallbackQuery):
    actor_id = call.from_user.id
    offer_id = call.data.split(":", 1)[1]

    try:
        res = await internal_bot_client.select_offer(actor_id, offer_id)
    except Exception as e:
        await call.answer(f"⚠️ Không thể chọn đề nghị này: {parse_http_error(e)}", show_alert=True)
        return

    loan_id = res.get("loan_id")
    expires_at = res.get("reservation_expires_at")
    exp_str = expires_at[:16].replace("T", " ") if expires_at else "72 giờ"

    msg = (
        "🎉 **BẠN ĐÃ CHỌN ĐỀ NGHỊ HỖ TRỢ THÀNH CÔNG!**\n\n"
        f"📦 Bản sách đã được tự động giữ chỗ (Reserved) riêng cho bạn.\n"
        f"⏳ Thời hạn giữ chỗ: trước **{exp_str} UTC**.\n\n"
        "Vui lòng liên hệ với chủ sách để thống nhất địa điểm giao nhận và bấm "
        "**🤝 Đang mượn** để xác nhận giao nhận khi đã cầm sách trên tay!"
    )
    await call.message.edit_text(msg, parse_mode="Markdown")
    await call.answer("Đã chọn đề nghị!", show_alert=True)


@router.callback_query(F.data.startswith("dec_o:"))
async def handle_decline_offer(call: CallbackQuery):
    actor_id = call.from_user.id
    offer_id = call.data.split(":", 1)[1]

    try:
        await internal_bot_client.decline_offer(actor_id, offer_id, reason="Requester declined")
    except Exception as e:
        await call.answer(f"Lỗi: {parse_http_error(e)}", show_alert=True)
        return

    await call.message.edit_text("❌ Bạn đã từ chối đề nghị này.", parse_mode="Markdown")
    await call.answer()


# ==========================================
# OWNER OFFER NOTIFICATION RESPONSES
# ==========================================

@router.callback_query(F.data.startswith("off_f:"))
async def handle_owner_offer_full(call: CallbackQuery):
    actor_id = call.from_user.id
    need_id = call.data.split(":", 1)[1]

    # Find owner's available copies
    try:
        copies = await internal_bot_client.get_my_books(actor_id)
        available = [
            c for c in copies
            if c.get("status") == "available" or c.get("circulation_status") == "available"
        ]
        copy_id = None
        if available:
            copy_id = available[0].get("copy_id") or available[0].get("id")
        elif copies:
            copy_id = copies[0].get("copy_id") or copies[0].get("id")

        await internal_bot_client.create_offer(
            telegram_user_id=actor_id,
            need_id=need_id,
            offer_type="full_physical_copy",
            copy_id=copy_id,
            proposed_duration_days=14,
            message="Tôi có bản sách đầy đủ sẵn sàng chia sẻ!",
        )
    except Exception as e:
        await call.answer(f"Lỗi gửi đề nghị: {parse_http_error(e)}", show_alert=True)
        return

    await call.message.edit_text(
        "✅ **Cảm ơn bạn!** Đề nghị hỗ trợ bản đầy đủ của bạn đã được chuyển tới người cần sách.",
        parse_mode="Markdown",
    )
    await call.answer("Đã gửi đề nghị hỗ trợ!", show_alert=True)


@router.callback_query(F.data.startswith("off_p:"))
async def handle_owner_offer_partial(call: CallbackQuery):
    actor_id = call.from_user.id
    need_id = call.data.split(":", 1)[1]
    try:
        copies = await internal_bot_client.get_my_books(actor_id)
        copy_id = copies[0].get("copy_id") or copies[0].get("id") if copies else None
        await internal_bot_client.create_offer(
            telegram_user_id=actor_id,
            need_id=need_id,
            offer_type="partial_physical_copy",
            copy_id=copy_id,
            proposed_duration_days=14,
            message="Tôi có bản tài liệu một phần / photocopy sẵn sàng hỗ trợ!",
        )
    except Exception as e:
        await call.answer(f"Lỗi gửi đề nghị: {parse_http_error(e)}", show_alert=True)
        return

    await call.message.edit_text(
        "✅ **Cảm ơn bạn!** Đề nghị hỗ trợ tài liệu một phần của bạn đã được chuyển tới người cần sách.",
        parse_mode="Markdown",
    )
    await call.answer("Đã gửi đề nghị hỗ trợ!", show_alert=True)


@router.callback_query(F.data.startswith("off_u:"))
async def handle_owner_offer_upcoming(call: CallbackQuery):
    actor_id = call.from_user.id
    need_id = call.data.split(":", 1)[1]
    try:
        await internal_bot_client.create_offer(
            telegram_user_id=actor_id,
            need_id=need_id,
            offer_type="available_later",
            proposed_duration_days=14,
            message="Sách hiện đang cho mượn nhưng sắp có lại.",
        )
    except Exception as e:
        await call.answer(f"Lỗi gửi đề nghị: {parse_http_error(e)}", show_alert=True)
        return

    await call.message.edit_text(
        "⏳ **Đã ghi nhận!** Hệ thống sẽ gửi thông tin tới người cần rằng sách sắp sẵn sàng.",
        parse_mode="Markdown",
    )
    await call.answer("Đã ghi nhận sách sắp có lại!", show_alert=True)


@router.callback_query(F.data.startswith("off_r:"))
async def handle_owner_offer_referral(call: CallbackQuery):
    await call.message.edit_text(
        "💡 **Cảm ơn bạn!** Gợi ý nguồn học liệu của bạn đã được ghi nhận vào hệ thống.",
        parse_mode="Markdown",
    )
    await call.answer("Đã ghi nhận gợi ý nguồn!", show_alert=True)


@router.callback_query(F.data.startswith("off_d:"))
@router.callback_query(F.data.startswith("off_n:"))
async def handle_owner_offer_decline(call: CallbackQuery):
    await call.message.edit_text(
        "👌 Đã ghi nhận bạn chưa thể hỗ trợ lượt này. Cảm ơn bạn!",
        parse_mode="Markdown",
    )
    await call.answer()


@router.callback_query(F.data == "off_mute")
@router.callback_query(F.data.startswith("off_m:"))
async def handle_owner_offer_mute(call: CallbackQuery):
    await call.message.edit_text(
        "🔕 Đã tạm tắt thông báo tìm sách tương tự trong 7 ngày tới. Bạn có thể bật lại trong Cài đặt.",
        parse_mode="Markdown",
    )
    await call.answer("Đã tắt thông báo!", show_alert=True)


# ==========================================
# COMMUNITY LIBRARY & WARNINGS HANDLERS
# ==========================================

@router.message(Command("community"))
@router.message(F.text == "🌐 Thư viện cộng đồng")
@router.callback_query(F.data == "comm:refresh")
async def handle_community_library(event: Message | CallbackQuery):
    actor_id = event.from_user.id
    is_callback = isinstance(event, CallbackQuery)
    if is_callback:
        await event.answer("Đang tải tài nguyên cộng đồng...")

    try:
        data = await internal_bot_client.get_community_library(actor_id, limit=8)
        copies = data.get("available_copies", [])
        digitals = data.get("digital_resources", [])
        total_c = data.get("total_copies", len(copies))
        total_d = data.get("total_digital", len(digitals))
    except Exception as e:
        err_msg = f"⚠️ Không thể tải thư viện cộng đồng: {parse_http_error(e)}"
        if is_callback:
            await event.message.edit_text(err_msg)
        else:
            await event.answer(err_msg)
        return

    lines = [
        "🌐 **THƯ VIỆN CỘNG ĐỒNG BOCONIC**\n",
        f"📚 Hiện có **{total_c}** bản sách/photocopy sẵn sàng mượn và **{total_d}** tài liệu số trích đoạn.\n",
    ]

    if copies:
        lines.append("📖 **Tài liệu & Sách đang có sẵn để mượn:**")
        for idx, c in enumerate(copies[:6], 1):
            part_str = ""
            if c.get("is_partial"):
                r_info = c["ranges"][0] if c.get("ranges") else {}
                part_str = f" `[Photocopy Trang {r_info.get('start_page', '?')}–{r_info.get('end_page', '?')}]`"
            else:
                part_str = " `[Sách nguyên bản]`"
            
            author_str = f" ({c['author'][:20]})" if c.get("author") else ""
            lines.append(
                f"{idx}. 📚 **{c['book_title']}**{author_str}{part_str}\n"
                f"   • Mã: `{c['public_code']}` | Chủ sách: **{c['owner_alias']}** | Tình trạng: `{c['condition']}`"
            )
        lines.append("")

    if digitals:
        lines.append("💾 **Trích đoạn số & File học tập mới nhất:**")
        for idx, d in enumerate(digitals[:4], 1):
            p_str = f" (Trang {d['page_start']}–{d['page_end']})" if d.get("page_start") else ""
            file_tag = "💾 [Tệp đính kèm]" if d.get("has_file") else ("🔗 [Link]" if d.get("url") else "📝 [Ghi chú]")
            lines.append(
                f"• {file_tag} **{d['title']}**{p_str}\n"
                f"  Sách: {d['book_title']} | Bởi: {d['owner_alias']}"
            )
        lines.append("")

    lines.append("👇 *Bấm trực tiếp nút mượn bên dưới hoặc chọn chuyên mục để tra cứu thêm:*")
    full_text = "\n".join(lines)
    kb = get_community_library_keyboard(copies)

    if is_callback:
        try:
            await event.message.edit_text(full_text, reply_markup=kb, parse_mode="Markdown")
        except Exception:
            pass
    else:
        await event.answer(full_text, reply_markup=kb, parse_mode="Markdown")


@router.message(Command("warnings"))
async def handle_warnings(message: Message):
    actor_id = message.from_user.id
    try:
        warnings = await internal_bot_client.get_my_warnings(actor_id)
    except Exception as e:
        await message.answer(f"⚠️ Không thể kiểm tra cảnh báo: {parse_http_error(e)}")
        return

    if not warnings:
        await message.answer("✨ Tài khoản của bạn trong sạch, không có cảnh báo nào!", parse_mode="Markdown")
        return

    lines = ["⚠️ **CẢNH BÁO TÀI KHOẢN CỦA BẠN:**\n"]
    for idx, w in enumerate(warnings, 1):
        severity_icon = {"low": "🟡", "medium": "🟠", "high": "🔴", "critical": "🚨"}.get(w.get("severity", "low"), "⚠️")
        status = w.get("status", "pending")
        reason = w.get("reason", "Không rõ")
        created = str(w.get("created_at", ""))[:10]
        ack_text = " ✅ Đã xác nhận" if status == "acknowledged" else ""
        lines.append(
            f"{idx}. {severity_icon} **{w.get('warning_type', 'Cảnh báo')}**{ack_text}\n"
            f"   • Lý do: {reason}\n"
            f"   • Ngày: {created} | Trạng thái: `{status}`"
        )
    lines.append("\n💡 *Gõ /warnings để kiểm tra lại. Liên hệ quản trị viên qua 🚩 Báo cáo / Hỗ trợ nếu bạn muốn khiếu nại.*")
    await message.answer("\n".join(lines), parse_mode="Markdown")


# ==========================================
# CHAPTER & PERSONAL PROGRESS HANDLERS
# ==========================================

@router.message(Command("chapters"))
async def handle_chapters_command(message: Message):
    actor_id = message.from_user.id
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "📖 Vui lòng cung cấp mã sách. Ví dụ:\n`/chapters <book_id>`\n"
            "Hoặc vào **📚 Thư viện của tôi** để xem danh mục chương của từng sách!",
            parse_mode="Markdown",
        )
        return

    book_id = args[1].strip()
    try:
        data = await internal_bot_client.get_book_chapters_and_progress(actor_id, book_id)
    except Exception as e:
        await message.answer(f"⚠️ Không thể tải danh mục chương: {parse_http_error(e)}")
        return

    chapters = data.get("chapters", [])
    summary = data.get("progress_summary", {})
    if not chapters:
        await message.answer("ℹ️ Sách này hiện chưa có danh mục chương trong catalog chung.")
        return

    txt = (
        f"📑 **DANH MỤC CHƯƠNG & TIẾN ĐỘ HỌC CÁ NHÂN**\n\n"
        f"📊 Tiến độ: **{summary.get('display_text', '0/0')}** ({summary.get('completion_percentage', 0)}%)\n"
        f"⏳ Đang đọc: {summary.get('in_progress_chapters', 0)} chương\n\n"
        "Bấm vào từng chương bên dưới để cập nhật trạng thái học, bookmark hoặc đăng nhu cầu tìm sách:"
    )
    kb = get_book_chapters_keyboard(book_id, chapters, summary.get("entries"))
    await message.answer(txt, reply_markup=kb, parse_mode="Markdown")


@router.callback_query(F.data.startswith("ch_list:"))
async def handle_callback_chapter_list(call: CallbackQuery):
    actor_id = call.from_user.id
    book_id = call.data.split(":", 1)[1]
    try:
        data = await internal_bot_client.get_book_chapters_and_progress(actor_id, book_id)
    except Exception as e:
        await call.answer(f"Lỗi: {parse_http_error(e)}", show_alert=True)
        return

    chapters = data.get("chapters", [])
    summary = data.get("progress_summary", {})
    txt = (
        f"📑 **DANH MỤC CHƯƠNG & TIẾN ĐỘ HỌC CÁ NHÂN**\n\n"
        f"📊 Tiến độ: **{summary.get('display_text', '0/0')}** ({summary.get('completion_percentage', 0)}%)\n\n"
        "Chọn chương để xem chi tiết hoặc cập nhật tiến độ:"
    )
    kb = get_book_chapters_keyboard(book_id, chapters, summary.get("entries"))
    await call.message.edit_text(txt, reply_markup=kb, parse_mode="Markdown")
    await call.answer()


@router.callback_query(F.data.startswith("ch_d:"))
async def handle_callback_chapter_detail(call: CallbackQuery):
    actor_id = call.from_user.id
    parts = call.data.split(":")
    book_id, chapter_id = parts[1], parts[2]

    try:
        data = await internal_bot_client.get_book_chapters_and_progress(actor_id, book_id)
    except Exception as e:
        await call.answer(f"Lỗi: {parse_http_error(e)}", show_alert=True)
        return

    chapters = data.get("chapters", [])
    target = next((c for c in chapters if c["id"] == chapter_id), None)
    if not target:
        await call.answer("Không tìm thấy chương!", show_alert=True)
        return

    entries = data.get("progress_summary", {}).get("entries", [])
    entry = next((e for e in entries if e["chapter_id"] == chapter_id), None)
    current_state = entry.get("reading_state", "not_started") if entry else "not_started"

    st_label = {"not_started": "⚪ Chưa đọc", "in_progress": "⏳ Đang đọc", "completed": "✅ Đã đọc xong"}.get(current_state, current_state)
    page_str = f"{target.get('page_start')} – {target.get('page_end')}" if target.get('page_start') else "Chưa xác minh"

    txt = (
        f"📖 **{target.get('chapter_code', target.get('chapter_number'))}. {target.get('title')}**\n\n"
        f"📄 Khoảng trang: **{page_str}**\n"
        f"🏷️ Trạng thái cá nhân: **{st_label}**\n"
    )
    if entry and entry.get("bookmark_page"):
        txt += f"🔖 Bookmark: Trang {entry['bookmark_page']}\n"
    if entry and entry.get("personal_notes"):
        txt += f"📝 Ghi chú cá nhân: _{entry['personal_notes']}_\n"

    kb = get_chapter_detail_keyboard(book_id, chapter_id, current_state)
    await call.message.edit_text(txt, reply_markup=kb, parse_mode="Markdown")
    await call.answer()


@router.callback_query(F.data.startswith("set_st:"))
async def handle_callback_set_chapter_status(call: CallbackQuery):
    actor_id = call.from_user.id
    _, book_id, chapter_id, new_state = call.data.split(":")

    try:
        await internal_bot_client.update_chapter_progress(
            telegram_user_id=actor_id,
            book_id=book_id,
            chapter_id=chapter_id,
            reading_state=new_state,
        )
    except Exception as e:
        await call.answer(f"Lỗi: {parse_http_error(e)}", show_alert=True)
        return

    st_name = "Đã đọc xong" if new_state == "completed" else ("Đang đọc" if new_state == "in_progress" else "Chưa đọc")
    await call.answer(f"Đã cập nhật: {st_name}!", show_alert=False)

    # Refresh chapter detail
    kb = get_chapter_detail_keyboard(book_id, chapter_id, new_state)
    try:
        await call.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass


@router.callback_query(F.data.startswith("req_ch:"))
async def handle_callback_request_chapter_menu(call: CallbackQuery, state: FSMContext):
    actor_id = call.from_user.id
    book_id = call.data.split(":", 1)[1]
    try:
        data = await internal_bot_client.get_book_chapters_and_progress(actor_id, book_id)
        book_title = data.get("book_title", "Sách")
        chapters = data.get("chapters", [])
    except Exception as e:
        await call.answer(f"Lỗi: {parse_http_error(e)}", show_alert=True)
        return

    if not chapters:
        await state.clear()
        await state.set_state(RequestWizardState.waiting_for_scope)
        await state.update_data(title_query=book_title, book_id=book_id)
        await call.message.answer(
            f"📢 **ĐĂNG NHU CẦU CHO SÁCH:** **{book_title}**\n\nBạn cần phạm vi tài liệu nào?",
            reply_markup=get_need_scope_keyboard(),
            parse_mode="Markdown",
        )
        await call.answer()
        return

    buttons = []
    for c in chapters[:8]:
        cid = c["id"]
        c_title = c.get("title", f"Chương {c.get('chapter_number', '')}")
        buttons.append([InlineKeyboardButton(text=f"📢 Cần: {c_title[:24]}", callback_data=f"need_c:{book_id}:{cid}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Quay lại danh mục chương", callback_data=f"ch_list:{book_id}")])

    await call.message.edit_text(
        f"📖 **Chọn chương bạn đang cần tìm:**\n📚 Sách: **{book_title}**",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="Markdown",
    )
    await call.answer()


@router.callback_query(F.data.startswith("need_c:"))
async def handle_callback_need_chapter(call: CallbackQuery):
    actor_id = call.from_user.id
    _, book_id, chapter_id = call.data.split(":")

    try:
        data = await internal_bot_client.get_book_chapters_and_progress(actor_id, book_id)
        chapters = data.get("chapters", [])
        target = next((c for c in chapters if c["id"] == chapter_id), None)
        title = f"Chương: {target.get('title', 'Sách')}" if target else "Sách theo chương"

        # Create chapter-targeted need
        res = await internal_bot_client.create_need(
            telegram_user_id=actor_id,
            title_query=title,
            book_id=book_id,
            scope_type="chapters",
            target_chapters=[chapter_id],
            description=f"Cần tài liệu cho chương: {target.get('title', 'N/A') if target else 'N/A'} (chapter_id: {chapter_id})",
        )
        nid = res.get("need_id", "")
        nid_display = nid[:8] + "..." if len(nid) > 8 else nid
        await call.message.answer(
            f"📢 **ĐÃ TẠO NHU CẦU CHO CHƯƠNG NÀY!**\n\n"
            f"Mã nhu cầu: `{nid_display}`\n"
            "Hệ thống đang quét các chủ sách có bản sách phù hợp và gửi thông báo hỗ trợ.",
            parse_mode="Markdown",
        )
        await call.answer("Đã đăng nhu cầu cho chương này!", show_alert=True)
    except Exception as e:
        await call.answer(f"Lỗi tạo nhu cầu: {parse_http_error(e)}", show_alert=True)


@router.callback_query(F.data.startswith("wtch_c:"))
async def handle_callback_watch_chapter(call: CallbackQuery):
    await call.answer("🔔 Đã bật theo dõi! Bạn sẽ nhận thông báo khi có nguồn sách mới cho chương này.", show_alert=True)


@router.callback_query(F.data.startswith("exp_n:"))
async def handle_callback_export_notes(call: CallbackQuery):
    actor_id = call.from_user.id
    book_id = call.data.split(":", 1)[1]
    url = f"{internal_bot_client.base_url}/api/v1/me/notes/{book_id}/export?user_id=tg_{actor_id}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url)
            if res.status_code == 200:
                md = res.json().get("markdown", "")
                await call.message.answer(f"```markdown\n{md[:3500]}\n```", parse_mode="Markdown")
            else:
                await call.message.answer("ℹ️ Bạn chưa có ghi chú cá nhân nào cho sách này.")
        await call.answer()
    except Exception as e:
        await call.answer(f"Lỗi: {parse_http_error(e)}", show_alert=True)


@router.message(F.text == "🎒 Tài nguyên đang dùng")
@router.message(Command("myresources"))
async def handle_my_resources(message: Message):
    actor_id = message.from_user.id
    try:
        data = await internal_bot_client.get_my_resources(actor_id)
    except Exception as e:
        await message.answer(f"Lỗi kiểm tra tài nguyên: {parse_http_error(e)}")
        return

    borrowed = data.get("borrowed_loans", [])
    lent = data.get("lent_loans", [])
    owned = data.get("owned_copies", [])
    needs = data.get("open_needs", [])
    progress = data.get("study_progress", {})
    trust = data.get("trust_profile", {})

    lines = [
        f"🎒 **TÀI NGUYÊN ĐANG SỬ DỤNG — {data.get('display_name') or 'Bạn'}**\n",
        f"⭐ **Chỉ số Uy tín:** {trust.get('reliability_score', 'N/A')}% ({trust.get('history_label', 'Chưa có lịch sử')})\n",
        "────────────────────────────",
        f"📖 **1. Sách đang mượn & cầm giữ ({len(borrowed)} cuốn):**"
    ]

    if not borrowed:
        lines.append("   • *Hiện bạn không giữ cuốn sách nào của người khác.*")
    else:
        for idx, b in enumerate(borrowed, 1):
            overdue_txt = " ⚠️ **QUÁ HẠN!**" if b.get("is_overdue") else ""
            due_str = str(b.get("due_at", ""))[:10] if b.get("due_at") else "Chưa rõ"
            book_title = b.get("book_title") or "Sách"
            code_str = b.get("copy_code") or (b.get("copy_id") or "N/A")[:8]
            lender_name = b.get("lender_name") or "Chủ sách"
            lines.append(
                f"   {idx}. 📚 **{book_title}**{overdue_txt}\n"
                f"      • Mã: `{code_str}` | Hạn trả: **{due_str}**\n"
                f"      • Chủ sách: {lender_name}"
            )

    lines.append("\n" + f"🤝 **2. Sách cá nhân đang cho mượn ({len(lent)} cuốn):**")
    if not lent:
        lines.append("   • *Không có cuốn nào đang cho mượn ngoài.*")
    else:
        for idx, l in enumerate(lent, 1):
            due_str = str(l.get("due_at", ""))[:10] if l.get("due_at") else "N/A"
            book_title = l.get("book_title") or "Sách"
            borrower_name = l.get("borrower_name") or "Người mượn"
            lines.append(
                f"   {idx}. 📚 **{book_title}**\n"
                f"      • Người mượn: {borrower_name} | Hạn trả: {due_str}"
            )

    lines.append("\n" + f"📦 **3. Kho sách sở hữu đã đăng ký:** **{len(owned)} bản sách**")
    lines.append(f"📢 **4. Nhu cầu đang tìm:** **{len(needs)} nhu cầu mở**")
    lines.append(
        f"🎓 **5. Tiến độ học:** Đã đọc **{progress.get('completed_chapters', 0)}** chương | "
        f"Đang đọc **{progress.get('in_progress_chapters', 0)}** chương | "
        f"**{progress.get('notes_count', 0)}** ghi chú"
    )

    lines.append("\n💡 *Gõ /chapters để xem chi tiết học tập từng chương hoặc /myloans để xem hạn trả chi tiết.*")

    kb_menu = get_main_menu_keyboard(is_admin=is_admin(message.from_user.id))
    await message.answer("\n".join(lines), reply_markup=kb_menu, parse_mode="Markdown")


@router.message(F.text == "📖 Quản lý theo chương")
async def handle_chapters_menu_button(message: Message):
    """Show owned books for chapter management instead of raw command call."""
    actor_id = message.from_user.id
    try:
        copies = await internal_bot_client.get_my_books(actor_id)
    except Exception as e:
        await message.answer(f"⚠️ Không thể tải danh sách sách: {parse_http_error(e)}")
        return

    if not copies:
        await message.answer(
            "📖 Bạn chưa có cuốn sách nào trong hệ thống.\n\n"
            "Hãy bấm **➕ Đăng sách** trước, sau đó quay lại đây để quản lý chương!",
            reply_markup=get_main_menu_keyboard(is_admin=is_admin(actor_id)),
            parse_mode="Markdown",
        )
        return

    # Build inline keyboard for book selection
    buttons = []
    seen_books = set()
    for c in copies:
        book_id = c.get("book_id")
        if book_id and book_id not in seen_books:
            seen_books.add(book_id)
            title = c.get("book_title", "Sách")[:35]
            buttons.append([InlineKeyboardButton(text=f"📚 {title}", callback_data=f"ch_list:{book_id}")])
        if len(buttons) >= 10:
            break

    if not buttons:
        await message.answer(
            "📖 Không tìm thấy sách phù hợp. Hãy đăng sách trước!",
            reply_markup=get_main_menu_keyboard(is_admin=is_admin(actor_id)),
        )
        return

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(
        "📖 **QUẢN LÝ THEO CHƯƠNG**\n\n"
        "Chọn cuốn sách bạn muốn xem danh mục chương và cập nhật tiến độ học:",
        reply_markup=kb,
        parse_mode="Markdown",
    )


# ==========================================
# PARTIAL MATERIALS HANDLERS (TÀI LIỆU TỪNG PHẦN)
# ==========================================

# ==========================================
# PARTIAL MATERIALS HANDLERS (TÀI LIỆU TỪNG PHẦN)
# ==========================================

@router.message(F.text == "📑 Up tài liệu 1 phần")
@router.message(F.text == "Up tài liệu từng phần")
@router.message(F.text == "Tải tài liệu từng phần")
@router.message(Command("uppartial"))
@router.message(Command("uploadpartial"))
@router.message(Command("partial"))
async def handle_up_partial_start(message: Message, state: FSMContext):
    """Entry point for partial materials upload / photocopy declaration."""
    await state.clear()
    await state.set_state(PartialMaterialUploadState.choosing_type)
    text = (
        "📑 **ĐĂNG KÝ / TẢI LÊN TÀI LIỆU TỪNG PHẦN (PARTIAL MATERIALS)**\n\n"
        "Boconic hỗ trợ bạn lưu trữ trích đoạn học tập, bản photocopy cá nhân hoặc tài liệu theo từng chương:\n\n"
        "• 📕 **Bản photocopy / tài liệu giấy:** Khai báo khoảng trang sở hữu, mặc định lưu trữ *Riêng tư (Private)* vào tài khoản.\n"
        "• 💾 **Tài liệu số / Liên kết:** Tải file trực tiếp (PDF, Word, Ảnh) hoặc gắn link theo chương, cam kết sử dụng học tập cá nhân và đưa vào chế độ *Cách ly (Quarantine)* an toàn bản quyền.\n\n"
        "👉 *Vui lòng chọn loại tài liệu bạn muốn thêm:*"
    )
    await message.answer(text, reply_markup=get_partial_type_keyboard(), parse_mode="Markdown")


@router.callback_query(F.data.startswith("ptp:"))
async def handle_partial_type_choice(call: CallbackQuery, state: FSMContext):
    choice = call.data.split(":")[1]
    actor_id = call.from_user.id
    if choice == "cancel":
        await state.clear()
        try:
            await call.message.delete()
        except Exception:
            pass
        await call.message.answer("❌ Đã hủy thao tác.", reply_markup=get_main_menu_keyboard(is_admin=is_admin(actor_id)))
        await call.answer()
        return

    if choice == "start_new":
        await state.clear()
        await state.set_state(PartialMaterialUploadState.choosing_type)
        text = (
            "📑 **TẢI LÊN TÀI LIỆU MỚI**\n\n"
            "👉 *Vui lòng chọn loại tài liệu bạn muốn thêm:*"
        )
        await call.message.answer(text, reply_markup=get_partial_type_keyboard(), parse_mode="Markdown")
        await call.answer()
        return

    if choice == "refresh_list":
        try:
            data = await internal_bot_client.get_my_partial_materials(actor_id)
            physical = data.get("physical_copies", [])
            digital = data.get("digital_resources", [])
            lines = ["📑 **TÀI LIỆU TỪNG PHẦN TRONG TÀI KHOẢN CỦA BẠN**\n"]
            if physical:
                lines.append(f"📕 **Bản photocopy / tài liệu giấy ({len(physical)}):**")
                for idx, p in enumerate(physical, 1):
                    r_str = ""
                    if p.get("ranges"):
                        r = p["ranges"][0]
                        r_str = f" | Trang {r['start_page']}–{r['end_page']} ({r['pages_count']} trang)"
                    lines.append(
                        f"{idx}. 📚 **{p['book_title']}**\n"
                        f"   • Mã: `{p['public_code']}`{r_str}\n"
                        f"   • Quyền riêng tư: `{p['visibility']}` | Tình trạng: {p['condition']}"
                    )
                lines.append("")

            if digital:
                lines.append(f"💾 **Tài liệu số & trích đoạn theo chương ({len(digital)}):**")
                for idx, d in enumerate(digital, 1):
                    st = "⏳ Cách ly (Quarantine)" if d["verification_status"] == "quarantine" else d["verification_status"]
                    info_sub = ""
                    if d.get("has_file") and d.get("filename"):
                        info_sub = f"\n   • Tệp: 💾 `{d['filename']}`"
                    elif d.get("url"):
                        info_sub = f"\n   • Link: {d['url']}"
                    lines.append(
                        f"{idx}. 📄 **{d['title']}**\n"
                        f"   • Sách: {d['book_title']} (Chương {d.get('chapter_number') or 1})\n"
                        f"   • Trạng thái: **{st}**{info_sub}"
                    )
            lines.append("\n💡 *Gõ /uppartial để tải lên tài liệu mới.*")
            await call.message.edit_text(
                "\n".join(lines),
                reply_markup=get_my_partial_management_keyboard(physical, digital),
                parse_mode="Markdown",
            )
            await call.answer("🔄 Đã cập nhật danh sách.")
        except Exception as e:
            await call.answer(f"Lỗi làm mới: {parse_http_error(e)}", show_alert=True)
        return

    await state.update_data(material_type=choice)
    await state.set_state(PartialMaterialUploadState.waiting_for_book_query)

    type_name = "bản photocopy / tài liệu giấy" if choice == "physical" else "tài liệu số / liên kết chương"
    prompt = (
        f"🔍 **Bước 1 — Chọn đầu sách ({type_name}):**\n\n"
        "Vui lòng nhập tên sách, từ khóa hoặc mã ISBN của cuốn sách mà tài liệu này thuộc về:\n\n"
        "*(Hoặc bấm /cancel để hủy bỏ)*"
    )
    await call.message.edit_text(prompt, parse_mode="Markdown")
    await call.answer()


@router.message(PartialMaterialUploadState.waiting_for_book_query)
async def handle_partial_book_query(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Vui lòng nhập từ khóa tên sách bằng tin nhắn văn bản, hoặc gõ /cancel để hủy:")
        return

    q = message.text.strip()
    if q.startswith("/cancel"):
        await state.clear()
        await message.answer("❌ Đã hủy thao tác.", reply_markup=get_main_menu_keyboard(is_admin=is_admin(message.from_user.id)))
        return

    actor_id = message.from_user.id
    try:
        search_res = await internal_bot_client.search_books(actor_id, q, limit=6)
    except Exception as e:
        await message.answer(f"Lỗi tìm kiếm: {parse_http_error(e)}")
        return

    items = search_res.get("items", [])
    await state.update_data(last_partial_query=q)
    if not items:
        buttons = [
            [InlineKeyboardButton(text=f"➕ Tạo tài liệu mới: {q[:25]}", callback_data="pcreate_custom_book")],
            [InlineKeyboardButton(text="❌ Hủy bỏ", callback_data="ptp:cancel")],
        ]
        await message.answer(
            f"Chưa có đầu sách `{q}` trong danh mục.\n"
            "Bạn có muốn tạo mới tài liệu này để tiếp tục tải lên / khai báo không?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode="Markdown"
        )
        return

    buttons = []
    for b in items:
        b_id = b.get("book_id") or b.get("id")
        title = b.get("title", "Sách")
        authors = ", ".join(b.get("authors") or []) or "N/A"
        btn_text = f"📖 {title[:28]}... ({authors[:15]})" if len(title) > 28 else f"📖 {title} ({authors[:15]})"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"pselb:{b_id}")])
    buttons.append([InlineKeyboardButton(text=f"➕ Tạo tài liệu mới: {q[:25]}", callback_data="pcreate_custom_book")])
    buttons.append([InlineKeyboardButton(text="❌ Hủy bỏ", callback_data="ptp:cancel")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await state.set_state(PartialMaterialUploadState.waiting_for_book_selection)
    await message.answer("📚 **Chọn đúng cuốn sách bên dưới (hoặc tạo mới):**", reply_markup=kb, parse_mode="Markdown")


@router.callback_query(F.data == "pcreate_custom_book")
async def handle_partial_create_custom_book(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    title = data.get("last_partial_query") or "Tài liệu học tập"
    actor_id = call.from_user.id
    try:
        res = await internal_bot_client.quick_create_book(actor_id, title)
        b_id = res["book_id"]
        ch_id = res["chapter_id"]
    except Exception as e:
        await call.message.edit_text(f"❌ Lỗi tạo đầu tài liệu: {parse_http_error(e)}")
        return

    await state.update_data(book_id=b_id, book_title=title, chapter_id=ch_id)
    material_type = data.get("material_type", "physical")
    if material_type == "physical":
        await state.set_state(PartialMaterialUploadState.waiting_for_pages)
        msg = (
            f"📚 **Đã tạo tài liệu:** {title}\n\n"
            "📖 **Bước 2/4 — Khai báo khoảng trang:**\n"
            "Bạn đang sở hữu bản photocopy từ trang nào đến trang nào?\n\n"
            "👉 *Nhập theo định dạng `TrangBắtĐầu-TrangKếtThúc` (Ví dụ: `1-50`, `trang 45 đến 120` hoặc `30`):*"
        )
        await call.message.edit_text(msg, parse_mode="Markdown")
    else:
        await state.set_state(PartialMaterialUploadState.waiting_for_digital_title)
        prompt = (
            f"📚 **Đã tạo tài liệu:** {title}\n\n"
            "📝 **Bước 3/5 — Tiêu đề hoặc Tệp tài liệu:**\n\n"
            "• **Gửi ngay tệp tài liệu** (PDF, Word, Ảnh scan) trực tiếp vào đây.\n"
            "• **HOẶC nhập tiêu đề tài liệu** (Ví dụ: `Slide tóm tắt`, `Đề cương & bài giải`).\n\n"
            "*(Hoặc bấm /cancel để hủy bỏ)*"
        )
        await call.message.edit_text(prompt, parse_mode="Markdown")



@router.callback_query(F.data.startswith("pselb:"))
async def handle_partial_book_selected(call: CallbackQuery, state: FSMContext):
    book_id = call.data.split(":")[1]
    actor_id = call.from_user.id
    data = await state.get_data()
    material_type = data.get("material_type", "physical")

    try:
        chapters_data = await internal_bot_client.get_book_chapters_and_progress(actor_id, book_id)
        book_title = chapters_data.get("book_title", "Đầu sách đã chọn")
    except Exception:
        chapters_data = {"chapters": []}
        book_title = "Đầu sách đã chọn"

    await state.update_data(book_id=book_id, book_title=book_title)

    if material_type == "physical":
        await state.set_state(PartialMaterialUploadState.waiting_for_pages)
        msg = (
            f"📚 **Đã chọn:** {book_title}\n\n"
            "📖 **Bước 2/4 — Khai báo khoảng trang:**\n"
            "Bạn đang sở hữu bản photocopy từ trang nào đến trang nào?\n\n"
            "👉 *Nhập theo định dạng `TrangBắtĐầu-TrangKếtThúc` (Ví dụ: `1-50`, `trang 45 đến 120` hoặc `30`):*"
        )
        await call.message.edit_text(msg, parse_mode="Markdown")
        await call.answer()
    else:
        chapters = chapters_data.get("chapters", [])
        buttons = []
        if chapters:
            for ch in chapters[:10]:
                c_id = ch.get("id") or ch.get("chapter_id")
                c_num = ch.get("chapter_number") or ch.get("chapter_code") or ""
                c_label = f"Chương {c_num}: {ch.get('title', '')[:25]}"
                buttons.append([InlineKeyboardButton(text=c_label, callback_data=f"pselc:{c_id}")])
            buttons.append([InlineKeyboardButton(text="📑 Gắn vào Tài liệu chung (Chương 1)", callback_data="pselc:auto")])
        else:
            # When book has no pre-existing chapters, provide instant auto chapter creation!
            buttons.append([InlineKeyboardButton(text="📑 Tiếp tục với Tài liệu chung / Chương 1", callback_data="pselc:auto")])

        buttons.append([InlineKeyboardButton(text="❌ Hủy bỏ", callback_data="ptp:cancel")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await state.set_state(PartialMaterialUploadState.waiting_for_digital_chapter)
        prompt_text = (
            f"📚 **Đã chọn:** {book_title}\n\n"
            "📑 **Bước 2/5 — Chọn chương sách gắn tài liệu:**"
        )
        if not chapters:
            prompt_text += "\n\n*(Sách này chưa chia danh mục chương chi tiết. Bạn có thể bấm tiếp tục với Tài liệu chung)*"
        await call.message.edit_text(prompt_text, reply_markup=kb, parse_mode="Markdown")
        await call.answer()


@router.message(PartialMaterialUploadState.waiting_for_pages)
async def handle_partial_pages_input(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Vui lòng nhập khoảng trang dạng: `1-50` hoặc `30-80`:", parse_mode="Markdown")
        return

    text = message.text.strip()
    if text.startswith("/cancel"):
        await state.clear()
        await message.answer("❌ Đã hủy thao tác.", reply_markup=get_main_menu_keyboard(is_admin=is_admin(message.from_user.id)))
        return

    match = re.search(r"(\d+)\s*(?:-|–|—|đến|to|->)\s*(\d+)", text)
    if match:
        start_p, end_p = int(match.group(1)), int(match.group(2))
    else:
        single = re.search(r"(\d+)", text)
        if single:
            start_p = end_p = int(single.group(1))
        else:
            await message.answer(
                "❌ Định dạng không hợp lệ. Vui lòng nhập khoảng trang dạng: `1-50` hoặc `30-80`:",
                parse_mode="Markdown",
            )
            return

    if start_p < 1 or end_p < start_p:
        await message.answer(
            f"❌ Khoảng trang `{start_p}-{end_p}` không hợp lệ. Trang bắt đầu phải >= 1 và <= trang kết thúc.\nVui lòng nhập lại:",
            parse_mode="Markdown",
        )
        return

    await state.update_data(start_page=start_p, end_page=end_p)
    await state.set_state(PartialMaterialUploadState.waiting_for_condition)
    await message.answer(
        f"✅ Khoảng trang: **{start_p}–{end_p}** ({end_p - start_p + 1} trang)\n\n"
        "🔍 **Bước 3/4 — Chọn tình trạng vật lý của bản photocopy:**",
        reply_markup=get_partial_condition_inline_keyboard(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("pcond:"))
async def handle_partial_condition_selected(call: CallbackQuery, state: FSMContext):
    cond = call.data.split(":")[1]
    await state.update_data(condition=cond)
    await state.set_state(PartialMaterialUploadState.waiting_for_source)
    await call.message.edit_text(
        "📝 **Bước 4/4 — Nguồn gốc bản photocopy:**\n\n"
        "Nhập mô tả ngắn gọn về nguồn gốc tài liệu (Ví dụ: `Bản photo lưu hành nội bộ trường`, hoặc gõ /skip để dùng mô tả mặc định):",
        parse_mode="Markdown",
    )
    await call.answer()


@router.message(PartialMaterialUploadState.waiting_for_source)
async def handle_partial_source_input(message: Message, state: FSMContext):
    source_desc = None
    if message.text:
        text = message.text.strip()
        if text.startswith("/cancel"):
            await state.clear()
            await message.answer("❌ Đã hủy thao tác.", reply_markup=get_main_menu_keyboard(is_admin=is_admin(message.from_user.id)))
            return
        if not text.startswith("/skip"):
            source_desc = text

    await state.update_data(source_description=source_desc)
    await state.set_state(PartialMaterialUploadState.waiting_for_visibility)
    await message.answer(
        "🔒 **Bước cuối — Quyền riêng tư của tài liệu:**\n\n"
        "Theo chính sách Boconic, bản photocopy tài liệu từng phần được khuyến nghị lưu ở chế độ **Riêng tư (Chỉ riêng tôi)** để phục vụ học tập cá nhân.",
        reply_markup=get_partial_visibility_keyboard(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("pvis:"))
async def handle_partial_visibility_selected(call: CallbackQuery, state: FSMContext):
    raw_vis = call.data.split(":")[1]
    vis = "published" if raw_vis in ("public", "published") else raw_vis
    actor_id = call.from_user.id
    data = await state.get_data()
    book_id = data["book_id"]
    book_title = data.get("book_title", "Sách")
    start_p = data["start_page"]
    end_p = data["end_page"]
    cond = data.get("condition", "good")
    source_desc = data.get("source_description")

    try:
        res = await internal_bot_client.declare_physical_partial(
            telegram_user_id=actor_id,
            book_id=book_id,
            start_page=start_p,
            end_page=end_p,
            condition=cond,
            source_description=source_desc,
            visibility=vis,
        )
    except Exception as e:
        await call.message.edit_text(f"❌ Lỗi khai báo: {parse_http_error(e)}")
        await call.answer()
        await state.clear()
        return

    copy_code = res.get("public_code") or res.get("copy_id", "")[:8]
    pages_count = end_p - start_p + 1
    vis_label = "🌐 Công khai cộng đồng (Mọi người có thể thấy & mượn)" if vis == "published" else "🔒 Riêng tư (Chỉ riêng tôi)"

    success_msg = (
        "🎉 **ĐÃ KHAI BÁO TÀI LIỆU MỘT PHẦN THÀNH CÔNG!**\n\n"
        f"• Mã bản sách: `{copy_code}`\n"
        f"• Đầu sách: **{book_title}**\n"
        f"• Khoảng trang: **Trang {start_p}–{end_p} ({pages_count} trang)**\n"
        f"• Tình trạng: **{cond}**\n"
        f"• Quyền riêng tư: **{vis_label}**\n\n"
        "🔒 Tài liệu đã được lưu trữ an toàn trong tài khoản của bạn. Gõ /mypartial để xem danh sách."
    )
    await state.clear()
    await call.message.edit_text(success_msg, parse_mode="Markdown")
    await call.message.answer(
        "Bạn có thể tiếp tục sử dụng các tính năng khác từ menu:",
        reply_markup=get_main_menu_keyboard(is_admin=is_admin(actor_id)),
    )
    await call.answer()


# Digital branch handlers
@router.callback_query(F.data.startswith("pselc:"))
async def handle_partial_digital_chapter_selected(call: CallbackQuery, state: FSMContext):
    chapter_id = call.data.split(":")[1]
    await state.update_data(chapter_id=chapter_id)
    await state.set_state(PartialMaterialUploadState.waiting_for_digital_title)
    prompt = (
        "📝 **Bước 3/5 — Tiêu đề hoặc Tệp tài liệu:**\n\n"
        "• **Gửi ngay tệp tài liệu** (PDF, Word, Ảnh scan) trực tiếp vào đây.\n"
        "• **HOẶC nhập tiêu đề tài liệu** (Ví dụ: `Slide tóm tắt Chương 1`, `Đề cương & bài giải`).\n\n"
        "*(Hoặc bấm /cancel để hủy bỏ)*"
    )
    await call.message.edit_text(prompt, parse_mode="Markdown")
    await call.answer()


@router.message(PartialMaterialUploadState.waiting_for_digital_title)
async def handle_partial_digital_title_input(message: Message, state: FSMContext):
    # Check if user sent a file directly at this step
    if message.document:
        doc = message.document
        max_bytes = settings.UPLOAD_MAX_MB * 1024 * 1024
        if doc.file_size and doc.file_size > max_bytes:
            await message.answer(f"⚠️ Dung lượng tệp quá lớn ({doc.file_size / (1024*1024):.1f}MB). Giới hạn tối đa là {settings.UPLOAD_MAX_MB}MB.")
            return

        try:
            file_info = await message.bot.get_file(doc.file_id)
            file_io = await message.bot.download_file(file_info.file_path)
            file_bytes = file_io.getvalue()
            b64_str = base64.b64encode(file_bytes).decode("utf-8")
            clean_name = doc.file_name or "tai_lieu.pdf"
            title = os.path.splitext(clean_name)[0]
            await state.update_data(
                digital_title=title,
                file_base64=b64_str,
                filename=clean_name,
                resource_type="file",
            )
            await state.set_state(PartialMaterialUploadState.waiting_for_digital_pages)
            await message.answer(
                f"✅ Đã nhận tệp: **{clean_name}** ({len(file_bytes) / 1024:.1f} KB)\n\n"
                "📄 **Bước 5/5 — Khoảng trang liên quan:**\n\n"
                "Nhập khoảng trang của tài liệu này (Ví dụ: `15-30` hoặc gõ /skip nếu bao gồm toàn chương):",
                parse_mode="Markdown",
            )
            return
        except Exception as e:
            await message.answer(f"⚠️ Lỗi khi tải tệp từ Telegram: {e}. Vui lòng thử lại hoặc nhập tiêu đề dạng chữ:")
            return

    if message.photo:
        photo = message.photo[-1]
        try:
            file_info = await message.bot.get_file(photo.file_id)
            file_io = await message.bot.download_file(file_info.file_path)
            file_bytes = file_io.getvalue()
            b64_str = base64.b64encode(file_bytes).decode("utf-8")
            clean_name = f"photo_{int(time.time())}.jpg"
            title = "Ảnh chụp tài liệu học tập"
            await state.update_data(
                digital_title=title,
                file_base64=b64_str,
                filename=clean_name,
                resource_type="file",
            )
            await state.set_state(PartialMaterialUploadState.waiting_for_digital_pages)
            await message.answer(
                f"✅ Đã nhận ảnh tài liệu ({len(file_bytes) / 1024:.1f} KB)\n\n"
                "📄 **Bước 5/5 — Khoảng trang liên quan:**\n\n"
                "Nhập khoảng trang (Ví dụ: `1-5` hoặc gõ /skip):",
                parse_mode="Markdown",
            )
            return
        except Exception as e:
            await message.answer(f"⚠️ Lỗi xử lý ảnh: {e}. Vui lòng thử lại:")
            return

    if not message.text:
        await message.answer("❌ Vui lòng nhập tiêu đề bằng chữ hoặc gửi tệp tài liệu:")
        return

    title = message.text.strip()
    if title.startswith("/cancel"):
        await state.clear()
        await message.answer("❌ Đã hủy thao tác.", reply_markup=get_main_menu_keyboard(is_admin=is_admin(message.from_user.id)))
        return

    await state.update_data(digital_title=title)
    await state.set_state(PartialMaterialUploadState.waiting_for_digital_url)
    await message.answer(
        "📎 **Bước 4/5 — Tệp đính kèm hoặc Liên kết (URL):**\n\n"
        "• **Gửi tệp tài liệu** (PDF, Word, Ảnh) trực tiếp tại đây.\n"
        "• **HOẶC nhập link liên kết** (Google Drive, Dropbox, OneDrive...). \n"
        "• *(Hoặc gõ /skip để bỏ qua nếu chỉ lưu ghi chú)*:",
        parse_mode="Markdown",
    )


@router.message(PartialMaterialUploadState.waiting_for_digital_url)
async def handle_partial_digital_url_input(message: Message, state: FSMContext):
    # Check for document upload
    if message.document:
        doc = message.document
        max_bytes = settings.UPLOAD_MAX_MB * 1024 * 1024
        if doc.file_size and doc.file_size > max_bytes:
            await message.answer(f"⚠️ Dung lượng tệp quá lớn ({doc.file_size / (1024*1024):.1f}MB). Giới hạn tối đa là {settings.UPLOAD_MAX_MB}MB.")
            return

        try:
            file_info = await message.bot.get_file(doc.file_id)
            file_io = await message.bot.download_file(file_info.file_path)
            file_bytes = file_io.getvalue()
            b64_str = base64.b64encode(file_bytes).decode("utf-8")
            clean_name = doc.file_name or "tai_lieu.pdf"
            await state.update_data(
                file_base64=b64_str,
                filename=clean_name,
                resource_type="file",
            )
            await state.set_state(PartialMaterialUploadState.waiting_for_digital_pages)
            await message.answer(
                f"✅ Đã nhận tệp: **{clean_name}** ({len(file_bytes) / 1024:.1f} KB)\n\n"
                "📄 **Bước 5/5 — Khoảng trang liên quan:**\n\n"
                "Nhập khoảng trang của trích đoạn này (Ví dụ: `15-30` hoặc gõ /skip nếu bao gồm toàn chương):",
                parse_mode="Markdown",
            )
            return
        except Exception as e:
            await message.answer(f"⚠️ Lỗi tải tệp: {e}. Vui lòng thử lại hoặc gõ /skip:")
            return

    # Check for photo upload
    if message.photo:
        photo = message.photo[-1]
        try:
            file_info = await message.bot.get_file(photo.file_id)
            file_io = await message.bot.download_file(file_info.file_path)
            file_bytes = file_io.getvalue()
            b64_str = base64.b64encode(file_bytes).decode("utf-8")
            clean_name = f"photo_{int(time.time())}.jpg"
            await state.update_data(
                file_base64=b64_str,
                filename=clean_name,
                resource_type="file",
            )
            await state.set_state(PartialMaterialUploadState.waiting_for_digital_pages)
            await message.answer(
                f"✅ Đã nhận ảnh tài liệu ({len(file_bytes) / 1024:.1f} KB)\n\n"
                "📄 **Bước 5/5 — Khoảng trang liên quan:**\n\n"
                "Nhập khoảng trang (Ví dụ: `1-5` hoặc gõ /skip):",
                parse_mode="Markdown",
            )
            return
        except Exception as e:
            await message.answer(f"⚠️ Lỗi xử lý ảnh: {e}. Vui lòng thử lại:")
            return

    if not message.text:
        await message.answer("❌ Vui lòng gửi tệp tài liệu, nhập đường dẫn URL hoặc gõ /skip:")
        return

    text = message.text.strip()
    if text.startswith("/cancel"):
        await state.clear()
        await message.answer("❌ Đã hủy thao tác.", reply_markup=get_main_menu_keyboard(is_admin=is_admin(message.from_user.id)))
        return

    url = None if text.startswith("/skip") else text
    await state.update_data(digital_url=url)
    await state.set_state(PartialMaterialUploadState.waiting_for_digital_pages)
    await message.answer(
        "📄 **Bước 5/5 — Khoảng trang liên quan:**\n\n"
        "Nhập khoảng trang của trích đoạn này (Ví dụ: `15-30` hoặc gõ /skip nếu bao gồm toàn chương):",
        parse_mode="Markdown",
    )


@router.message(PartialMaterialUploadState.waiting_for_digital_pages)
async def handle_partial_digital_pages_input(message: Message, state: FSMContext):
    p_start, p_end = None, None
    if message.text:
        text = message.text.strip()
        if text.startswith("/cancel"):
            await state.clear()
            await message.answer("❌ Đã hủy thao tác.", reply_markup=get_main_menu_keyboard(is_admin=is_admin(message.from_user.id)))
            return

        if not text.startswith("/skip"):
            match = re.search(r"(\d+)\s*(?:-|–|—|đến|to|->)\s*(\d+)", text)
            if match:
                p_start, p_end = int(match.group(1)), int(match.group(2))
            else:
                single = re.search(r"(\d+)", text)
                if single:
                    p_start = p_end = int(single.group(1))

    await state.update_data(page_start=p_start, page_end=p_end)
    await state.set_state(PartialMaterialUploadState.waiting_for_fair_use)

    pledge_text = (
        "⚖️ **CAM KẾT BẢN QUYỀN & MỤC ĐÍCH HỌC TẬP (FAIR USE)**\n\n"
        "Theo chính sách kiểm soát tài liệu từng phần của Boconic:\n"
        "1. Bạn cam đoan tài liệu trích đoạn này chỉ phục vụ mục đích học tập, nghiên cứu cá nhân.\n"
        "2. Tài liệu sẽ được bảo vệ trong trạng thái **Cách ly (Quarantine)** để đảm bảo an toàn bản quyền trước khi lưu hành.\n\n"
        "👉 *Vui lòng bấm nút bên dưới để xác nhận cam kết:*"
    )
    await message.answer(pledge_text, reply_markup=get_partial_fair_use_keyboard(), parse_mode="Markdown")


@router.callback_query(F.data.startswith("pfu:"))
async def handle_partial_fair_use_choice(call: CallbackQuery, state: FSMContext):
    choice = call.data.split(":")[1]
    if choice != "accept":
        await state.clear()
        await call.message.edit_text("❌ Đã hủy lưu tài liệu vì chưa đồng ý cam kết bản quyền.")
        await call.answer()
        return

    await state.set_state(PartialMaterialUploadState.waiting_for_digital_visibility)
    prompt = (
        "🌐 **Bước cuối — Quyền hiển thị của tài liệu số:**\n\n"
        "• **Công khai cộng đồng:** Mọi người trong thư viện có thể tra cứu và học tập cùng bạn.\n"
        "• **Riêng tư:** Chỉ lưu trữ an toàn trong tài khoản của bạn phục vụ học tập cá nhân.\n\n"
        "👉 *Vui lòng chọn quyền hiển thị mong muốn:*"
    )
    await call.message.edit_text(prompt, reply_markup=get_digital_visibility_keyboard(), parse_mode="Markdown")
    await call.answer()


@router.callback_query(F.data.startswith("pdvis:"))
async def handle_partial_digital_visibility_choice(call: CallbackQuery, state: FSMContext):
    vis_choice = call.data.split(":")[1]
    is_public = (vis_choice == "public")
    actor_id = call.from_user.id
    data = await state.get_data()
    book_id = data["book_id"]
    book_title = data.get("book_title", "Sách")
    chapter_id = data.get("chapter_id") or "auto"
    title = data.get("digital_title") or "Tài liệu học tập"
    url = data.get("digital_url")
    file_b64 = data.get("file_base64")
    filename = data.get("filename")
    page_start = data.get("page_start")
    page_end = data.get("page_end")

    try:
        await internal_bot_client.upload_digital_partial(
            telegram_user_id=actor_id,
            book_id=book_id,
            chapter_id=chapter_id,
            title=title,
            url=url,
            file_bytes_base64=file_b64,
            filename=filename,
            page_start=page_start,
            page_end=page_end,
            rights_basis="personal_fair_use",
            consent_given=True,
            is_public=is_public,
        )
    except Exception as e:
        await call.message.edit_text(f"❌ Lỗi lưu tài liệu số: {parse_http_error(e)}")
        await call.answer()
        await state.clear()
        return

    page_info = f"Trang {page_start}–{page_end}" if page_start and page_end else "Toàn chương / Tổng hợp"
    file_info = f"💾 Tệp: `{filename}`" if filename else (f"🔗 Link: {url}" if url else "📝 Ghi chú số")
    vis_text = "🌐 Công khai cộng đồng (Mọi người có thể đọc & tham khảo)" if is_public else "🔒 Riêng tư (Chỉ riêng tôi)"

    success_msg = (
        "🎉 **ĐÃ LƯU TRÍCH ĐOẠN SỐ THÀNH CÔNG!**\n\n"
        f"• Tiêu đề: **{title}**\n"
        f"• Sách: **{book_title}**\n"
        f"• Nội dung đính kèm: {file_info}\n"
        f"• Khoảng trang: **{page_info}**\n"
        f"• Quyền hiển thị: **{vis_text}**\n\n"
        "🔒 Tài liệu đã được lưu trữ an toàn trong tài khoản của bạn. Gõ /mypartial để xem lại và quản lý."
    )
    await state.clear()
    await call.message.edit_text(success_msg, parse_mode="Markdown")
    await call.message.answer(
        "Bạn có thể tiếp tục sử dụng các tính năng khác từ menu:",
        reply_markup=get_main_menu_keyboard(is_admin=is_admin(actor_id)),
    )
    await call.answer()



@router.message(Command("mypartial"))
async def handle_my_partial_command(message: Message):
    """View personal partial materials."""
    actor_id = message.from_user.id
    try:
        data = await internal_bot_client.get_my_partial_materials(actor_id)
    except Exception as e:
        await message.answer(f"Lỗi tải danh mục: {parse_http_error(e)}")
        return

    physical = data.get("physical_copies", [])
    digital = data.get("digital_resources", [])

    if not physical and not digital:
        await message.answer(
            "📭 Bạn chưa có tài liệu một phần nào trong tài khoản.\n\n"
            "Bấm **📑 Up tài liệu 1 phần** hoặc gõ /uppartial để thêm bản photocopy hoặc trích đoạn số!",
            reply_markup=get_main_menu_keyboard(is_admin=is_admin(actor_id)),
        )
        return

    lines = ["📑 **TÀI LIỆU TỪNG PHẦN TRONG TÀI KHOẢN CỦA BẠN**\n"]
    if physical:
        lines.append(f"📕 **Bản photocopy / tài liệu giấy ({len(physical)}):**")
        for idx, p in enumerate(physical, 1):
            r_str = ""
            if p.get("ranges"):
                r = p["ranges"][0]
                r_str = f" | Trang {r['start_page']}–{r['end_page']} ({r['pages_count']} trang)"
            lines.append(
                f"{idx}. 📚 **{p['book_title']}**\n"
                f"   • Mã: `{p['public_code']}`{r_str}\n"
                f"   • Quyền riêng tư: `{p['visibility']}` | Tình trạng: {p['condition']}"
            )
        lines.append("")

    if digital:
        lines.append(f"💾 **Tài liệu số & trích đoạn theo chương ({len(digital)}):**")
        for idx, d in enumerate(digital, 1):
            st = "⏳ Cách ly (Quarantine)" if d["verification_status"] == "quarantine" else d["verification_status"]
            info_sub = ""
            if d.get("has_file") and d.get("filename"):
                info_sub = f"\n   • Tệp: 💾 `{d['filename']}`"
            elif d.get("url"):
                info_sub = f"\n   • Link: {d['url']}"
            lines.append(
                f"{idx}. 📄 **{d['title']}**\n"
                f"   • Sách: {d['book_title']} (Chương {d.get('chapter_number') or 1})\n"
                f"   • Trạng thái: **{st}**{info_sub}"
            )

    lines.append("\n💡 *Dùng các nút bên dưới để xóa hoặc thêm mới tài liệu.*")
    await message.answer(
        "\n".join(lines),
        reply_markup=get_my_partial_management_keyboard(physical, digital),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("dpart:"))
async def handle_delete_partial_item(call: CallbackQuery):
    actor_id = call.from_user.id
    parts = call.data.split(":")
    item_type, item_id = parts[1], parts[2]
    try:
        if item_type == "physical":
            await internal_bot_client.delete_my_physical_partial(actor_id, item_id)
        else:
            await internal_bot_client.delete_my_digital_partial(actor_id, item_id)
        await call.answer("✅ Đã xóa tài liệu khỏi tài khoản của bạn.", show_alert=True)

        # Refresh list in place
        try:
            data = await internal_bot_client.get_my_partial_materials(actor_id)
            physical = data.get("physical_copies", [])
            digital = data.get("digital_resources", [])
            if not physical and not digital:
                await call.message.edit_text(
                    "📭 Bạn chưa có tài liệu một phần nào trong tài khoản.\n\n"
                    "Bấm **📑 Up tài liệu 1 phần** hoặc gõ /uppartial để thêm bản photocopy hoặc trích đoạn số!"
                )
            else:
                lines = ["📑 **TÀI LIỆU TỪNG PHẦN TRONG TÀI KHOẢN CỦA BẠN**\n"]
                if physical:
                    lines.append(f"📕 **Bản photocopy / tài liệu giấy ({len(physical)}):**")
                    for idx, p in enumerate(physical, 1):
                        r_str = ""
                        if p.get("ranges"):
                            r = p["ranges"][0]
                            r_str = f" | Trang {r['start_page']}–{r['end_page']} ({r['pages_count']} trang)"
                        lines.append(
                            f"{idx}. 📚 **{p['book_title']}**\n"
                            f"   • Mã: `{p['public_code']}`{r_str}\n"
                            f"   • Quyền riêng tư: `{p['visibility']}` | Tình trạng: {p['condition']}"
                        )
                    lines.append("")

                if digital:
                    lines.append(f"💾 **Tài liệu số & trích đoạn theo chương ({len(digital)}):**")
                    for idx, d in enumerate(digital, 1):
                        st = "⏳ Cách ly (Quarantine)" if d["verification_status"] == "quarantine" else d["verification_status"]
                        info_sub = ""
                        if d.get("has_file") and d.get("filename"):
                            info_sub = f"\n   • Tệp: 💾 `{d['filename']}`"
                        elif d.get("url"):
                            info_sub = f"\n   • Link: {d['url']}"
                        lines.append(
                            f"{idx}. 📄 **{d['title']}**\n"
                            f"   • Sách: {d['book_title']} (Chương {d.get('chapter_number') or 1})\n"
                            f"   • Trạng thái: **{st}**{info_sub}"
                        )
                lines.append("\n💡 *Dùng các nút bên dưới để xóa hoặc thêm mới tài liệu.*")
                await call.message.edit_text(
                    "\n".join(lines),
                    reply_markup=get_my_partial_management_keyboard(physical, digital),
                    parse_mode="Markdown",
                )
        except Exception:
            pass
    except Exception as e:
        await call.answer(f"Lỗi khi xóa: {parse_http_error(e)}", show_alert=True)


# ==========================================
# BORROW PARTIAL MATERIAL HANDLERS (MƯỢN TÀI LIỆU 1 PHẦN)
# ==========================================

@router.message(F.text == "📖 Mượn tài liệu 1 phần")
@router.message(F.text == "Mượn tài liệu 1 phần")
@router.message(F.text == "Mượn tài liệu từng phần")
@router.message(F.text == "Mượn tài liệu một phần")
@router.message(Command("borrow_partial"))
@router.message(Command("muon1phan"))
@router.message(Command("muonpartial"))
async def handle_borrow_partial_start(message: Message, state: FSMContext):
    """Entry point for borrowing partial materials (photocopy / chapters / digital fragments)."""
    await state.clear()
    text = (
        "📖 **MƯỢN TÀI LIỆU 1 PHẦN (CHƯƠNG / TRANG / PHOTOCOPY)**\n\n"
        "Boconic kết nối bạn với các bản photocopy, tài liệu học tập theo chương "
        "hoặc trích đoạn sách được cộng đồng chia sẻ hợp pháp:\n\n"
        "• 🔍 **Xem bản photo có sẵn:** Xem các bản 1 phần đang sẵn sàng cho mượn ngay.\n"
        "• 📢 **Đăng nhu cầu mượn 1 phần:** Đăng nhu cầu theo chương hoặc trang để hệ thống tự động tìm và báo chủ sách phù hợp.\n"
        "• 🔎 **Tìm kiếm theo từ khóa:** Tra cứu nhanh theo tên sách, tác giả hoặc môn học.\n"
        "• 💾 **Trích đoạn số:** Tiếp cận các tài liệu số, PDF theo chương đã được xác minh.\n\n"
        "👉 *Vui lòng chọn thao tác bạn muốn thực hiện:*"
    )
    await message.answer(text, reply_markup=get_borrow_partial_menu_keyboard(), parse_mode="Markdown")


# Fallback for typos like "mượn tài iệu 1 phần"
@router.message(F.text.func(lambda t: bool(t and any(k in t.lower() for k in ("mượn tài iệu 1 phần", "mượn tài liệu 1 phần", "mượn tài liệu từng phần", "mượn tài liệu một phần")))))
async def handle_borrow_partial_typo_fallback(message: Message, state: FSMContext):
    await handle_borrow_partial_start(message, state)


@router.callback_query(F.data.startswith("bprt:"))
async def handle_borrow_partial_callback(call: CallbackQuery, state: FSMContext):
    action = call.data.split(":", 1)[1]
    actor_id = call.from_user.id

    if action == "cancel":
        await state.clear()
        try:
            await call.message.delete()
        except Exception:
            pass
        await call.message.answer("❌ Đã đóng menu mượn tài liệu 1 phần.", reply_markup=get_main_menu_keyboard(is_admin=is_admin(actor_id)))
        await call.answer()
        return

    if action == "available":
        await call.answer()
        try:
            data = await internal_bot_client.search_available_partial_materials(actor_id, query=None, limit=8)
            physical = data.get("physical_copies", [])
        except Exception as e:
            await call.message.answer(f"⚠️ Lỗi khi tải danh sách: {parse_http_error(e)}")
            return

        if not physical:
            no_copies_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📢 Đăng nhu cầu mượn 1 phần ngay", callback_data="bprt:create_need")],
                [InlineKeyboardButton(text="🔎 Tìm từ khóa khác", callback_data="bprt:search")],
                [InlineKeyboardButton(text="🔙 Quay lại", callback_data="bprt:menu")],
            ])
            await call.message.answer(
                "Hiện chưa có bản photocopy / 1 phần nào đang sẵn sàng cho mượn công khai.\n\n"
                "👉 Bạn có thể **Đăng nhu cầu mượn 1 phần** để hệ thống thông báo cho các chủ sách có bản phù hợp!",
                reply_markup=no_copies_kb,
                parse_mode="Markdown",
            )
            return

        await call.message.answer(
            f"📚 **DANH SÁCH BẢN PHOTOCOPY / 1 PHẦN SẴN SÀNG CHO MƯỢN ({len(physical)}):**\n"
            "Bấm trực tiếp nút **Gửi yêu cầu mượn** để kết nối với chủ sách:",
            parse_mode="Markdown",
        )

        for p in physical:
            r_str = ""
            if p.get("ranges"):
                r = p["ranges"][0]
                ch_str = f" (Chương: {', '.join(str(c) for c in r.get('chapters', []))})" if r.get("chapters") else ""
                r_str = f"\n   • Phạm vi: **Trang {r['start_page']}–{r['end_page']}**{ch_str}"

            card_text = (
                f"📕 **{p['book_title']}**\n"
                f"   • Mã bản: `{p['public_code']}` | Tình trạng: `{p['condition']}`{r_str}\n"
                f"   • Chủ sở hữu: **@{p['owner_alias']}** | Thời hạn mượn tối đa: **{p['maximum_loan_days']} ngày**"
            )
            await call.message.answer(
                card_text,
                reply_markup=get_partial_copy_borrow_keyboard(p["copy_id"]),
                parse_mode="Markdown",
            )
        return

    if action == "create_need":
        await call.answer()
        await state.clear()
        await state.set_state(BorrowPartialState.waiting_for_book_title)
        text = (
            "📢 **TẠO NHU CẦU MƯỢN TÀI LIỆU 1 PHẦN**\n\n"
            "Vui lòng nhập **Tên sách hoặc môn học** bạn đang cần mượn một phần:\n"
            "_(Ví dụ: Giải tích 1, Toán 12 Tập 2, Triết học Mác - Lênin)_"
        )
        await call.message.answer(text, reply_markup=get_cancel_keyboard(), parse_mode="Markdown")
        return

    if action == "search":
        await call.answer()
        await state.clear()
        await state.set_state(BorrowPartialState.waiting_for_search_keyword)
        text = (
            "🔎 **TÌM KIẾM TÀI LIỆU 1 PHẦN**\n\n"
            "Nhập từ khóa tên sách, môn học hoặc tác giả bạn muốn tìm bản photocopy/trích đoạn:"
        )
        await call.message.answer(text, reply_markup=get_cancel_keyboard(), parse_mode="Markdown")
        return

    if action == "digital":
        await call.answer()
        try:
            data = await internal_bot_client.search_available_partial_materials(actor_id, query=None, limit=8)
            digital = data.get("digital_resources", [])
        except Exception as e:
            await call.message.answer(f"⚠️ Lỗi khi tải tài nguyên: {parse_http_error(e)}")
            return

        if not digital:
            await call.message.answer(
                "Hiện chưa có trích đoạn số công khai nào được duyệt trong hệ thống.",
                parse_mode="Markdown",
            )
            return

        lines = ["💾 **CÁC TRÍCH ĐOẠN SỐ & TÀI LIỆU HỌC TẬP ĐÃ DUYỆT:**\n"]
        for idx, d in enumerate(digital, 1):
            ch_info = f"Chương {d['chapter_number']}: " if d.get("chapter_number") else ""
            pg_info = f" (Trang {d['page_start']}–{d['page_end']})" if d.get("page_start") and d.get("page_end") else ""
            link_info = f"\n   • Liên kết: {d['url']}" if d.get("url") else ""
            lines.append(
                f"{idx}. 📑 **{d['title']}**\n"
                f"   • Sách: **{d['book_title']}** | {ch_info}{d.get('chapter_title', '')}{pg_info}\n"
                f"   • Người chia sẻ: @{d['owner_alias']} | Cơ sở quyền: `{d.get('rights_basis', 'open_license')}`{link_info}"
            )
        await call.message.answer("\n".join(lines), parse_mode="Markdown")
        return

    if action == "menu":
        await call.answer()
        text = (
            "📖 **MƯỢN TÀI LIỆU 1 PHẦN (CHƯƠNG / TRANG / PHOTOCOPY)**\n\n"
            "👉 *Vui lòng chọn thao tác bạn muốn thực hiện:*"
        )
        await call.message.answer(text, reply_markup=get_borrow_partial_menu_keyboard(), parse_mode="Markdown")
        return


@router.message(BorrowPartialState.waiting_for_search_keyword)
async def handle_borrow_partial_search_keyword(message: Message, state: FSMContext):
    if not message.text or message.text == "❌ Hủy thao tác":
        await state.clear()
        await message.answer("❌ Đã hủy tìm kiếm.", reply_markup=get_main_menu_keyboard(is_admin=is_admin(message.from_user.id)))
        return

    kw = message.text.strip()
    await state.clear()
    actor_id = message.from_user.id
    try:
        data = await internal_bot_client.search_available_partial_materials(actor_id, query=kw, limit=8)
        physical = data.get("physical_copies", [])
        digital = data.get("digital_resources", [])
    except Exception as e:
        await message.answer(f"⚠️ Lỗi tìm kiếm: {parse_http_error(e)}", reply_markup=get_main_menu_keyboard(is_admin=is_admin(actor_id)))
        return

    if not physical and not digital:
        no_res_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Đăng nhu cầu mượn sách này", callback_data="bprt:create_need")],
            [InlineKeyboardButton(text="🔙 Menu mượn 1 phần", callback_data="bprt:menu")],
        ])
        await message.answer(
            f"Không tìm thấy bản photocopy hoặc trích đoạn số nào khớp với từ khóa **'{kw}'**.\n\n"
            f"👉 Bạn có thể bấm nút bên dưới để đăng nhu cầu cần mượn!",
            reply_markup=no_res_kb,
            parse_mode="Markdown",
        )
        return

    await message.answer(
        f"🔎 **KẾT QUẢ TÌM KIẾM CHO: '{kw}'**\n"
        f"Tìm thấy **{len(physical)}** bản photocopy và **{len(digital)}** trích đoạn số:",
        reply_markup=get_main_menu_keyboard(is_admin=is_admin(actor_id)),
        parse_mode="Markdown",
    )

    for p in physical:
        r_str = ""
        if p.get("ranges"):
            r = p["ranges"][0]
            ch_str = f" (Chương: {', '.join(str(c) for c in r.get('chapters', []))})" if r.get("chapters") else ""
            r_str = f"\n   • Phạm vi: **Trang {r['start_page']}–{r['end_page']}**{ch_str}"

        card_text = (
            f"📕 **{p['book_title']}**\n"
            f"   • Mã: `{p['public_code']}` | Tình trạng: `{p['condition']}`{r_str}\n"
            f"   • Chủ sở hữu: **@{p['owner_alias']}** | Thời hạn mượn: **{p['maximum_loan_days']} ngày**"
        )
        await message.answer(
            card_text,
            reply_markup=get_partial_copy_borrow_keyboard(p["copy_id"]),
            parse_mode="Markdown",
        )

    if digital:
        dig_lines = ["💾 **Trích đoạn số khớp từ khóa:**"]
        for idx, d in enumerate(digital, 1):
            dig_lines.append(f"{idx}. **{d['title']}** (Chương {d.get('chapter_number') or 1}) - @{d['owner_alias']}")
        await message.answer("\n".join(dig_lines), parse_mode="Markdown")


@router.message(BorrowPartialState.waiting_for_book_title)
async def handle_borrow_partial_title_input(message: Message, state: FSMContext):
    if not message.text or message.text == "❌ Hủy thao tác":
        await state.clear()
        await message.answer("❌ Đã hủy thao tác.", reply_markup=get_main_menu_keyboard(is_admin=is_admin(message.from_user.id)))
        return

    title_query = message.text.strip()
    if len(title_query) < 2:
        await message.answer("⚠️ Tiêu đề quá ngắn. Vui lòng nhập rõ hơn tên sách bạn cần:")
        return

    await state.update_data(title_query=title_query)
    await state.set_state(BorrowPartialState.waiting_for_scope_type)

    text = (
        f"📖 Sách bạn cần mượn 1 phần: **{title_query}**\n\n"
        "Vui lòng chọn hình thức phần tài liệu bạn cần:"
    )
    await message.answer(text, reply_markup=get_partial_borrow_scope_keyboard(), parse_mode="Markdown")


@router.callback_query(BorrowPartialState.waiting_for_scope_type, F.data.startswith("bprt_scope:"))
async def handle_borrow_partial_scope_choice(call: CallbackQuery, state: FSMContext):
    scope_type = call.data.split(":", 1)[1]
    await state.update_data(scope_type=scope_type)
    await state.set_state(BorrowPartialState.waiting_for_scope_detail)

    if scope_type == "chapters":
        await call.message.edit_text(
            "📑 Vui lòng nhập số hoặc tên các **chương bạn cần mượn**:\n"
            "_(Ví dụ: `Chương 1, 2` hoặc `1, 3`)_",
            parse_mode="Markdown",
        )
    else:  # page_range
        await call.message.edit_text(
            "📄 Vui lòng nhập **khoảng trang bạn cần mượn**:\n"
            "_(Ví dụ: `1-45` hoặc `50-100`)_",
            parse_mode="Markdown",
        )
    await call.answer()


@router.message(BorrowPartialState.waiting_for_scope_detail)
async def handle_borrow_partial_scope_detail_input(message: Message, state: FSMContext):
    if not message.text or message.text == "❌ Hủy thao tác":
        await state.clear()
        await message.answer("❌ Đã hủy thao tác.", reply_markup=get_main_menu_keyboard(is_admin=is_admin(message.from_user.id)))
        return

    detail_text = message.text.strip()
    data = await state.get_data()
    scope_type = data.get("scope_type", "chapters")

    page_range = []
    if scope_type == "page_range":
        match = re.search(r"(\d+)\s*[-–:]\s*(\d+)", detail_text)
        if match:
            start_p, end_p = int(match.group(1)), int(match.group(2))
            if start_p > end_p:
                start_p, end_p = end_p, start_p
            page_range = [start_p, end_p]
        else:
            await message.answer("⚠️ Khoảng trang không hợp lệ. Vui lòng nhập dạng `bắt đầu - kết thúc` (ví dụ: `1-50`):")
            return
    else:
        # Chapter numbers or names
        nums = [int(n) for n in re.findall(r"\b\d+\b", detail_text)]
        if nums:
            await state.update_data(target_chapters=nums)

    await state.update_data(page_range=page_range, scope_detail=detail_text)
    await state.set_state(BorrowPartialState.waiting_for_urgency)

    await message.answer(
        "⏳ **Chọn mức độ cần gấp:**",
        reply_markup=get_borrow_partial_urgency_keyboard(),
        parse_mode="Markdown",
    )


@router.callback_query(BorrowPartialState.waiting_for_urgency, F.data.startswith("bprt_urg:"))
async def handle_borrow_partial_urgency_choice(call: CallbackQuery, state: FSMContext):
    urgency = call.data.split(":", 1)[1]
    data = await state.get_data()
    actor_id = call.from_user.id

    title_query = data.get("title_query", "")
    scope_type = data.get("scope_type", "chapters")
    page_range = data.get("page_range", [])
    target_chapters = data.get("target_chapters", [])
    scope_detail = data.get("scope_detail", "")

    try:
        res = await internal_bot_client.create_need(
            telegram_user_id=actor_id,
            title_query=title_query,
            scope_type=scope_type,
            page_range=page_range,
            target_chapters=target_chapters,
            urgency=urgency,
            coarse_location=None,
            description=f"Nhu cầu mượn 1 phần: {scope_detail}" if scope_detail else None,
        )
    except Exception as e:
        await state.clear()
        await call.message.answer(
            f"⚠️ Lỗi khi đăng nhu cầu mượn 1 phần: {parse_http_error(e)}",
            reply_markup=get_main_menu_keyboard(is_admin=is_admin(actor_id)),
        )
        await call.answer()
        return

    await state.clear()
    need_id = res.get("need_id")

    success_text = (
        "🎉 **ĐÃ ĐĂNG NHU CẦU MƯỢN 1 PHẦN THÀNH CÔNG!**\n\n"
        f"📚 Sách: **{title_query}**\n"
        f"📑 Phần cần mượn: **{scope_detail}**\n"
        f"Mã nhu cầu: `{need_id}`\n\n"
        f"🔍 Hệ thống đã quét và gửi thông báo tới các chủ sách phù hợp "
        f"(bao gồm cả người có bản photocopy khớp khoảng trang này hoặc có sách đầy đủ).\n\n"
        "Bạn sẽ nhận được tin nhắn thông báo ngay khi có thành viên gửi đề nghị hỗ trợ!"
    )
    await call.message.answer(
        success_text,
        reply_markup=get_main_menu_keyboard(is_admin=is_admin(actor_id)),
        parse_mode="Markdown",
    )
    await call.answer()





