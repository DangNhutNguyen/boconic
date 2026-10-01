import datetime
import hashlib
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Cookie, Depends, Form, Query, Request, Response, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, Response as PlainResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.security import generate_session_token, generate_csrf_token, verify_password, hash_password
from app.db.models.catalog import Author, Book, BookAuthor, BookCopy, CopyCoverageRange, Chapter, ChapterProposal, ChapterResource
from app.db.models.rbac import Role, Permission, RolePermission, AdminRoleAssignment
from app.db.models.community import (
    AuthorizedCollection,
    CommunityRequest,
    Report,
    RequestMatch,
    SupportOffer,
    UserWarning,
)
from app.db.models.custom_fields import CustomFieldDefinition
from app.db.models.identity import AdminAccount, AdminSession, User
from app.db.models.jobs import AuditLog, BackupJob, ImportJob, OutboxEvent
from app.db.models.lending import Loan
from app.db.session import get_db
from app.services.assembly_service import AssemblyService
from app.services.audit import AuditService
from app.services.backup import BackupService
from app.services.catalog import CatalogService
from app.services.chapter_service import ChapterService
from app.services.coverage_service import CoverageService
from app.services.import_export import ImportExportService
from app.services.need_service import NeedService
from app.services.user_service import UserService
from app.services.warning_service import WarningService

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(prefix="/admin", tags=["Admin Web Console"])

async def get_optional_admin(boconic_session: Optional[str], db: AsyncSession) -> Optional[AdminAccount]:
    if not boconic_session:
        return None
    res = await db.execute(select(AdminSession).where(AdminSession.session_token == boconic_session))
    session = res.scalar_one_or_none()
    if session:
        return await db.get(AdminAccount, session.admin_id)
    return None

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def admin_root(boconic_session: Optional[str] = Cookie(None), db: AsyncSession = Depends(get_db)):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)
    return RedirectResponse(url="/admin/dashboard", status_code=303)

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})

@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(AdminAccount).where(AdminAccount.username == username.strip()))
    admin = res.scalar_one_or_none()
    if not admin or not verify_password(password, admin.password_hash):
        return templates.TemplateResponse(
            request, "login.html", {"error": "Tên đăng nhập hoặc mật khẩu không chính xác."}
        )

    session_token = generate_session_token()
    csrf_token = generate_csrf_token()
    import datetime
    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7)

    session = AdminSession(
        admin_id=admin.id,
        session_token=session_token,
        csrf_token=csrf_token,
        expires_at=expires_at,
    )
    db.add(session)
    await db.commit()

    response = RedirectResponse(url="/admin/dashboard", status_code=303)
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=session_token,
        max_age=86400 * 7,
        httponly=True,
        samesite="lax",
    )
    return response

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    now = datetime.datetime.now(datetime.timezone.utc)
    u_count = (await db.execute(select(func.count(User.id)))).scalar_one()
    b_count = (await db.execute(select(func.count(Book.id)))).scalar_one()
    c_count = (await db.execute(select(func.count(BookCopy.id)))).scalar_one()
    avail_count = (await db.execute(select(func.count(BookCopy.id)).where(BookCopy.circulation_status == "available"))).scalar_one()
    active_loans = (await db.execute(select(func.count(Loan.id)).where(Loan.status == "active"))).scalar_one()
    reserved_loans = (await db.execute(select(func.count(Loan.id)).where(Loan.status == "reserved"))).scalar_one()
    overdue_loans = (await db.execute(select(func.count(Loan.id)).where(Loan.status == "active", Loan.due_at < now))).scalar_one()
    reports_count = (await db.execute(select(func.count(Report.id)).where(Report.status.in_(["open", "reviewing"])))).scalar_one()
    pending_proposals = (await db.execute(select(func.count(ChapterProposal.id)).where(ChapterProposal.status == "pending"))).scalar_one()
    pending_outbox = (await db.execute(select(func.count(OutboxEvent.id)).where(OutboxEvent.status == "pending"))).scalar_one()

    # Recent loans
    recent_loans_res = await db.execute(
        select(Loan)
        .options(
            selectinload(Loan.copy).selectinload(BookCopy.book),
            selectinload(Loan.borrower),
            selectinload(Loan.lender),
        )
        .order_by(desc(Loan.created_at))
        .limit(10)
    )
    recent_loans = recent_loans_res.scalars().all()

    metrics = {
        "users_count": u_count,
        "books_count": b_count,
        "copies_count": c_count,
        "available_copies_count": avail_count,
        "active_loans_count": active_loans,
        "reserved_loans_count": reserved_loans,
        "overdue_loans_count": overdue_loans,
        "unresolved_reports_count": reports_count,
        "pending_proposals": pending_proposals,
        "pending_outbox": pending_outbox,
    }

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "admin": admin,
            "metrics": metrics,
            "recent_loans": recent_loans,
            "active_nav": "dashboard",
        },
    )

@router.get("/books", response_class=HTMLResponse)
async def books_page(
    request: Request,
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    books_res = await db.execute(
        select(Book)
        .options(
            selectinload(Book.authors).selectinload(BookAuthor.author),
            selectinload(Book.copies),
        )
        .order_by(desc(Book.created_at))
    )
    books = books_res.scalars().all()

    custom_fields_res = await db.execute(
        select(CustomFieldDefinition)
        .where(CustomFieldDefinition.entity_type == "book", CustomFieldDefinition.active.is_(True))
    )
    custom_fields = custom_fields_res.scalars().all()

    return templates.TemplateResponse(
        request,
        "books.html",
        {
            "admin": admin,
            "books": books,
            "custom_fields": custom_fields,
            "active_nav": "books",
        },
    )

@router.post("/books", response_class=HTMLResponse)
async def admin_create_book_form(
    request: Request,
    title: str = Form(...),
    authors: str = Form(...),
    isbn: Optional[str] = Form(None),
    curriculum: Optional[str] = Form(None),
    subject: Optional[str] = Form(None),
    grade_level: Optional[int] = Form(None),
    publisher: Optional[str] = Form(None),
    publication_year: Optional[int] = Form(None),
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    author_list = [a.strip() for a in authors.split(",") if a.strip()]
    book = await CatalogService.create_book(
        db=db,
        title=title,
        authors=author_list,
        publisher=publisher,
        publication_year=publication_year,
        subject=subject,
        grade_level=grade_level,
        curriculum=curriculum,
        isbn_raw=isbn,
    )
    await AuditService.log_action(
        db,
        action="create_book",
        entity_type="book",
        entity_id=book.id,
        actor_id=admin.id,
    )
    await db.commit()
    return RedirectResponse(url=f"/admin/books/{book.id}?message=Đã+tạo+đầu+sách+thành+công", status_code=303)


@router.get("/books/{book_id}", response_class=HTMLResponse)
async def admin_book_detail(
    request: Request,
    book_id: str,
    message: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    from app.db.models.community import CommunityRequest as CR
    book_res = await db.execute(
        select(Book)
        .options(
            selectinload(Book.authors).selectinload(BookAuthor.author),
            selectinload(Book.copies).selectinload(BookCopy.owner),
            selectinload(Book.copies).selectinload(BookCopy.current_holder),
            selectinload(Book.chapters),
        )
        .where(Book.id == book_id)
    )
    book = book_res.scalar_one_or_none()
    if not book:
        return RedirectResponse(url="/admin/books?error=Không+tìm+thấy+đầu+sách", status_code=303)

    chapters = sorted(book.chapters, key=lambda c: c.order_index or 0)
    copies = list(book.copies)

    needs_res = await db.execute(
        select(CR).where(CR.book_id == book_id).order_by(desc(CR.created_at)).limit(20)
    )
    needs = list(needs_res.scalars().all())

    return templates.TemplateResponse(
        request,
        "book_detail.html",
        {
            "admin": admin,
            "book": book,
            "copies": copies,
            "chapters": chapters,
            "needs": needs,
            "message": message,
            "error": error,
            "active_nav": "books",
        },
    )


@router.get("/books/{book_id}/edit", response_class=HTMLResponse)
async def admin_book_edit_page(
    request: Request,
    book_id: str,
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    book_res = await db.execute(
        select(Book)
        .options(selectinload(Book.authors).selectinload(BookAuthor.author))
        .where(Book.id == book_id)
    )
    book = book_res.scalar_one_or_none()
    if not book:
        return RedirectResponse(url="/admin/books", status_code=303)

    authors_str = ", ".join(ba.author.name for ba in book.authors)

    return templates.TemplateResponse(
        request,
        "book_edit.html",
        {
            "admin": admin,
            "book": book,
            "authors_str": authors_str,
            "active_nav": "books",
        },
    )


@router.post("/books/{book_id}/edit", response_class=HTMLResponse)
async def admin_book_edit_submit(
    request: Request,
    book_id: str,
    title: str = Form(...),
    authors: str = Form(...),
    isbn: Optional[str] = Form(None),
    curriculum: Optional[str] = Form(None),
    subject: Optional[str] = Form(None),
    grade_level: Optional[int] = Form(None),
    publisher: Optional[str] = Form(None),
    publication_year: Optional[int] = Form(None),
    edition_label: Optional[str] = Form(None),
    language: str = Form("vi"),
    description: Optional[str] = Form(None),
    action: Optional[str] = Form(None),
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    book = await db.get(Book, book_id)
    if not book:
        return RedirectResponse(url="/admin/books", status_code=303)

    from app.services.catalog import normalize_isbn

    # Update fields
    book.title = title.strip()
    book.publisher = publisher.strip() if publisher else None
    book.publication_year = publication_year
    book.edition_label = edition_label.strip() if edition_label else None
    book.language = language
    book.subject = subject.strip() if subject else None
    book.grade_level = grade_level
    book.curriculum = curriculum.strip() if curriculum else None
    book.description = description.strip() if description else None

    if isbn:
        isbn10, isbn13 = normalize_isbn(isbn)
        if isbn13:
            # Check uniqueness (allow same book)
            existing_res = await db.execute(select(Book).where(Book.isbn13 == isbn13, Book.id != book_id))
            if existing_res.scalar_one_or_none():
                return templates.TemplateResponse(
                    request,
                    "book_edit.html",
                    {
                        "admin": admin,
                        "book": book,
                        "authors_str": authors,
                        "error": f"ISBN {isbn13} đã tồn tại trên đầu sách khác.",
                        "active_nav": "books",
                    },
                )
            book.isbn10 = isbn10
            book.isbn13 = isbn13
        else:
            book.isbn10 = None
            book.isbn13 = None
    else:
        book.isbn10 = None
        book.isbn13 = None

    # Update authors: clear and re-add
    await db.execute(select(BookAuthor).where(BookAuthor.book_id == book_id))
    existing_links_res = await db.execute(select(BookAuthor).where(BookAuthor.book_id == book_id))
    for link in existing_links_res.scalars().all():
        await db.delete(link)
    await db.flush()

    author_list = [a.strip() for a in authors.split(",") if a.strip()]
    for author_name in author_list:
        author_obj = await CatalogService.get_or_create_author(db, author_name)
        new_link = BookAuthor(book_id=book.id, author_id=author_obj.id)
        db.add(new_link)

    await AuditService.log_action(db, action="update_book", entity_type="book", entity_id=book.id, actor_id=admin.id)
    await db.commit()

    if action == "save_add_copy":
        return RedirectResponse(url=f"/admin/books/{book_id}/copies/add", status_code=303)

    return RedirectResponse(url=f"/admin/books/{book_id}?message=Đã+cập+nhật+thông+tin+đầu+sách", status_code=303)


@router.get("/books/{book_id}/copies/add", response_class=HTMLResponse)
async def admin_add_copy_page(
    request: Request,
    book_id: str,
    error: Optional[str] = Query(None),
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    from app.db.models.identity import User
    book_res = await db.execute(
        select(Book)
        .options(
            selectinload(Book.authors).selectinload(BookAuthor.author),
            selectinload(Book.copies),
        )
        .where(Book.id == book_id)
    )
    book = book_res.scalar_one_or_none()
    if not book:
        return RedirectResponse(url="/admin/books", status_code=303)

    users_res = await db.execute(select(User).where(User.status == "active").order_by(User.display_name))
    users = users_res.scalars().all()

    return templates.TemplateResponse(
        request,
        "add_copy.html",
        {
            "admin": admin,
            "book": book,
            "users": users,
            "error": error,
            "active_nav": "books",
        },
    )


@router.post("/books/{book_id}/copies/add", response_class=HTMLResponse)
async def admin_add_copy_submit(
    book_id: str,
    owner_id: str = Form(...),
    quantity: int = Form(1),
    condition: str = Form("good"),
    format_type: str = Form("physical"),
    maximum_loan_days: int = Form(14),
    lending_policy: str = Form("free_return"),
    visibility: str = Form("published"),
    is_partial: str = Form("false"),
    barcode: Optional[str] = Form(None),
    storage_location: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    action: Optional[str] = Form(None),
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    quantity = max(1, min(quantity, 20))  # Clamp 1-20
    created_codes = []
    errors = []

    for i in range(quantity):
        try:
            copy = await CatalogService.add_book_copy(
                db=db,
                book_id=book_id,
                owner_id=owner_id,
                condition=condition,
                maximum_loan_days=maximum_loan_days,
                lending_policy=lending_policy,
                storage_location_private=storage_location,
                notes=notes,
                barcode=barcode if quantity == 1 else None,
                visibility=visibility,
                format_type=format_type,
                is_partial=(is_partial == "true"),
            )
            created_codes.append(copy.public_code)
        except Exception as e:
            errors.append(f"Bản {i+1}: {str(e)}")

    if created_codes:
        await AuditService.log_action(
            db, action="add_copies", entity_type="book_copy",
            entity_id=book_id, actor_id=admin.id,
            details={"count": len(created_codes), "codes": created_codes},
        )
        await db.commit()

    if errors and not created_codes:
        return RedirectResponse(
            url=f"/admin/books/{book_id}/copies/add?error={'|'.join(errors)}",
            status_code=303,
        )

    msg = f"Đã+tạo+{len(created_codes)}+bản+sách:+{',+'.join(created_codes)}"
    if errors:
        msg += f"+|+Lỗi:+{len(errors)}+bản"

    if action == "save_add_another":
        return RedirectResponse(url=f"/admin/books/{book_id}/copies/add?message={msg}", status_code=303)

    return RedirectResponse(url=f"/admin/books/{book_id}?message={msg}", status_code=303)


@router.get("/books/{book_id}/chapters/add", response_class=HTMLResponse)
async def admin_add_chapter_page(
    request: Request,
    book_id: str,
    error: Optional[str] = Query(None),
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    book_res = await db.execute(
        select(Book).options(selectinload(Book.chapters)).where(Book.id == book_id)
    )
    book = book_res.scalar_one_or_none()
    if not book:
        return RedirectResponse(url="/admin/books", status_code=303)

    existing_chapters = sorted(book.chapters, key=lambda c: c.order_index or 0)
    next_order = max((ch.order_index or 0 for ch in existing_chapters), default=-1) + 1

    return templates.TemplateResponse(
        request,
        "add_chapter.html",
        {
            "admin": admin,
            "book": book,
            "existing_chapters": existing_chapters,
            "next_order": next_order,
            "error": error,
            "active_nav": "books",
        },
    )


@router.post("/books/{book_id}/chapters/add", response_class=HTMLResponse)
async def admin_add_chapter_submit(
    book_id: str,
    title: str = Form(...),
    chapter_code: Optional[str] = Form(None),
    chapter_number: Optional[int] = Form(None),
    order_index: int = Form(0),
    page_start: Optional[int] = Form(None),
    page_end: Optional[int] = Form(None),
    pagination_basis: str = Form("edition_page_numbers"),
    source: str = Form("manual"),
    parent_id: Optional[str] = Form(None),
    action: Optional[str] = Form(None),
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    book = await db.get(Book, book_id)
    if not book:
        return RedirectResponse(url="/admin/books", status_code=303)

    chapter = Chapter(
        book_id=book_id,
        title=title.strip(),
        chapter_code=chapter_code.strip() if chapter_code else None,
        chapter_number=chapter_number,
        order_index=order_index,
        page_start=page_start,
        page_end=page_end,
        pagination_basis=pagination_basis,
        source=source,
        parent_id=parent_id if parent_id else None,
        verification_status="unverified",
    )
    db.add(chapter)
    await AuditService.log_action(
        db, action="add_chapter", entity_type="chapter",
        entity_id=book_id, actor_id=admin.id,
        details={"title": title},
    )
    await db.commit()

    if action == "save_add_another":
        return RedirectResponse(url=f"/admin/books/{book_id}/chapters/add", status_code=303)

    return RedirectResponse(url=f"/admin/books/{book_id}?message=Đã+thêm+chương+'{title}'", status_code=303)


@router.get("/copies", response_class=HTMLResponse)
async def copies_page(
    request: Request,
    search: Optional[str] = Query(None),
    condition: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    visibility: Optional[str] = Query(None),
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    owner_user = select(User.id, User.public_alias).subquery("owner_user")
    holder_user = select(User.id, User.public_alias).subquery("holder_user")

    stmt = (
        select(
            BookCopy,
            Book,
            owner_user.c.public_alias.label("owner_alias"),
            holder_user.c.public_alias.label("holder_alias"),
        )
        .join(Book, BookCopy.book_id == Book.id)
        .outerjoin(owner_user, BookCopy.owner_id == owner_user.c.id)
        .outerjoin(holder_user, BookCopy.current_holder_id == holder_user.c.id)
    )
    if search:
        q = f"%{search.strip()}%"
        stmt = stmt.where(or_(BookCopy.public_code.ilike(q), Book.title.ilike(q)))
    if condition:
        stmt = stmt.where(BookCopy.condition == condition)
    if status:
        stmt = stmt.where(BookCopy.circulation_status == status)
    if visibility:
        stmt = stmt.where(BookCopy.visibility == visibility)

    stmt = stmt.order_by(desc(BookCopy.created_at))
    res = await db.execute(stmt)
    copies = res.all()

    return templates.TemplateResponse(
        request,
        "copies.html",
        {
            "admin": admin,
            "copies": copies,
            "search_query": search,
            "current_condition": condition,
            "current_status": status,
            "current_vis": visibility,
            "active_nav": "copies",
        },
    )


@router.get("/copies/{copy_id}", response_class=HTMLResponse)
async def admin_copy_detail(
    request: Request,
    copy_id: str,
    message: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    copy_res = await db.execute(
        select(BookCopy)
        .options(
            selectinload(BookCopy.book),
            selectinload(BookCopy.owner),
            selectinload(BookCopy.current_holder),
            selectinload(BookCopy.loans).selectinload(Loan.borrower),
        )
        .where(BookCopy.id == copy_id)
    )
    copy = copy_res.scalar_one_or_none()
    if not copy:
        return RedirectResponse(url="/admin/copies", status_code=303)

    owner_alias = copy.owner.public_alias if copy.owner else "N/A"
    holder_alias = copy.current_holder.public_alias if copy.current_holder else "N/A"
    loans = sorted(copy.loans, key=lambda l: l.created_at or datetime.datetime.min, reverse=True)

    return templates.TemplateResponse(
        request,
        "copy_detail.html",
        {
            "admin": admin,
            "copy": copy,
            "book": copy.book,
            "owner_alias": owner_alias,
            "holder_alias": holder_alias,
            "loans": loans,
            "message": message,
            "error": error,
            "active_nav": "copies",
        },
    )


@router.post("/copies/{copy_id}/update", response_class=HTMLResponse)
async def admin_update_copy(
    copy_id: str,
    condition: str = Form(...),
    visibility: str = Form(...),
    notes: Optional[str] = Form(None),
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    copy = await db.get(BookCopy, copy_id)
    if not copy:
        return RedirectResponse(url="/admin/copies", status_code=303)

    # Guard: cannot change to available if there's an active loan
    old_condition = copy.condition
    old_visibility = copy.visibility

    copy.condition = condition
    copy.visibility = visibility
    if notes:
        copy.notes = (copy.notes or "") + f"\n[Admin] {notes}"

    await AuditService.log_action(
        db, action="update_copy", entity_type="book_copy",
        entity_id=copy.id, actor_id=admin.id,
        details={"old_condition": old_condition, "new_condition": condition, "old_visibility": old_visibility, "new_visibility": visibility},
    )
    await db.commit()
    return RedirectResponse(url=f"/admin/copies/{copy_id}?message=Đã+cập+nhật+thành+công", status_code=303)


@router.get("/loans", response_class=HTMLResponse)
async def loans_page(
    request: Request,
    status: Optional[str] = Query(None),
    overdue: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    message: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    stmt = select(Loan).options(
        selectinload(Loan.copy).selectinload(BookCopy.book),
        selectinload(Loan.borrower),
        selectinload(Loan.lender),
    )
    if status:
        stmt = stmt.where(Loan.status == status)

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    if overdue == "yes":
        stmt = stmt.where(Loan.status == "active", Loan.due_at < now_utc)
    elif overdue == "no":
        stmt = stmt.where(or_(Loan.status != "active", Loan.due_at >= now_utc, Loan.due_at.is_(None)))

    if q and q.strip():
        kw = f"%{q.strip()}%"
        stmt = (
            stmt.join(BookCopy, Loan.copy_id == BookCopy.id)
            .join(Book, BookCopy.book_id == Book.id)
            .join(User, Loan.borrower_id == User.id)
            .where(
                (Book.title.ilike(kw))
                | (BookCopy.public_code.ilike(kw))
                | (User.public_alias.ilike(kw))
                | (User.display_name.ilike(kw))
            )
        )

    stmt = stmt.order_by(desc(Loan.created_at))
    res = await db.execute(stmt)
    loans = res.scalars().unique().all()

    # Safely calculate overdue status without offset-naive/offset-aware datetime conflict
    for l in loans:
        due = l.due_at
        if due and due.tzinfo is None:
            due = due.replace(tzinfo=datetime.timezone.utc)
        l.is_overdue = bool(l.status == "active" and due and due < now_utc)

    return templates.TemplateResponse(
        request,
        "loans.html",
        {
            "admin": admin,
            "loans": loans,
            "now": now_utc,
            "current_status": status,
            "overdue_filter": overdue,
            "search_q": q or "",
            "message": message,
            "error": error,
            "active_nav": "loans",
        },
    )


@router.get("/loans/{loan_id}", response_class=HTMLResponse)
async def admin_loan_detail(
    request: Request,
    loan_id: str,
    message: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    from app.db.models.lending import HandoverConfirmation, LoanEvent
    loan_res = await db.execute(
        select(Loan).options(
            selectinload(Loan.copy).selectinload(BookCopy.book),
            selectinload(Loan.borrower),
            selectinload(Loan.lender),
            selectinload(Loan.confirmations).selectinload(HandoverConfirmation.actor),
            selectinload(Loan.events),
        ).where(Loan.id == loan_id)
    )
    loan = loan_res.scalar_one_or_none()
    if not loan:
        return RedirectResponse(url="/admin/loans", status_code=303)

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    due = loan.due_at
    if due and due.tzinfo is None:
        due = due.replace(tzinfo=datetime.timezone.utc)
    is_overdue = bool(loan.status == "active" and due and due < now_utc)
    confirmations = sorted(loan.confirmations, key=lambda c: c.confirmed_at or datetime.datetime.min)
    events = sorted(loan.events, key=lambda e: e.created_at or datetime.datetime.min, reverse=True)

    return templates.TemplateResponse(
        request,
        "loan_detail.html",
        {
            "admin": admin,
            "loan": loan,
            "confirmations": confirmations,
            "events": events,
            "is_overdue": is_overdue,
            "message": message,
            "error": error,
            "active_nav": "loans",
        },
    )


@router.post("/loans/{loan_id}/force-return", response_class=HTMLResponse)
async def admin_force_return_loan_direct(
    loan_id: str,
    resolution_notes: str = Form(...),
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    try:
        await UserService.admin_force_return_loan(
            db=db, loan_id=loan_id, admin_id=admin.username, resolution_notes=resolution_notes,
        )
        await db.commit()
        return RedirectResponse(url=f"/admin/loans/{loan_id}?message=Đã+cưỡng+chế+trả+sách+thành+công", status_code=303)
    except Exception as e:
        await db.rollback()
        return RedirectResponse(url=f"/admin/loans/{loan_id}?error={str(e)}", status_code=303)


@router.post("/loans/{loan_id}/resolve", response_class=HTMLResponse)
async def admin_resolve_dispute(
    loan_id: str,
    resolution: str = Form(...),
    reason: str = Form(...),
    redirect_to: Optional[str] = Form(None),
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    from app.db.models.lending import LoanEvent
    loan = await db.get(Loan, loan_id)
    dest = redirect_to or f"/admin/loans/{loan_id}"
    sep = "&" if "?" in dest else "?"
    if not loan or loan.status != "disputed":
        return RedirectResponse(url=f"{dest}{sep}error=Giao+dịch+không+ở+trạng+thái+tranh+chấp", status_code=303)

    old_status = loan.status
    loan.status = resolution
    if resolution == "returned":
        loan.returned_at = datetime.datetime.now(datetime.timezone.utc)
        copy = await db.get(BookCopy, loan.copy_id)
        if copy:
            copy.circulation_status = "available"
            copy.current_holder_id = copy.owner_id
    elif resolution == "closed_lost":
        copy = await db.get(BookCopy, loan.copy_id)
        if copy:
            copy.circulation_status = "lost"
    elif resolution == "active":
        copy = await db.get(BookCopy, loan.copy_id)
        if copy:
            copy.circulation_status = "loaned"

    event = LoanEvent(
        loan_id=loan.id, actor_id=admin.id,
        action="admin_resolve_dispute", from_status=old_status,
        to_status=resolution, reason=reason,
    )
    db.add(event)
    await AuditService.log_action(
        db, action="resolve_dispute", entity_type="loan",
        entity_id=loan.id, actor_id=admin.id,
        details={"resolution": resolution, "reason": reason},
    )
    await db.commit()
    return RedirectResponse(url=f"{dest}{sep}message=Đã+xử+lý+tranh+chấp+thành+công", status_code=303)


@router.get("/custom-fields", response_class=HTMLResponse)
async def custom_fields_page(
    request: Request,
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    res = await db.execute(select(CustomFieldDefinition).order_by(CustomFieldDefinition.entity_type, CustomFieldDefinition.key))
    fields = res.scalars().all()

    return templates.TemplateResponse(
        request,
        "custom_fields.html",
        {"admin": admin, "fields": fields, "active_nav": "custom_fields"},
    )

@router.post("/custom-fields", response_class=HTMLResponse)
async def custom_fields_submit(
    entity_type: str = Form(...),
    key: str = Form(...),
    label: str = Form(...),
    field_type: str = Form(...),
    options_raw: Optional[str] = Form(None),
    required: bool = Form(False),
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    options = []
    if options_raw:
        for item in options_raw.split(","):
            if ":" in item:
                k, v = item.split(":", 1)
                options.append({"id": k.strip(), "label": v.strip()})

    field_def = CustomFieldDefinition(
        entity_type=entity_type,
        key=key.strip(),
        label=label.strip(),
        field_type=field_type,
        required=required,
        options=options,
    )
    db.add(field_def)
    await db.commit()

    return RedirectResponse(url="/admin/custom-fields", status_code=303)

@router.get("/import", response_class=HTMLResponse)
async def import_page(
    request: Request,
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    res = await db.execute(select(ImportJob).order_by(desc(ImportJob.created_at)).limit(10))
    history = res.scalars().all()

    return templates.TemplateResponse(
        request,
        "import_wizard.html",
        {"admin": admin, "import_history": history, "message": None, "active_nav": "import"},
    )

@router.post("/import/upload", response_class=HTMLResponse)
async def import_upload(
    request: Request,
    entity_type: str = Form(...),
    mode: str = Form("upsert"),
    csv_file: UploadFile = File(...),
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    content = await csv_file.read()
    headers, rows, delimiter = ImportExportService.parse_csv_content(content)
    file_hash = hashlib.sha256(content).hexdigest()

    # Default mapping heuristic
    mapping = {}
    for h in headers:
        hl = h.lower()
        if "tên" in hl or "title" in hl or "sách" in hl:
            mapping["title"] = h
        elif "tác giả" in hl or "author" in hl:
            mapping["authors"] = h
        elif "isbn" in hl:
            mapping["isbn"] = h
        elif "nxb" in hl or "publisher" in hl:
            mapping["publisher"] = h
        elif "lớp" in hl or "grade" in hl:
            mapping["grade_level"] = h
        elif "môn" in hl or "subject" in hl:
            mapping["subject"] = h
        elif "bộ" in hl or "chương trình" in hl or "curriculum" in hl:
            mapping["curriculum"] = h
        elif "năm" in hl or "year" in hl:
            mapping["publication_year"] = h

    job = ImportJob(
        entity_type=entity_type,
        filename=csv_file.filename or "import.csv",
        file_hash=file_hash,
        mode=mode,
        mapping=mapping,
        status="staged",
        total_rows=len(rows),
        created_by=admin.id,
    )
    db.add(job)
    await db.flush()

    # Execute directly for P0 demo
    await ImportExportService.execute_book_import(db, job.id, rows, mapping, mode=mode)
    await db.commit()

    res = await db.execute(select(ImportJob).order_by(desc(ImportJob.created_at)).limit(10))
    history = res.scalars().all()

    msg = f"Đã nhập thành công tệp '{csv_file.filename}' ({len(rows)} dòng). Tạo mới: {job.created_count}, Cập nhật: {job.updated_count}, Lỗi: {job.error_count}."
    return templates.TemplateResponse(
        request,
        "import_wizard.html",
        {"admin": admin, "import_history": history, "message": msg, "active_nav": "import"},
    )

@router.get("/export")
async def export_data(
    entity: str = Query("books"),
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    if entity == "books":
        res = await db.execute(select(Book).options(selectinload(Book.copies)))
        books = res.scalars().all()
        csv_data = await ImportExportService.export_books_csv(db, list(books))
        return PlainResponse(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=boconic_books_catalog.csv"},
        )
    return RedirectResponse(url="/admin/dashboard", status_code=303)

@router.get("/audit", response_class=HTMLResponse)
async def audit_page(
    request: Request,
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    res = await db.execute(select(AuditLog).order_by(desc(AuditLog.created_at)).limit(50))
    logs = res.scalars().all()

    return templates.TemplateResponse(
        request, "audit.html", {"admin": admin, "logs": logs, "active_nav": "audit"}
    )

@router.get("/backups", response_class=HTMLResponse)
async def backups_page(
    request: Request,
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    res = await db.execute(select(BackupJob).order_by(desc(BackupJob.created_at)))
    backups = res.scalars().all()

    return templates.TemplateResponse(
        request, "backups.html", {"admin": admin, "backups": backups, "active_nav": "backups"}
    )

@router.post("/backups", response_class=HTMLResponse)
async def create_backup_submit(
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    await BackupService.create_backup(db, created_by=admin.id)
    await db.commit()
    return RedirectResponse(url="/admin/backups", status_code=303)


# ==========================================
# REQUESTS & OFFERS ADMIN OPERATIONS
# ==========================================

@router.get("/requests", response_class=HTMLResponse)
async def admin_requests_page(
    request: Request,
    status: Optional[str] = Query(None),
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    stmt = select(CommunityRequest, User.public_alias).join(User, CommunityRequest.user_id == User.id)
    if status:
        stmt = stmt.where(CommunityRequest.status == status)
    stmt = stmt.order_by(desc(CommunityRequest.created_at))
    res = await db.execute(stmt)
    rows = res.all()

    requests_data = []
    for req, alias in rows:
        m_count = (await db.execute(select(func.count(RequestMatch.id)).where(RequestMatch.need_id == req.id))).scalar_one() or 0
        o_count = (await db.execute(select(func.count(SupportOffer.id)).where(SupportOffer.need_id == req.id))).scalar_one() or 0
        requests_data.append((req, alias, m_count, o_count))

    return templates.TemplateResponse(
        request,
        "requests.html",
        {
            "admin": admin,
            "requests": requests_data,
            "current_status": status,
            "active_nav": "requests",
        },
    )


@router.post("/requests/{need_id}/rematch", response_class=HTMLResponse)
async def admin_rematch_need(
    need_id: str,
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    await NeedService.match_need_with_owners(db, need_id)
    await db.commit()
    return RedirectResponse(url="/admin/requests", status_code=303)


@router.post("/requests/{need_id}/cancel", response_class=HTMLResponse)
async def admin_cancel_need(
    need_id: str,
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    need = await db.get(CommunityRequest, need_id)
    if need:
        need.status = "cancelled"
        await db.commit()
    return RedirectResponse(url="/admin/requests", status_code=303)


# ==========================================
# INVENTORY & PARTIAL MATERIALS ADMIN
# ==========================================

@router.get("/inventory", response_class=HTMLResponse)
async def admin_inventory_page(
    request: Request,
    visibility: Optional[str] = Query(None),
    format: Optional[str] = Query(None),
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    owner_user = select(User.id, User.public_alias).subquery("owner_user")
    holder_user = select(User.id, User.public_alias).subquery("holder_user")

    stmt = (
        select(
            BookCopy,
            Book,
            owner_user.c.public_alias.label("owner_alias"),
            holder_user.c.public_alias.label("holder_alias"),
        )
        .join(Book, BookCopy.book_id == Book.id)
        .outerjoin(owner_user, BookCopy.owner_id == owner_user.c.id)
        .outerjoin(holder_user, BookCopy.current_holder_id == holder_user.c.id)
    )
    if visibility:
        stmt = stmt.where(BookCopy.visibility == visibility)
    if format:
        stmt = stmt.where(BookCopy.format == format)

    stmt = stmt.order_by(desc(BookCopy.created_at))
    res = await db.execute(stmt)
    copies = res.all()

    return templates.TemplateResponse(
        request,
        "inventory.html",
        {
            "admin": admin,
            "copies": copies,
            "current_vis": visibility,
            "current_format": format,
            "active_nav": "inventory",
        },
    )


@router.get("/partial-materials", response_class=HTMLResponse)
async def admin_partial_materials_page(
    request: Request,
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    stmt = (
        select(CopyCoverageRange, BookCopy, Book, User.public_alias)
        .join(BookCopy, CopyCoverageRange.copy_id == BookCopy.id)
        .join(Book, BookCopy.book_id == Book.id)
        .join(User, BookCopy.owner_id == User.id)
        .order_by(desc(CopyCoverageRange.created_at))
    )
    res = await db.execute(stmt)
    partial_items = res.all()

    digital_stmt = (
        select(ChapterResource, Chapter, Book, User.public_alias)
        .join(Chapter, ChapterResource.chapter_id == Chapter.id)
        .join(Book, ChapterResource.book_id == Book.id)
        .join(User, ChapterResource.owner_id == User.id)
        .order_by(desc(ChapterResource.created_at))
    )
    digital_res = await db.execute(digital_stmt)
    digital_items = digital_res.all()

    return templates.TemplateResponse(
        request,
        "partial_materials.html",
        {
            "admin": admin,
            "partial_items": partial_items,
            "digital_items": digital_items,
            "active_nav": "partial_materials",
        },
    )


@router.post("/partial-materials/{range_id}/verify", response_class=HTMLResponse)
async def admin_verify_partial_material(
    range_id: str,
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    r_item = await db.get(CopyCoverageRange, range_id)
    if r_item:
        r_item.verification_status = "verified"
        await db.commit()
    return RedirectResponse(url="/admin/partial-materials", status_code=303)


@router.post("/partial-materials/{range_id}/reject", response_class=HTMLResponse)
async def admin_reject_partial_material(
    range_id: str,
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    r_item = await db.get(CopyCoverageRange, range_id)
    if r_item:
        r_item.verification_status = "rejected"
        await db.commit()
    return RedirectResponse(url="/admin/partial-materials", status_code=303)


@router.post("/partial-materials/digital/{resource_id}/verify", response_class=HTMLResponse)
async def admin_verify_digital_resource(
    resource_id: str,
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    resource = await db.get(ChapterResource, resource_id)
    if resource:
        resource.verification_status = "verified"
        resource.is_public = True
        await db.commit()
    return RedirectResponse(url="/admin/partial-materials", status_code=303)


@router.post("/partial-materials/digital/{resource_id}/reject", response_class=HTMLResponse)
async def admin_reject_digital_resource(
    resource_id: str,
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    resource = await db.get(ChapterResource, resource_id)
    if resource:
        resource.verification_status = "rejected"
        resource.is_public = False
        await db.commit()
    return RedirectResponse(url="/admin/partial-materials", status_code=303)


@router.get("/partial-materials/digital/{resource_id}/file")
async def admin_download_digital_resource_file(
    resource_id: str,
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    """Admin inspection download for uploaded partial material files."""
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    from fastapi.responses import FileResponse
    from app.services.partial_material_service import PartialMaterialService
    file_path, filename = await PartialMaterialService.get_digital_partial_file(
        db=db, user_id=admin.id, resource_id=resource_id, is_admin=True
    )
    return FileResponse(path=file_path, filename=filename, media_type="application/octet-stream")


# ==========================================
# AUTHORIZED COLLECTIONS ADMIN
# ==========================================

@router.get("/collections", response_class=HTMLResponse)
async def admin_collections_page(
    request: Request,
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    stmt = select(AuthorizedCollection, Book).join(Book, AuthorizedCollection.book_id == Book.id).order_by(desc(AuthorizedCollection.created_at))
    res = await db.execute(stmt)
    collections = res.all()

    return templates.TemplateResponse(
        request,
        "collections.html",
        {
            "admin": admin,
            "collections": collections,
            "active_nav": "collections",
        },
    )


@router.post("/collections/{col_id}/assemble", response_class=HTMLResponse)
async def admin_assemble_collection(
    col_id: str,
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    await AssemblyService.run_assembly_job(db, col_id, requested_by=admin.id)
    await db.commit()
    return RedirectResponse(url="/admin/collections", status_code=303)


# ==========================================
# MODERATION & WARNINGS ADMIN
# ==========================================

@router.get("/moderation", response_class=HTMLResponse)
async def admin_moderation_page(
    request: Request,
    message: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    # 1. Disputed loans
    disputed_stmt = (
        select(Loan)
        .options(
            selectinload(Loan.copy).selectinload(BookCopy.book),
            selectinload(Loan.borrower),
            selectinload(Loan.lender),
        )
        .where(Loan.status == "disputed")
        .order_by(desc(Loan.updated_at))
    )
    disputed_loans = (await db.execute(disputed_stmt)).scalars().all()

    # 2. Reports
    reports_stmt = (
        select(Report)
        .options(selectinload(Report.reporter))
        .order_by(desc(Report.created_at))
    )
    reports = (await db.execute(reports_stmt)).scalars().all()

    # 3. Warnings
    stmt = (
        select(UserWarning, User.public_alias)
        .join(User, UserWarning.subject_user_id == User.id)
        .order_by(desc(UserWarning.created_at))
    )
    warnings = (await db.execute(stmt)).all()

    return templates.TemplateResponse(
        request,
        "moderation.html",
        {
            "admin": admin,
            "disputed_loans": disputed_loans,
            "reports": reports,
            "warnings": warnings,
            "message": message,
            "error": error,
            "active_nav": "moderation",
        },
    )


@router.post("/reports/{report_id}/resolve", response_class=HTMLResponse)
async def admin_resolve_report(
    report_id: str,
    status: str = Form(...),
    resolution_note: str = Form(""),
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    report = await db.get(Report, report_id)
    if report:
        report.status = status
        report.resolution_note = resolution_note
        report.resolved_by = admin.id
        report.resolved_at = datetime.datetime.now(datetime.timezone.utc)
        await AuditService.log_action(
            db, action="resolve_report", entity_type="report",
            entity_id=report.id, actor_id=admin.id,
            details={"status": status, "note": resolution_note},
        )
        await db.commit()
    return RedirectResponse(url="/admin/moderation?message=Đã+cập+nhật+báo+cáo+thành+công", status_code=303)



@router.post("/warnings/issue", response_class=HTMLResponse)
async def admin_issue_warning(
    user_id: str = Form(...),
    category: str = Form(...),
    severity: str = Form(...),
    message: str = Form(...),
    reason: str = Form(...),
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    await WarningService.issue_warning(
        db=db,
        subject_user_id=user_id.strip(),
        category=category,
        severity=severity,
        message=message,
        reason=reason,
        issued_by=admin.id,
    )
    await db.commit()
    return RedirectResponse(url="/admin/moderation", status_code=303)


@router.post("/warnings/{warning_id}/appeal/accept", response_class=HTMLResponse)
async def admin_accept_appeal(
    warning_id: str,
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    await WarningService.review_appeal(db, warning_id, moderator_id=admin.id, decision="accepted")
    await db.commit()
    return RedirectResponse(url="/admin/moderation", status_code=303)


@router.post("/warnings/{warning_id}/appeal/reject", response_class=HTMLResponse)
async def admin_reject_appeal(
    warning_id: str,
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    await WarningService.review_appeal(db, warning_id, moderator_id=admin.id, decision="rejected")
    await db.commit()
    return RedirectResponse(url="/admin/moderation", status_code=303)


# ==========================================
# ANALYTICS & JOBS ADMIN
# ==========================================

@router.get("/analytics", response_class=HTMLResponse)
async def admin_analytics_page(
    request: Request,
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    total_needs = (await db.execute(select(func.count(CommunityRequest.id)))).scalar_one() or 0
    open_needs = (await db.execute(select(func.count(CommunityRequest.id)).where(CommunityRequest.status == "open"))).scalar_one() or 0
    fulfilled_needs = (await db.execute(select(func.count(CommunityRequest.id)).where(CommunityRequest.status == "fulfilled"))).scalar_one() or 0

    total_offers = (await db.execute(select(func.count(SupportOffer.id)))).scalar_one() or 0
    selected_offers = (await db.execute(select(func.count(SupportOffer.id)).where(SupportOffer.status.in_(["selected", "fulfilled"])))).scalar_one() or 0
    selection_rate = round((selected_offers / total_offers * 100.0), 1) if total_offers > 0 else 0.0

    matched_owners_count = (await db.execute(select(func.count(RequestMatch.id)))).scalar_one() or 0
    notified_count = (await db.execute(select(func.count(RequestMatch.id)).where(RequestMatch.notification_status == "sent"))).scalar_one() or 0

    active_loans = (await db.execute(select(func.count(Loan.id)).where(Loan.status.in_(["reserved", "active", "return_pending"])))).scalar_one() or 0
    now = datetime.datetime.now(datetime.timezone.utc)
    overdue_loans = (await db.execute(select(func.count(Loan.id)).where(Loan.status == "active", Loan.due_at < now))).scalar_one() or 0

    total_warnings = (await db.execute(select(func.count(UserWarning.id)))).scalar_one() or 0
    rights_warnings = (await db.execute(select(func.count(UserWarning.id)).where(UserWarning.category == "rights_review"))).scalar_one() or 0
    pending_appeals = (await db.execute(select(func.count(UserWarning.id)).where(UserWarning.appeal_status == "pending"))).scalar_one() or 0
    active_collections = (await db.execute(select(func.count(AuthorizedCollection.id)).where(AuthorizedCollection.status == "active"))).scalar_one() or 0

    fulfillment_rate = round((fulfilled_needs / total_needs * 100.0), 1) if total_needs > 0 else 0.0

    stats = {
        "total_needs": total_needs,
        "open_needs": open_needs,
        "fulfilled_needs": fulfilled_needs,
        "total_offers": total_offers,
        "selected_offers": selected_offers,
        "selection_rate": selection_rate,
        "matched_owners_count": matched_owners_count,
        "notified_count": notified_count,
        "active_loans": active_loans,
        "overdue_loans": overdue_loans,
        "total_warnings": total_warnings,
        "rights_warnings": rights_warnings,
        "pending_appeals": pending_appeals,
        "active_collections": active_collections,
        "fulfillment_rate": fulfillment_rate,
    }

    return templates.TemplateResponse(
        request,
        "analytics.html",
        {
            "admin": admin,
            "stats": stats,
            "active_nav": "analytics",
        },
    )


@router.get("/chapter-proposals", response_class=HTMLResponse)
async def list_chapter_proposals(
    request: Request,
    status: str = Query("all"),
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    query = select(ChapterProposal).options(
        selectinload(ChapterProposal.book),
        selectinload(ChapterProposal.chapter),
        selectinload(ChapterProposal.proposer),
    ).order_by(desc(ChapterProposal.created_at))

    if status != "all":
        query = query.where(ChapterProposal.status == status)

    res = await db.execute(query)
    proposals = list(res.scalars().all())

    return templates.TemplateResponse(
        request,
        "chapter_proposals.html",
        {
            "admin": admin,
            "proposals": proposals,
            "current_status": status,
            "active_nav": "chapter_proposals",
        },
    )


@router.post("/chapter-proposals/{proposal_id}/review")
async def review_chapter_proposal(
    proposal_id: str,
    action: str = Form(...), # approve or reject
    review_notes: Optional[str] = Form(None),
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    is_approved = (action == "approve")
    await ChapterService.review_chapter_proposal(
        db=db,
        proposal_id=proposal_id,
        reviewer_id=admin.username,
        approved=is_approved,
        review_notes=review_notes,
    )
    await db.commit()
    return RedirectResponse(url="/admin/chapter-proposals", status_code=303)


@router.get("/process-audit", response_class=HTMLResponse)
async def process_audit_dashboard(
    request: Request,
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    # Revalidation needs
    reval_res = await db.execute(
        select(CommunityRequest).options(
            selectinload(CommunityRequest.user)
        ).where(CommunityRequest.revalidation_required == True)
    )
    revalidation_needs = list(reval_res.scalars().all())

    # Pending proposals
    pending_prop_res = await db.execute(
        select(func.count(ChapterProposal.id)).where(ChapterProposal.status == "pending")
    )
    pending_proposals_count = pending_prop_res.scalar_one() or 0

    # Active and overdue loans
    now = datetime.datetime.now(datetime.timezone.utc)
    active_loans_count = (await db.execute(select(func.count(Loan.id)).where(Loan.status == "active"))).scalar_one() or 0
    overdue_loans_count = (await db.execute(select(func.count(Loan.id)).where(Loan.status == "active", Loan.due_at < now))).scalar_one() or 0

    # Outbox events
    pending_outbox_count = (await db.execute(select(func.count(OutboxEvent.id)).where(OutboxEvent.status == "pending"))).scalar_one() or 0
    recent_outbox_res = await db.execute(
        select(OutboxEvent).order_by(desc(OutboxEvent.created_at)).limit(25)
    )
    recent_outbox = list(recent_outbox_res.scalars().all())

    return templates.TemplateResponse(
        request,
        "process_audit.html",
        {
            "admin": admin,
            "revalidation_needs": revalidation_needs,
            "pending_proposals_count": pending_proposals_count,
            "active_loans_count": active_loans_count,
            "overdue_loans_count": overdue_loans_count,
            "pending_outbox_count": pending_outbox_count,
            "recent_outbox": recent_outbox,
            "active_nav": "process_audit",
        },
    )


@router.post("/process-audit/resolve-revalidation/{need_id}")
async def resolve_need_revalidation(
    need_id: str,
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    need = await db.get(CommunityRequest, need_id)
    if need:
        need.revalidation_required = False
        await db.commit()

    return RedirectResponse(url="/admin/process-audit", status_code=303)


# ==========================================
# USER MANAGEMENT & RESOURCE TRACKING ADMIN
# ==========================================

@router.get("/users", response_class=HTMLResponse)
async def admin_users_page(
    request: Request,
    search: Optional[str] = Query(None),
    status: Optional[str] = Query("all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    data = await UserService.list_users(
        db=db,
        search=search,
        status=status,
        page=page,
        page_size=page_size,
    )

    return templates.TemplateResponse(
        request,
        "users.html",
        {
            "admin": admin,
            "users_data": data["users"],
            "total_count": data["total_count"],
            "current_page": data["page"],
            "total_pages": data["total_pages"],
            "search_query": search or "",
            "status_filter": status or "all",
            "stats": data["stats"],
            "active_nav": "users",
        },
    )


@router.get("/users/{user_id}", response_class=HTMLResponse)
async def admin_user_detail_page(
    request: Request,
    user_id: str,
    message: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    details = await UserService.get_user_resource_details(db, user_id=user_id)
    books = (await db.execute(select(Book).order_by(Book.title))).scalars().all()

    return templates.TemplateResponse(
        request,
        "user_detail.html",
        {
            "admin": admin,
            "user": details["user"],
            "locations": details["locations"],
            "settings": details["settings"],
            "trust_profile": details["trust_profile"],
            "warnings": details["warnings"],
            "borrowed_loans": details["borrowed_loans"],
            "lent_loans": details["lent_loans"],
            "owned_copies": details["owned_copies"],
            "chapter_resources": details["chapter_resources"],
            "open_needs": details["open_needs"],
            "open_offers": details["open_offers"],
            "study_progress": details["study_progress"],
            "books": books,
            "message": message,
            "error": error,
            "active_nav": "users",
        },
    )


@router.post("/users/{user_id}/partial-copy", response_class=HTMLResponse)
async def admin_declare_user_partial_copy(
    user_id: str,
    book_id: str = Form(...),
    start_page: int = Form(...),
    end_page: int = Form(...),
    condition: str = Form("good"),
    source_description: Optional[str] = Form(None),
    visibility: str = Form("private"),
    notes: Optional[str] = Form(None),
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    """Desk librarian action: declare a physical photocopy or excerpt holding on behalf of user."""
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    try:
        from app.services.partial_material_service import PartialMaterialService
        await PartialMaterialService.create_physical_partial_material(
            db=db,
            user_id=user_id,
            book_id=book_id,
            start_page=start_page,
            end_page=end_page,
            condition=condition,
            source_description=source_description,
            visibility=visibility,
            notes=notes,
        )
        await db.commit()
        return RedirectResponse(
            url=f"/admin/users/{user_id}?message=Đã+khai+báo+tài+liệu+photocopy+1+phần+thành+công",
            status_code=303,
        )
    except Exception as e:
        await db.rollback()
        return RedirectResponse(
            url=f"/admin/users/{user_id}?error={str(e)}",
            status_code=303,
        )


@router.post("/users/{user_id}/status", response_class=HTMLResponse)
async def admin_update_user_status_form(
    user_id: str,
    status: str = Form(...),
    reason: str = Form(""),
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    try:
        await UserService.update_user_status(
            db=db,
            user_id=user_id,
            new_status=status,
            reason=reason,
            admin_id=admin.username,
        )
        await db.commit()
        return RedirectResponse(
            url=f"/admin/users/{user_id}?message=Đã+cập+nhật+trạng+thái+thành+công",
            status_code=303,
        )
    except Exception as e:
        await db.rollback()
        return RedirectResponse(
            url=f"/admin/users/{user_id}?error={str(e)}",
            status_code=303,
        )


@router.post("/users/{user_id}/warn", response_class=HTMLResponse)
async def admin_warn_user_form(
    user_id: str,
    category: str = Form(...),
    severity: str = Form(...),
    message: str = Form(...),
    reason: str = Form(...),
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    try:
        await WarningService.issue_warning(
            db=db,
            subject_user_id=user_id,
            category=category,
            severity=severity,
            message=message,
            reason=reason,
            issued_by=admin.username,
        )
        await db.commit()
        return RedirectResponse(
            url=f"/admin/users/{user_id}?message=Đã+gửi+cảnh+cáo+thành+công",
            status_code=303,
        )
    except Exception as e:
        await db.rollback()
        return RedirectResponse(
            url=f"/admin/users/{user_id}?error={str(e)}",
            status_code=303,
        )


@router.post("/users/{user_id}/force-return/{loan_id}", response_class=HTMLResponse)
async def admin_force_return_loan_form(
    user_id: str,
    loan_id: str,
    resolution_notes: str = Form(...),
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    try:
        await UserService.admin_force_return_loan(
            db=db,
            loan_id=loan_id,
            admin_id=admin.username,
            resolution_notes=resolution_notes,
        )
        await db.commit()
        return RedirectResponse(
            url=f"/admin/users/{user_id}?message=Đã+hoàn+tất+cưỡng+chế+giao+dịch+mượn",
            status_code=303,
        )
    except Exception as e:
        await db.rollback()
        return RedirectResponse(
            url=f"/admin/users/{user_id}?error={str(e)}",
            status_code=303,
        )


@router.get("/roles", response_class=HTMLResponse)
async def admin_roles_page(
    request: Request,
    message: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    # Check and seed default permissions & roles if empty
    perms_count = (await db.execute(select(func.count(Permission.id)))).scalar_one()
    if perms_count == 0:
        default_perms = [
            ("catalog.read", "Xem danh mục sách và chi tiết"),
            ("catalog.write", "Thêm, sửa sách và cấu trúc chương"),
            ("copies.manage", "Quản lý bản sách vật lý và trạng thái"),
            ("loans.manage", "Xem và điều phối giao dịch mượn"),
            ("loans.override", "Cưỡng chế hoàn tất hoặc giải quyết tranh chấp mượn"),
            ("chapters.review", "Phê duyệt hoặc từ chối đề xuất chương"),
            ("users.view", "Tra cứu hồ sơ và tài nguyên người dùng"),
            ("users.moderate", "Khóa tài khoản, ban hành cảnh báo người dùng"),
            ("audit.view", "Xem nhật ký audit và chuẩn đoán luồng vận hành"),
            ("backup.manage", "Tạo và khôi phục bản sao lưu dữ liệu"),
        ]
        perm_objs = {}
        for code, desc_text in default_perms:
            p = Permission(code=code, description=desc_text)
            db.add(p)
            perm_objs[code] = p
        await db.flush()

        roles_count = (await db.execute(select(func.count(Role.id)))).scalar_one()
        if roles_count == 0:
            r_super = Role(name="superadmin", description="Toàn quyền quản trị hệ thống", is_system=True)
            r_librarian = Role(name="librarian", description="Thủ thư: Quản lý sách, bản sao và cấu trúc chương", is_system=True)
            r_moderator = Role(name="moderator", description="Kiểm duyệt viên: Xử lý vi phạm, báo cáo và cảnh báo", is_system=True)
            r_operator = Role(name="operator", description="Vận hành viên: Giám sát mượn trả và luồng tiến trình", is_system=True)
            db.add_all([r_super, r_librarian, r_moderator, r_operator])
            await db.flush()

            # Attach permissions to roles
            librarian_perm_codes = ["catalog.read", "catalog.write", "copies.manage", "chapters.review"]
            for c in librarian_perm_codes:
                db.add(RolePermission(role_id=r_librarian.id, permission_id=perm_objs[c].id))

            mod_perm_codes = ["users.view", "users.moderate", "loans.override"]
            for c in mod_perm_codes:
                db.add(RolePermission(role_id=r_moderator.id, permission_id=perm_objs[c].id))

            op_perm_codes = ["loans.manage", "audit.view", "backup.manage"]
            for c in op_perm_codes:
                db.add(RolePermission(role_id=r_operator.id, permission_id=perm_objs[c].id))

            # Auto-assign superadmin role to current admin if not assigned
            db.add(AdminRoleAssignment(admin_id=admin.id, role_id=r_super.id))
            await db.commit()

    # Query admins with their roles
    admins_res = await db.execute(
        select(AdminAccount)
        .options(selectinload(AdminAccount.role_assignments).selectinload(AdminRoleAssignment.role))
        .order_by(AdminAccount.created_at.asc())
    )
    admins = admins_res.scalars().all()

    # Query roles with their permissions
    roles_res = await db.execute(
        select(Role)
        .options(selectinload(Role.permissions).selectinload(RolePermission.permission))
        .order_by(Role.is_system.desc(), Role.name.asc())
    )
    roles = roles_res.scalars().all()

    # Query all permissions
    perms_res = await db.execute(select(Permission).order_by(Permission.code.asc()))
    permissions = perms_res.scalars().all()

    # Fetch CSRF token from current session
    sess_res = await db.execute(select(AdminSession).where(AdminSession.session_token == boconic_session))
    current_sess = sess_res.scalar_one_or_none()
    csrf_token = current_sess.csrf_token if current_sess else ""

    return templates.TemplateResponse(
        request,
        "roles.html",
        {
            "current_admin": admin,
            "admins": admins,
            "roles": roles,
            "permissions": permissions,
            "active_nav": "roles",
            "csrf_token": csrf_token,
            "message": message,
            "error": error,
        },
    )


@router.post("/roles/create", response_class=HTMLResponse)
async def admin_create_role(
    request: Request,
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    form_data = await request.form()
    name = (form_data.get("name") or "").strip().lower()
    description = (form_data.get("description") or "").strip()
    selected_perms = form_data.getlist("permissions")

    if not name:
        return RedirectResponse(url="/admin/roles?error=Tên+vai+trò+không+được+để+trống", status_code=303)

    # Check duplicate
    existing = (await db.execute(select(Role).where(Role.name == name))).scalar_one_or_none()
    if existing:
        return RedirectResponse(url="/admin/roles?error=Vai+trò+này+đã+tồn+tại", status_code=303)

    new_role = Role(name=name, description=description, is_system=False)
    db.add(new_role)
    await db.flush()

    for p_id in selected_perms:
        db.add(RolePermission(role_id=new_role.id, permission_id=p_id))

    await db.commit()
    return RedirectResponse(url=f"/admin/roles?message=Đã+tạo+thành+công+vai+trò+{name}", status_code=303)


@router.post("/roles/accounts/create", response_class=HTMLResponse)
async def admin_create_account(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    email: Optional[str] = Form(None),
    role_id: Optional[str] = Form(None),
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    clean_user = username.strip()
    if len(password) < 8:
        return RedirectResponse(url="/admin/roles?error=Mật+khẩu+phải+có+ít+nhất+8+ký+tự", status_code=303)

    existing = (await db.execute(select(AdminAccount).where(AdminAccount.username == clean_user))).scalar_one_or_none()
    if existing:
        return RedirectResponse(url="/admin/roles?error=Tên+đăng+nhập+đã+tồn+tại", status_code=303)

    new_admin = AdminAccount(
        username=clean_user,
        email=email.strip() if email else None,
        password_hash=hash_password(password),
        is_active=True,
    )
    db.add(new_admin)
    await db.flush()

    if role_id:
        db.add(AdminRoleAssignment(admin_id=new_admin.id, role_id=role_id))

    await db.commit()
    return RedirectResponse(url=f"/admin/roles?message=Đã+tạo+tài+khoản+quản+trị+{clean_user}", status_code=303)


@router.post("/roles/accounts/{target_admin_id}/toggle-status", response_class=HTMLResponse)
async def admin_toggle_account_status(
    target_admin_id: str,
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_optional_admin(boconic_session, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    if admin.id == target_admin_id:
        return RedirectResponse(url="/admin/roles?error=Không+thể+tự+khóa+tài+khoản+của+chính+mình", status_code=303)

    target = await db.get(AdminAccount, target_admin_id)
    if not target:
        return RedirectResponse(url="/admin/roles?error=Không+tìm+thấy+tài+khoản", status_code=303)

    target.is_active = not target.is_active
    await db.commit()
    action = "kích hoạt" if target.is_active else "khóa"
    return RedirectResponse(url=f"/admin/roles?message=Đã+{action}+tài+khoản+{target.username}", status_code=303)


@router.get("/logout", response_class=HTMLResponse)
@router.post("/logout", response_class=HTMLResponse)
async def admin_logout(
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    if boconic_session:
        res = await db.execute(select(AdminSession).where(AdminSession.session_token == boconic_session))
        sess = res.scalar_one_or_none()
        if sess:
            await db.delete(sess)
            await db.commit()
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie(key=settings.SESSION_COOKIE_NAME)
    return response
