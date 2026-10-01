import asyncio
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select
from app.db.models.catalog import Author, Book, BookAuthor, BookCopy, Chapter
from app.db.models.community import (
    AuthorizedCollection,
    CollectionContribution,
    CommunityRequest,
    Resource,
    UserWarning,
)
from app.db.models.identity import User, UserLocation
from app.db.models.lending import BorrowRequest, Loan
from app.db.models.organization import Organization
from app.db.session import async_session_factory
from app.services.catalog import CatalogService
from app.services.lending import LendingService

async def seed_demo():
    print("==================================================")
    print("        BOCONIC DEMO DATA SEED GENERATOR          ")
    print("==================================================")

    async with async_session_factory() as db:
        # 1. Create Demo Users
        print("[1/5] Đang tạo người dùng demo (Actor A & Actor B)...")
        res_a = await db.execute(select(User).where(User.telegram_user_id == 100001))
        user_a = res_a.scalar_one_or_none()
        if not user_a:
            user_a = User(
                telegram_user_id=100001,
                display_name="Nguyễn Văn A (Demo)",
                public_alias="User #A81F",
                language_code="vi",
                status="active",
            )
            db.add(user_a)
            await db.flush()
            loc_a = UserLocation(
                user_id=user_a.id,
                city="TP. Hồ Chí Minh",
                district="Quận 10",
                neighborhood="Phường 14",
                precision_level="coarse",
            )
            db.add(loc_a)

        res_b = await db.execute(select(User).where(User.telegram_user_id == 100002))
        user_b = res_b.scalar_one_or_none()
        if not user_b:
            user_b = User(
                telegram_user_id=100002,
                display_name="Trần Thị B (Demo)",
                public_alias="User #B92C",
                language_code="vi",
                status="active",
            )
            db.add(user_b)
            await db.flush()
            loc_b = UserLocation(
                user_id=user_b.id,
                city="TP. Hồ Chí Minh",
                district="Quận 5",
                neighborhood="Phường 4",
                precision_level="coarse",
            )
            db.add(loc_b)

        await db.commit()

        # 2. Create Demo Organizations
        print("[2/5] Đang tạo các tổ chức thư viện & trường học demo...")
        res_org = await db.execute(select(Organization).where(Organization.name.like("%THPT Lê Hồng Phong%")))
        org = res_org.scalar_one_or_none()
        if not org:
            org = Organization(
                name="Thư viện Trường THPT Chuyên Lê Hồng Phong [DỮ LIỆU DEMO]",
                kind="school",
                city="TP. Hồ Chí Minh",
                district="Quận 5",
                public_address="235 Nguyễn Văn Cừ, Phường 4, Quận 5",
                verification_status="verified",
                verification_source="Sở Giáo dục & Đào tạo TP.HCM",
                inventory_policy="Ưu tiên phục vụ học sinh và giáo viên liên trường.",
            )
            db.add(org)
            await db.commit()

        # 3. Create Demo Books (Vietnam New Curriculum 2024)
        print("[3/5] Đang tạo danh mục sách giáo khoa lớp 12 chuẩn...")
        books_data = [
            {
                "title": "Toán 12 - Tập 1",
                "authors": ["Hà Huy Khoái", "Cung Thế Anh", "Trần Văn Tấn"],
                "publisher": "NXB Giáo dục Việt Nam",
                "publication_year": 2024,
                "edition_label": "Tái bản lần 1 (2024)",
                "subject": "Toán học",
                "grade_level": 12,
                "curriculum": "Kết nối tri thức",
                "isbn": "9786040388278",
                "description": "Sách giáo khoa Toán 12 theo chương trình GDPT 2018 bộ Kết nối tri thức với cuộc sống.",
                "chapters": [
                    (1, "Ứng dụng đạo hàm để khảo sát và vẽ đồ thị hàm số", 5, 42, ["dao_ham", "khao_sat_ham_so"]),
                    (2, "Toạ độ của vectơ trong không gian", 43, 76, ["vecto", "khong_gian"]),
                ],
            },
            {
                "title": "Vật lí 12",
                "authors": ["Trần Ngọc Hợi", "Nguyễn Văn Đạt"],
                "publisher": "NXB Giáo dục Việt Nam",
                "publication_year": 2024,
                "edition_label": "Xuất bản 2024",
                "subject": "Vật lý",
                "grade_level": 12,
                "curriculum": "Chân trời sáng tạo",
                "isbn": "9786040388285",
                "description": "Sách giáo khoa Vật lí 12 bộ Chân trời sáng tạo.",
                "chapters": [
                    (1, "Vật lí nhiệt", 6, 38, ["nhiet_hoc", "nhiet_do"]),
                    (2, "Khí lí tưởng", 39, 68, ["khi_li_tuong", "ap_suat"]),
                ],
            },
            {
                "title": "Hóa học 12",
                "authors": ["Lê Kim Long", "Đặng Xuân Thư"],
                "publisher": "NXB Đại học Sư phạm",
                "publication_year": 2024,
                "edition_label": "Xuất bản 2024",
                "subject": "Hóa học",
                "grade_level": 12,
                "curriculum": "Cánh Diều",
                "isbn": "9786040388292",
                "description": "Sách giáo khoa Hóa học 12 bộ Cánh Diều.",
                "chapters": [
                    (1, "Ester - Lipid. Xà phòng và chất giặt rửa", 5, 24, ["ester", "lipid"]),
                    (2, "Carbohydrate", 25, 48, ["glucose", "tinh_bot"]),
                ],
            },
        ]

        created_books = []
        for bd in books_data:
            b_check = await db.execute(select(Book).where(Book.isbn13 == bd["isbn"]))
            book = b_check.scalar_one_or_none()
            if not book:
                book = await CatalogService.create_book(
                    db=db,
                    title=bd["title"],
                    authors=bd["authors"],
                    publisher=bd["publisher"],
                    publication_year=bd["publication_year"],
                    edition_label=bd["edition_label"],
                    subject=bd["subject"],
                    grade_level=bd["grade_level"],
                    curriculum=bd["curriculum"],
                    isbn_raw=bd["isbn"],
                    description=bd["description"],
                )
                # Add chapters
                for ch_num, ch_title, p_start, p_end, ch_topics in bd["chapters"]:
                    chapter = Chapter(
                        book_id=book.id,
                        chapter_number=ch_num,
                        title=ch_title,
                        page_start=p_start,
                        page_end=p_end,
                        topics=ch_topics,
                        source="NXB",
                        verification_status="verified",
                    )
                    db.add(chapter)
                await db.commit()
            created_books.append(book)

        # 4. Create Physical Copies
        print("[4/5] Đang tạo các bản sách vật lý cho User A và User B...")
        for book in created_books:
            c_check = await db.execute(select(BookCopy).where(BookCopy.book_id == book.id))
            if not c_check.scalars().first():
                # Add copy for user A
                await CatalogService.add_book_copy(
                    db=db,
                    book_id=book.id,
                    owner_id=user_a.id,
                    condition="like_new",
                    maximum_loan_days=21,
                    lending_policy="free_return",
                    notes="Sách giữ cẩn thận, đã bọc bìa kiếng nylon.",
                )
                # Add copy for user B
                await CatalogService.add_book_copy(
                    db=db,
                    book_id=book.id,
                    owner_id=user_b.id,
                    condition="good",
                    maximum_loan_days=14,
                    lending_policy="free_return",
                    notes="Có ghi chú bút chì ở một số trang bài tập.",
                )
                await db.commit()

        # 5. Create Verified Digital Resources
        print("[5/5] Đang tạo tài nguyên số mở đã kiểm duyệt bản quyền...")
        res_check = await db.execute(select(Resource).where(Resource.title.like("%Đề tham khảo Tốt nghiệp THPT 2025%")))
        if not res_check.scalar_one_or_none():
            resource1 = Resource(
                title="Đề tham khảo Tốt nghiệp THPT 2025 - Môn Toán học [DỮ LIỆU DEMO]",
                resource_type="exam_sample",
                source_name="Bộ Giáo dục và Đào tạo",
                source_url="https://moet.gov.vn",
                license_name="Tài liệu Hành chính Công",
                rights_basis="Văn bản quy phạm và tài liệu chính thức công bố công khai của Nhà nước.",
                allowed_actions=["metadata", "link"],
                verification_status="verified",
                takedown_status="none",
            )
            db.add(resource1)

            resource2 = Resource(
                title="Sổ tay Kiến thức Trọng tâm Vật lí 12 [DỮ LIỆU DEMO]",
                resource_type="study_guide",
                source_name="Học Liệu Mở Cộng Đồng",
                source_url="https://hoclieu.vn/vat-li-12",
                license_name="Creative Commons Attribution-NonCommercial 4.0 (CC BY-NC 4.0)",
                license_url="https://creativecommons.org/licenses/by-nc/4.0/",
                rights_basis="Tác giả cấp phép tự do phi thương mại cho cộng đồng học sinh.",
                allowed_actions=["metadata", "link"],
                verification_status="verified",
                takedown_status="none",
            )
            db.add(resource2)
            await db.commit()

        # 6. Create Demo Community Need & Support Offer
        print("[6/8] Đang tạo nhu cầu tìm sách (Need) và đề nghị hỗ trợ (Offer)...")
        from app.services.need_service import NeedService
        book_math = created_books[0] if created_books else None
        if book_math:
            need_check = await db.execute(select(CommunityRequest).where(CommunityRequest.user_id == user_a.id))
            if not need_check.scalar_one_or_none():
                need = await NeedService.create_need(
                    db=db,
                    user_id=user_a.id,
                    title_query=book_math.title,
                    book_id=book_math.id,
                    isbn=book_math.isbn13,
                    edition_label=book_math.edition_label,
                    scope_type="full_book",
                    quantity=1,
                    duration_days_needed=14,
                    coarse_location="Quận 10, TP.HCM",
                    urgency="urgent",
                    urgency_reason="Cần ôn tập kiểm tra giữa kỳ",
                    status="open",
                )
                await db.commit()

                # Find User B's copy of math book
                b_copies = await db.execute(
                    select(BookCopy).where(BookCopy.book_id == book_math.id, BookCopy.owner_id == user_b.id)
                )
                copy_b = b_copies.scalars().first()
                if copy_b:
                    await NeedService.create_offer(
                        db=db,
                        need_id=need.id,
                        provider_user_id=user_b.id,
                        offer_type="full_physical_copy",
                        copy_id=copy_b.id,
                        proposed_duration_days=14,
                        coarse_pickup_area="Khu vực ĐH Bách Khoa / Quận 10",
                        message="Mình có sách đầy đủ, bạn có thể ghé lấy bất cứ lúc nào!",
                    )
                    await db.commit()

        # 7. Create Demo Partial Photocopy Holding & Coverage
        print("[7/8] Đang tạo tài liệu photocopy một phần & khoảng trang...")
        from app.db.models.catalog import CopyCoverageRange
        if book_math:
            partial_check = await db.execute(select(CopyCoverageRange))
            if not partial_check.scalar_one_or_none():
                part_copy = await CatalogService.add_book_copy(
                    db=db,
                    book_id=book_math.id,
                    owner_id=user_b.id,
                    condition="good",
                    barcode="PHOTO_TOAN12_CH1",
                    visibility="private",
                    format_type="partial_photocopy",
                    is_partial=True,
                    coverage_summary={"ranges": [[1, 30]], "chapters": ["Chương 1: Ứng dụng đạo hàm"]},
                )
                cov_range = CopyCoverageRange(
                    copy_id=part_copy.id,
                    start_page=1,
                    end_page=30,
                    pagination_basis="edition_2024",
                    chapters=["Chương 1: Ứng dụng đạo hàm"],
                    source_description="Bản photocopy bài tập cá nhân tự in",
                    verification_status="verified",
                )
                db.add(cov_range)
                await db.commit()

        # 8. Create Demo Authorized Collection & Warning
        print("[8/8] Đang tạo Authorized Collection & Cảnh báo người dùng mẫu...")
        from app.services.assembly_service import AssemblyService
        from app.services.warning_service import WarningService
        if book_math:
            col_check = await db.execute(select(AuthorizedCollection))
            if not col_check.scalar_one_or_none():
                col = await AssemblyService.create_collection(
                    db=db,
                    book_id=book_math.id,
                    title="Tuyển tập Chuyên đề Ôn thi THPT Môn Toán [Open CC-BY-NC]",
                    target_scope={"start_page": 1, "end_page": 50},
                    rights_basis="Creative Commons CC-BY-NC 4.0 - Được tác giả đồng ý chia sẻ học liệu",
                    allowed_actions=["receive", "aggregate", "distribute_file"],
                    recipient_scope="community",
                    created_by=user_a.id,
                )
                await AssemblyService.verify_collection(db, col.id, verifier_id=user_a.id, status="active")

                await AssemblyService.submit_contribution(
                    db,
                    collection_id=col.id,
                    contributor_id=user_b.id,
                    start_page=1,
                    end_page=25,
                    source_type="digital_pdf",
                    checksum_sha256="7a8f9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a",
                    consent_given=True,
                )
                await db.commit()

            warn_check = await db.execute(select(UserWarning))
            if not warn_check.scalar_one_or_none():
                await WarningService.issue_warning(
                    db=db,
                    subject_user_id=user_b.id,
                    category="rights_review",
                    severity="info",
                    message="Bạn đã khai báo một phần tài liệu. Hãy lưu ý giữ ở chế độ Riêng tư nếu chưa có bản quyền phát hành công khai.",
                    reason="Chính sách bản quyền Mục 2 Boconic",
                    issued_by="admin_system",
                )
                await db.commit()

            # 5. Seed Demo Chapters & Study Progress
            print("[5/5] Đang tạo danh mục chương, đề xuất và tiến độ học cá nhân...")
            from app.services.chapter_service import ChapterService
            ch_check = await db.execute(select(Chapter).where(Chapter.book_id == book_math.id))
            ch_list = ch_check.scalars().all()
            if not ch_list:
                ch1 = Chapter(
                    book_id=book_math.id,
                    chapter_number=1,
                    chapter_code="1",
                    order_index=1,
                    title="Ứng dụng đạo hàm để khảo sát hàm số",
                    page_start=1,
                    page_end=45,
                    pagination_basis="edition_page_numbers",
                    topics=["Đạo hàm", "Khảo sát hàm số"],
                    verification_status="verified",
                    version=1,
                )
                ch2 = Chapter(
                    book_id=book_math.id,
                    chapter_number=2,
                    chapter_code="2",
                    order_index=2,
                    title="Hàm số lũy thừa, mũ và logarit",
                    page_start=46,
                    page_end=90,
                    pagination_basis="edition_page_numbers",
                    topics=["Lũy thừa", "Mũ", "Logarit"],
                    verification_status="verified",
                    version=1,
                )
                ch3 = Chapter(
                    book_id=book_math.id,
                    chapter_number=3,
                    chapter_code="3",
                    order_index=3,
                    title="Nguyên hàm, tích phân và ứng dụng",
                    page_start=91,
                    page_end=140,
                    pagination_basis="edition_page_numbers",
                    topics=["Nguyên hàm", "Tích phân"],
                    verification_status="verified",
                    version=1,
                )
                db.add_all([ch1, ch2, ch3])
                await db.flush()

                # User A personal study progress
                await ChapterService.update_chapter_progress(
                    db=db,
                    user_id=user_a.id,
                    book_id=book_math.id,
                    chapter_id=ch1.id,
                    reading_state="completed",
                )
                await ChapterService.update_chapter_progress(
                    db=db,
                    user_id=user_a.id,
                    book_id=book_math.id,
                    chapter_id=ch2.id,
                    reading_state="in_progress",
                    bookmark_page=65,
                    bookmark_note="Công thức đổi cơ số logarit",
                    personal_notes="Cần giải thêm 10 bài tập đồ thị mũ và logarit phần nâng cao.",
                )

                # User B creates a chapter proposal
                await ChapterService.create_chapter_proposal(
                    db=db,
                    user_id=user_b.id,
                    book_id=book_math.id,
                    action="create",
                    proposed_data={
                        "title": "Phụ lục: Hướng dẫn giải đề thi mẫu",
                        "chapter_number": 4,
                        "chapter_code": "Phụ lục",
                        "order_index": 4,
                        "page_start": 141,
                        "page_end": 170,
                        "topics": ["Đề thi", "Ôn tập"],
                    },
                    reason="Bản in có kèm phần bài tập mở rộng ở cuối sách",
                )
                await db.commit()

    print("\n==================================================")
    print("     DỮ LIỆU MẪU ĐÃ ĐƯỢC KHỞI TẠO THÀNH CÔNG!     ")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(seed_demo())
