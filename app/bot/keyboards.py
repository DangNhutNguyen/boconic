from typing import List, Optional
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

def get_main_menu_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """Main persistent reply keyboard grid."""
    keyboard = [
        [KeyboardButton(text="🔎 Tìm sách"), KeyboardButton(text="📚 Thư viện của tôi")],
        [KeyboardButton(text="🎒 Tài nguyên đang dùng"), KeyboardButton(text="📖 Quản lý theo chương")],
        [KeyboardButton(text="📢 Yêu cầu sách"), KeyboardButton(text="📋 Nhu cầu của tôi")],
        [KeyboardButton(text="📖 Mượn tài liệu 1 phần"), KeyboardButton(text="📑 Up tài liệu 1 phần")],
        [KeyboardButton(text="➕ Đăng sách"), KeyboardButton(text="🌐 Thư viện cộng đồng")],
        [KeyboardButton(text="🤝 Đang mượn"), KeyboardButton(text="📤 Đang cho mượn")],
        [KeyboardButton(text="📋 Yêu cầu mượn"), KeyboardButton(text="🔗 Tài nguyên mở")],
        [KeyboardButton(text="👤 Hồ sơ & Cài đặt"), KeyboardButton(text="🚩 Báo cáo / Hỗ trợ")],
    ]
    if is_admin:
        keyboard.append([KeyboardButton(text="👑 Quản trị hệ thống")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Quick cancel keyboard for FSM states."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Hủy thao tác")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

def get_book_inline_keyboard(book_id: str, available_copies: list) -> InlineKeyboardMarkup:
    """Inline keyboard for a book: buttons to borrow available copies using full UUID (<= 64 bytes)."""
    buttons = []
    for c in available_copies[:3]:
        # 'brq:' (4 bytes) + uuid (36 bytes) = 40 bytes <= 64 bytes
        cid = c["copy_id"]
        code = c["public_code"]
        cond = c.get("condition", "good")
        cond_vi = {
            "new": "Mới",
            "like_new": "Rất tốt",
            "good": "Tốt",
            "fair": "Khá",
        }.get(cond, cond)
        is_p = c.get("is_partial", False)
        p_tag = " (1 phần)" if is_p else ""
        btn_text = f"Mượn bản {code}{p_tag} ({cond_vi})"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"brq:{cid}")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_request_action_keyboard(request_id: str) -> InlineKeyboardMarkup:
    """Action buttons for owner to accept or reject an incoming borrow request."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Chấp nhận cho mượn", callback_data=f"acc:{request_id}"),
            InlineKeyboardButton(text="❌ Từ chối", callback_data=f"rej:{request_id}"),
        ]
    ])

def get_loan_handover_keyboard(loan_id: str, role: str) -> InlineKeyboardMarkup:
    """Action button to confirm physical handover."""
    btn_text = "🤝 Xác nhận đã giao sách" if role == "lender" else "📦 Xác nhận đã nhận được sách"
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=btn_text, callback_data=f"hdo:{loan_id}")]])

def get_loan_return_keyboard(loan_id: str, is_pending: bool = False) -> InlineKeyboardMarkup:
    """Action buttons to request or confirm return."""
    if not is_pending:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Đề nghị xác nhận trả sách", callback_data=f"rt_req:{loan_id}")]
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Xác nhận đã hoàn trả sách", callback_data=f"rt_cfm:{loan_id}")]
    ])

def get_condition_inline_keyboard() -> InlineKeyboardMarkup:
    """Inline buttons to select copy condition when adding a book."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Mới (99-100%)", callback_data="cnd:new"),
            InlineKeyboardButton(text="Rất tốt (90-95%)", callback_data="cnd:like_new"),
        ],
        [
            InlineKeyboardButton(text="Tốt (80-90%)", callback_data="cnd:good"),
            InlineKeyboardButton(text="Khá (70-80%)", callback_data="cnd:fair"),
        ],
    ])

def get_duration_inline_keyboard() -> InlineKeyboardMarkup:
    """Inline buttons to select maximum loan days."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="7 ngày", callback_data="dur:7"),
            InlineKeyboardButton(text="14 ngày (chuẩn)", callback_data="dur:14"),
        ],
        [
            InlineKeyboardButton(text="30 ngày", callback_data="dur:30"),
            InlineKeyboardButton(text="60 ngày", callback_data="dur:60"),
        ],
    ])

def get_report_category_keyboard() -> InlineKeyboardMarkup:
    """Inline buttons to select report category."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📖 Sách sai thông tin", callback_data="rpc:wrong_info"),
            InlineKeyboardButton(text="🚫 Không đến điểm hẹn", callback_data="rpc:no_show"),
        ],
        [
            InlineKeyboardButton(text="⚠️ Sách hư hỏng nặng", callback_data="rpc:damaged"),
            InlineKeyboardButton(text="⚠️ Vi phạm bản quyền / Giả mạo", callback_data="rpc:copyright"),
        ],
        [
            InlineKeyboardButton(text="Khác / Đóng góp ý kiến", callback_data="rpc:other"),
        ],
    ])


def get_library_tabs_keyboard() -> InlineKeyboardMarkup:
    """Inline buttons to switch between Personal Library tabs."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📖 Tôi sở hữu", callback_data="lib:owned"),
            InlineKeyboardButton(text="✅ Đang sẵn sàng", callback_data="lib:available"),
        ],
        [
            InlineKeyboardButton(text="📤 Đang cho mượn", callback_data="lib:lent"),
            InlineKeyboardButton(text="🤝 Tôi đang mượn", callback_data="lib:borrowed"),
        ],
        [
            InlineKeyboardButton(text="📌 Wishlist", callback_data="lib:wishlist"),
            InlineKeyboardButton(text="📑 Tài liệu 1 phần", callback_data="lib:resources"),
        ],
        [
            InlineKeyboardButton(text="📜 Lịch sử mượn", callback_data="lib:history"),
            InlineKeyboardButton(text="📚 Tất cả", callback_data="lib:all"),
        ],
    ])


def get_need_scope_keyboard() -> InlineKeyboardMarkup:
    """Inline buttons to choose book need scope."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📖 Cả quyển sách", callback_data="scp:full_book")],
        [InlineKeyboardButton(text="📑 Chương / Chủ đề", callback_data="scp:chapters")],
        [InlineKeyboardButton(text="📄 Khoảng trang cụ thể", callback_data="scp:page_range")],
    ])


def get_need_urgency_keyboard() -> InlineKeyboardMarkup:
    """Inline buttons to choose urgency."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Bình thường", callback_data="urg:normal"),
            InlineKeyboardButton(text="Cần gấp ⚡", callback_data="urg:urgent"),
            InlineKeyboardButton(text="Rất gấp 🔥", callback_data="urg:critical"),
        ]
    ])


def get_offer_notification_keyboard(need_id: str) -> InlineKeyboardMarkup:
    """
    Buttons on notification sent to copy owners:
    - Tôi có bản đầy đủ
    - Tôi có một phần
    - Sách sẽ có lại vào ngày...
    - Giới thiệu nguồn
    - Không thể hỗ trợ
    - Tắt thông báo loại này
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📚 Tôi có bản đầy đủ", callback_data=f"off_f:{need_id}"),
            InlineKeyboardButton(text="📑 Tôi có một phần", callback_data=f"off_p:{need_id}"),
        ],
        [
            InlineKeyboardButton(text="⏳ Sắp có lại", callback_data=f"off_u:{need_id}"),
            InlineKeyboardButton(text="🔗 Giới thiệu nguồn", callback_data=f"off_r:{need_id}"),
        ],
        [
            InlineKeyboardButton(text="❌ Không thể hỗ trợ", callback_data=f"off_n:{need_id}"),
            InlineKeyboardButton(text="🔕 Tắt thông báo", callback_data=f"off_m:{need_id}"),
        ],
    ])


def get_book_chapters_keyboard(book_id: str, chapters: List[Dict[str, Any]], progress_entries: Optional[List[Dict[str, Any]]] = None) -> InlineKeyboardMarkup:
    """Keyboard for displaying book chapters with reading status icons."""
    state_map = {}
    if progress_entries:
        for p in progress_entries:
            state_map[p["chapter_id"]] = p.get("reading_state", "not_started")

    rows = []
    for ch in chapters[:15]: # Show up to 15 chapters inline
        cid = ch["id"]
        st = state_map.get(cid, "not_started")
        icon = "⚪"
        if st == "completed":
            icon = "✅"
        elif st == "in_progress":
            icon = "⏳"

        label = f"{icon} {ch.get('chapter_code', ch.get('chapter_number', ''))}. {ch.get('title', 'Chương')}"
        if len(label) > 35:
            label = label[:32] + "..."
        rows.append([InlineKeyboardButton(text=label, callback_data=f"ch_d:{book_id}:{cid}")])

    # Action row
    rows.append([
        InlineKeyboardButton(text="📢 Cần chương sách", callback_data=f"req_ch:{book_id}"),
        InlineKeyboardButton(text="📝 Đề xuất sửa", callback_data=f"prop_ch:{book_id}"),
    ])
    rows.append([
        InlineKeyboardButton(text="📥 Xuất ghi chú", callback_data=f"exp_n:{book_id}"),
        InlineKeyboardButton(text="⬅️ Thư viện", callback_data="lib:all"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_chapter_detail_keyboard(book_id: str, chapter_id: str, current_state: str) -> InlineKeyboardMarkup:
    """Action keyboard for a specific chapter."""
    state_btns = []
    if current_state != "completed":
        state_btns.append(InlineKeyboardButton(text="✅ Đã đọc xong", callback_data=f"set_st:{book_id}:{chapter_id}:completed"))
    if current_state != "in_progress":
        state_btns.append(InlineKeyboardButton(text="⏳ Đang đọc", callback_data=f"set_st:{book_id}:{chapter_id}:in_progress"))
    if current_state != "not_started":
        state_btns.append(InlineKeyboardButton(text="⚪ Chưa đọc", callback_data=f"set_st:{book_id}:{chapter_id}:not_started"))

    return InlineKeyboardMarkup(inline_keyboard=[
        state_btns,
        [
            InlineKeyboardButton(text="📢 Tôi cần chương này", callback_data=f"need_c:{book_id}:{chapter_id}"),
            InlineKeyboardButton(text="🔔 Theo dõi nguồn", callback_data=f"wtch_c:{book_id}:{chapter_id}"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Danh mục chương", callback_data=f"ch_list:{book_id}"),
        ],
    ])



def get_need_offer_actions_keyboard(offer_id: str) -> InlineKeyboardMarkup:
    """Action buttons for requester viewing a support offer."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🤝 Chọn để mượn", callback_data=f"sel_o:{offer_id}"),
            InlineKeyboardButton(text="❌ Từ chối", callback_data=f"dec_o:{offer_id}"),
        ]
    ])


def get_partial_type_keyboard() -> InlineKeyboardMarkup:
    """Choose whether to declare a physical photocopy or upload a digital fragment."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📕 Khai báo bản photocopy / giấy", callback_data="ptp:physical"),
        ],
        [
            InlineKeyboardButton(text="💾 Tải lên liên kết / tài liệu số", callback_data="ptp:digital"),
        ],
        [
            InlineKeyboardButton(text="❌ Hủy bỏ", callback_data="ptp:cancel"),
        ],
    ])


def get_partial_fair_use_keyboard() -> InlineKeyboardMarkup:
    """Fair use compliance agreement before uploading digital excerpts."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚖️ Tôi cam kết dùng cho học tập cá nhân", callback_data="pfu:accept"),
        ],
        [
            InlineKeyboardButton(text="❌ Hủy bỏ", callback_data="pfu:cancel"),
        ],
    ])


def get_partial_visibility_keyboard() -> InlineKeyboardMarkup:
    """Choose visibility for photocopy partial holding."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔒 Riêng tư (Khuyến nghị)", callback_data="pvis:private"),
        ],
        [
            InlineKeyboardButton(text="👥 Bạn bè / Nhóm học", callback_data="pvis:internal"),
        ],
        [
            InlineKeyboardButton(text="🌐 Công khai cộng đồng", callback_data="pvis:public"),
        ],
    ])


def get_partial_condition_inline_keyboard() -> InlineKeyboardMarkup:
    """Inline buttons to select condition for partial photocopy."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Mới (Bản in đẹp, rõ nét)", callback_data="pcond:new"),
            InlineKeyboardButton(text="Rất tốt (Sạch sẽ, đủ trang)", callback_data="pcond:like_new"),
        ],
        [
            InlineKeyboardButton(text="Tốt (Có thể có highlight)", callback_data="pcond:good"),
            InlineKeyboardButton(text="Khá (Hơi cũ, đọc tốt)", callback_data="pcond:fair"),
        ],
    ])


def get_partial_item_actions_keyboard(item_type: str, item_id: str) -> InlineKeyboardMarkup:
    """Action button to delete a personal partial copy or digital resource."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🗑️ Xóa khỏi tài khoản", callback_data=f"dpart:{item_type}:{item_id}"),
        ]
    ])


def get_my_partial_management_keyboard(physical_items: list, digital_items: list) -> InlineKeyboardMarkup:
    """Build interactive action buttons for items in /mypartial."""
    buttons = []
    for idx, p in enumerate(physical_items[:5], 1):
        b_title = p.get("book_title", "Sách")[:16]
        buttons.append([
            InlineKeyboardButton(text=f"🗑️ Xóa bản photo #{idx} ({b_title})", callback_data=f"dpart:physical:{p['copy_id']}")
        ])
    for idx, d in enumerate(digital_items[:5], 1):
        d_title = d.get("title", "Tài liệu")[:16]
        buttons.append([
            InlineKeyboardButton(text=f"🗑️ Xóa tài liệu #{idx} ({d_title})", callback_data=f"dpart:digital:{d['resource_id']}")
        ])
    buttons.append([
        InlineKeyboardButton(text="➕ Thêm tài liệu mới", callback_data="ptp:start_new"),
        InlineKeyboardButton(text="🔄 Làm mới danh sách", callback_data="ptp:refresh_list"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_borrow_partial_menu_keyboard() -> InlineKeyboardMarkup:
    """Menu keyboard for borrowing partial materials."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔍 Xem bản photo 1 phần có sẵn", callback_data="bprt:available"),
        ],
        [
            InlineKeyboardButton(text="📢 Đăng nhu cầu mượn 1 phần (Chương/Trang)", callback_data="bprt:create_need"),
        ],
        [
            InlineKeyboardButton(text="🔎 Tìm theo tên môn / sách", callback_data="bprt:search"),
            InlineKeyboardButton(text="💾 Trích đoạn số theo chương", callback_data="bprt:digital"),
        ],
        [
            InlineKeyboardButton(text="❌ Đóng", callback_data="bprt:cancel"),
        ],
    ])


def get_partial_borrow_scope_keyboard() -> InlineKeyboardMarkup:
    """Scope choices when requesting to borrow a partial material."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📑 Cần theo Chương (Chapters)", callback_data="bprt_scope:chapters"),
        ],
        [
            InlineKeyboardButton(text="📄 Cần theo Khoảng trang (Page range)", callback_data="bprt_scope:page_range"),
        ],
        [
            InlineKeyboardButton(text="❌ Hủy", callback_data="bprt:cancel"),
        ],
    ])


def get_partial_copy_borrow_keyboard(copy_id: str) -> InlineKeyboardMarkup:
    """Button to borrow a specific partial copy."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🤝 Gửi yêu cầu mượn bản này", callback_data=f"brq:{copy_id}"),
        ]
    ])


def get_digital_visibility_keyboard() -> InlineKeyboardMarkup:
    """Choose visibility for digital partial material / excerpt."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌐 Công khai cộng đồng (Mọi người có thể đọc)", callback_data="pdvis:public"),
        ],
        [
            InlineKeyboardButton(text="🔒 Riêng tư (Chỉ lưu trữ cá nhân)", callback_data="pdvis:private"),
        ],
        [
            InlineKeyboardButton(text="❌ Hủy bỏ", callback_data="ptp:cancel"),
        ],
    ])


def get_community_library_keyboard(available_copies: list = None) -> InlineKeyboardMarkup:
    """Build interactive action buttons for community library browser."""
    buttons = []
    if available_copies:
        for c in available_copies[:6]:
            cid = c.get("copy_id")
            title = c.get("book_title", "Sách")
            code = c.get("public_code", "")
            part_tag = " (1 phần)" if c.get("is_partial") else ""
            btn_text = f"🤝 Mượn: {title[:18]}...{part_tag}" if len(title) > 18 else f"🤝 Mượn: {title}{part_tag}"
            buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"brq:{cid}")])

    buttons.append([
        InlineKeyboardButton(text="📖 Photocopy 1 phần", callback_data="bprt:available"),
        InlineKeyboardButton(text="💾 Trích đoạn số & File", callback_data="bprt:digital"),
    ])
    buttons.append([
        InlineKeyboardButton(text="🔎 Tìm theo tên môn", callback_data="bprt:search"),
        InlineKeyboardButton(text="➕ Đăng tài liệu của bạn", callback_data="ptp:start_new"),
    ])
    buttons.append([
        InlineKeyboardButton(text="🔄 Làm mới", callback_data="comm:refresh"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_borrow_partial_urgency_keyboard() -> InlineKeyboardMarkup:
    """Inline buttons to choose urgency for partial material borrow request."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Bình thường", callback_data="bprt_urg:normal"),
            InlineKeyboardButton(text="Cần gấp ⚡", callback_data="bprt_urg:urgent"),
            InlineKeyboardButton(text="Rất gấp 🔥", callback_data="bprt_urg:critical"),
        ],
        [
            InlineKeyboardButton(text="❌ Hủy", callback_data="bprt:cancel"),
        ]
    ])







