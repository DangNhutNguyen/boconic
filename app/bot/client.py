from typing import Any, Dict, List, Optional
import httpx
from app.core.config import settings

class BoconicInternalClient:
    def __init__(self, base_url: Optional[str] = None, bot_api_key: Optional[str] = None):
        self.base_url = (base_url or settings.APP_BASE_URL).rstrip("/")
        self.bot_api_key = bot_api_key or settings.BOT_API_KEY

    def _headers(self, telegram_user_id: int) -> Dict[str, str]:
        return {
            "X-Bot-Api-Key": self.bot_api_key,
            "X-Telegram-User-Id": str(telegram_user_id),
            "Content-Type": "application/json",
        }

    async def sync_user(
        self,
        telegram_user_id: int,
        display_name: str,
        telegram_username: Optional[str] = None,
        language_code: str = "vi",
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/users/sync"
        payload = {
            "display_name": display_name,
            "telegram_username": telegram_username,
            "language_code": language_code,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=payload, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def search_books(
        self, telegram_user_id: int, query: str, limit: int = 5
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/books/search"
        params = {"q": query, "limit": limit}
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, params=params, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def get_my_books(self, telegram_user_id: int) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/api/v1/internal/telegram/my-books"
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def get_my_loans(self, telegram_user_id: int) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/api/v1/internal/telegram/my-loans"
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def get_my_lendings(self, telegram_user_id: int) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/api/v1/internal/telegram/my-lendings"
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def create_borrow_request(
        self, telegram_user_id: int, copy_id: str, duration_days: int = 14
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/borrow-requests"
        payload = {"copy_id": copy_id, "duration_days": duration_days}
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=payload, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def accept_borrow_request(
        self, telegram_user_id: int, request_id: str
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/borrow-requests/{request_id}/accept"
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def reject_borrow_request(
        self, telegram_user_id: int, request_id: str, reason: Optional[str] = None
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/borrow-requests/{request_id}/reject"
        payload = {"note": reason} if reason else {}
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=payload, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def get_requests(self, telegram_user_id: int) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/requests"
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def add_copy(
        self,
        telegram_user_id: int,
        book_id: str,
        condition: str = "good",
        maximum_loan_days: int = 14,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/copies"
        payload = {
            "book_id": book_id,
            "condition": condition,
            "maximum_loan_days": maximum_loan_days,
            "notes": notes,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=payload, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def confirm_handover(self, telegram_user_id: int, loan_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/loans/{loan_id}/confirm-handover"
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def request_return(
        self, telegram_user_id: int, loan_id: str, note: Optional[str] = None
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/loans/{loan_id}/request-return"
        payload = {"note": note}
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=payload, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def confirm_return(self, telegram_user_id: int, loan_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/loans/{loan_id}/confirm-return"
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def create_community_need(
        self,
        telegram_user_id: int,
        title_query: str,
        grade_level: Optional[int] = None,
        subject: Optional[str] = None,
        curriculum: Optional[str] = None,
        quantity: int = 1,
        fulfillment_preference: str = "lend",
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/community-needs"
        payload = {
            "title_query": title_query,
            "grade_level": grade_level,
            "subject": subject,
            "curriculum": curriculum,
            "quantity": quantity,
            "fulfillment_preference": fulfillment_preference,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=payload, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def get_libraries(self, telegram_user_id: int) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/api/v1/internal/telegram/libraries"
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def get_resources(self, telegram_user_id: int) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/api/v1/internal/telegram/resources"
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def create_report(
        self,
        telegram_user_id: int,
        category: str,
        description: str,
        target_entity_type: str = "other",
        target_entity_id: str = "general",
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/reports"
        payload = {
            "category": category,
            "description": description,
            "target_entity_type": target_entity_type,
            "target_entity_id": target_entity_id,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=payload, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def get_admin_stats(self, telegram_user_id: int) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/admin/stats"
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    # --- Personal Library Methods ---
    async def get_library(self, telegram_user_id: int, tab: str = "all") -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/library"
        params = {"tab": tab}
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, params=params, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def set_copy_visibility(self, telegram_user_id: int, copy_id: str, visibility: str) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/library/copies/{copy_id}/visibility"
        payload = {"visibility": visibility}
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=payload, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def remove_copy(self, telegram_user_id: int, copy_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/library/copies/{copy_id}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.delete(url, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    # --- Needs Methods ---
    async def create_need(
        self,
        telegram_user_id: int,
        title_query: str,
        book_id: Optional[str] = None,
        isbn: Optional[str] = None,
        edition_label: Optional[str] = None,
        scope_type: str = "full_book",
        page_range: Optional[List[int]] = None,
        target_chapters: Optional[List[str]] = None,
        quantity: int = 1,
        duration_days_needed: int = 14,
        coarse_location: Optional[str] = None,
        urgency: str = "normal",
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/needs"
        payload = {
            "title_query": title_query,
            "book_id": book_id,
            "isbn": isbn,
            "edition_label": edition_label,
            "scope_type": scope_type,
            "page_range": page_range or [],
            "target_chapters": target_chapters or [],
            "quantity": quantity,
            "duration_days_needed": duration_days_needed,
            "coarse_location": coarse_location,
            "urgency": urgency,
            "description": description,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=payload, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def get_my_needs(self, telegram_user_id: int) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/api/v1/internal/telegram/needs/my"
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def get_need_detail(self, telegram_user_id: int, need_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/needs/{need_id}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def cancel_need(self, telegram_user_id: int, need_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/needs/{need_id}/cancel"
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    # --- Offers Methods ---
    async def create_offer(
        self,
        telegram_user_id: int,
        need_id: str,
        offer_type: str,
        copy_id: Optional[str] = None,
        resource_id: Optional[str] = None,
        covered_ranges: Optional[List[List[int]]] = None,
        proposed_duration_days: int = 14,
        coarse_pickup_area: Optional[str] = None,
        message: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/offers"
        payload = {
            "need_id": need_id,
            "offer_type": offer_type,
            "copy_id": copy_id,
            "resource_id": resource_id,
            "covered_ranges": covered_ranges or [],
            "proposed_duration_days": proposed_duration_days,
            "coarse_pickup_area": coarse_pickup_area,
            "message": message,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=payload, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def select_offer(self, telegram_user_id: int, offer_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/offers/{offer_id}/select"
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def withdraw_offer(self, telegram_user_id: int, offer_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/offers/{offer_id}/withdraw"
        payload = {"reason": reason} if reason else {}
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=payload, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def decline_offer(self, telegram_user_id: int, offer_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/offers/{offer_id}/decline"
        payload = {"reason": reason} if reason else {}
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=payload, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    # --- Partial Materials Methods ---
    async def register_partial_copy(
        self,
        telegram_user_id: int,
        book_id: str,
        start_page: int,
        end_page: int,
        condition: str = "good",
        barcode: Optional[str] = None,
        pagination_basis: Optional[str] = None,
        chapters: Optional[List[str]] = None,
        source_description: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/partial/copies"
        payload = {
            "book_id": book_id,
            "start_page": start_page,
            "end_page": end_page,
            "condition": condition,
            "barcode": barcode,
            "pagination_basis": pagination_basis,
            "chapters": chapters or [],
            "source_description": source_description,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=payload, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    # --- User Warnings Methods ---
    async def get_my_warnings(self, telegram_user_id: int) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/api/v1/internal/telegram/warnings/my"
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def acknowledge_warning(self, telegram_user_id: int, warning_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/warnings/{warning_id}/acknowledge"
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def appeal_warning(self, telegram_user_id: int, warning_id: str, appeal_note: str) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/warnings/{warning_id}/appeal"
        payload = {"appeal_note": appeal_note}
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=payload, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def get_book_chapters_and_progress(self, telegram_user_id: int, book_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/books/{book_id}/chapters"
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def update_chapter_progress(
        self,
        telegram_user_id: int,
        book_id: str,
        chapter_id: str,
        reading_state: str,
        bookmark_page: Optional[int] = None,
        bookmark_note: Optional[str] = None,
        personal_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/books/{book_id}/chapters/{chapter_id}/progress"
        payload = {
            "reading_state": reading_state,
            "bookmark_page": bookmark_page,
            "bookmark_note": bookmark_note,
            "personal_notes": personal_notes,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=payload, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def create_chapter_proposal(
        self,
        telegram_user_id: int,
        book_id: str,
        action: str,
        proposed_data: Dict[str, Any],
        reason: str,
        chapter_id: Optional[str] = None,
        base_version: int = 1,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/books/{book_id}/chapter-proposals"
        payload = {
            "action": action,
            "proposed_data": proposed_data,
            "reason": reason,
            "chapter_id": chapter_id,
            "base_version": base_version,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=payload, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def get_my_resources(self, telegram_user_id: int) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/users/me/resources"
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def declare_physical_partial(
        self,
        telegram_user_id: int,
        book_id: str,
        start_page: int,
        end_page: int,
        chapters: Optional[List[Any]] = None,
        condition: str = "good",
        source_description: Optional[str] = None,
        visibility: str = "private",
        storage_location_private: Optional[str] = None,
        notes: Optional[str] = None,
        barcode: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/partial-materials/physical"
        payload = {
            "book_id": book_id,
            "start_page": start_page,
            "end_page": end_page,
            "chapters": chapters or [],
            "condition": condition,
            "source_description": source_description,
            "visibility": visibility,
            "storage_location_private": storage_location_private,
            "notes": notes,
            "barcode": barcode,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=payload, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def upload_digital_partial(
        self,
        telegram_user_id: int,
        book_id: str,
        chapter_id: Optional[str] = None,
        title: str = "Tài liệu học tập",
        resource_type: str = "digital_fragment",
        url: Optional[str] = None,
        file_bytes_base64: Optional[str] = None,
        filename: Optional[str] = None,
        page_start: Optional[int] = None,
        page_end: Optional[int] = None,
        rights_basis: str = "personal_fair_use",
        consent_given: bool = True,
        provenance: Optional[str] = None,
        is_public: bool = False,
    ) -> Dict[str, Any]:
        api_url = f"{self.base_url}/api/v1/internal/telegram/partial-materials/digital"
        payload = {
            "book_id": book_id,
            "chapter_id": chapter_id or "auto",
            "title": title,
            "resource_type": resource_type,
            "url": url,
            "file_bytes_base64": file_bytes_base64,
            "filename": filename,
            "page_start": page_start,
            "page_end": page_end,
            "rights_basis": rights_basis,
            "consent_given": consent_given,
            "provenance": provenance,
            "is_public": is_public,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(api_url, json=payload, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def get_my_partial_materials(self, telegram_user_id: int) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/partial-materials/me"
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def delete_my_physical_partial(self, telegram_user_id: int, copy_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/partial-materials/physical/{copy_id}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.delete(url, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def delete_my_digital_partial(self, telegram_user_id: int, resource_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/partial-materials/digital/{resource_id}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.delete(url, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def search_available_partial_materials(
        self, telegram_user_id: int, query: Optional[str] = None, limit: int = 10
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/partial-materials/available"
        params = {"limit": limit}
        if query:
            params["q"] = query
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, params=params, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def quick_create_book(
        self, telegram_user_id: int, title: str, subject: Optional[str] = "Tài liệu học tập"
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/books/quick-create"
        payload = {"title": title, "subject": subject}
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=payload, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()

    async def get_community_library(
        self, telegram_user_id: int, limit: int = 20, offset: int = 0
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/internal/telegram/community/library"
        params = {"limit": limit, "offset": offset}
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, params=params, headers=self._headers(telegram_user_id))
            res.raise_for_status()
            return res.json()


internal_bot_client = BoconicInternalClient()





