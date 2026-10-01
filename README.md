# Boconic — Nền tảng Lưu thông & Chia sẻ Sách Học tập Cộng đồng

> **Tagline:** *Find what you need. Find who can help.*  
> **Phiên bản:** 2.0.0 · **Môi trường:** Python 3.12+ · **Ngôn ngữ sản phẩm:** Tiếng Việt  
> **Kiểm thử tự động:** 66/66 Tests Passed (100% Invariants Verified)

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI_0.110+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![SQLAlchemy](https://img.shields.io/badge/ORM-SQLAlchemy_2.0_Async-d71f00?style=flat-square&logo=sqlalchemy&logoColor=white)](https://www.sqlalchemy.org)
[![aiogram](https://img.shields.io/badge/Telegram_Bot-aiogram_3.x-2CA5E0?style=flat-square&logo=telegram&logoColor=white)](https://docs.aiogram.dev)
[![Pydantic](https://img.shields.io/badge/Data_Validation-Pydantic_v2-E92063?style=flat-square&logo=pydantic&logoColor=white)](https://docs.pydantic.dev)
[![Tests](https://img.shields.io/badge/Tests-66%20Passed-brightgreen?style=flat-square&logo=pytest&logoColor=white)](tests/)

---

## 📖 1. Giới thiệu Tổng quan

**Boconic** là nền tảng số hỗ trợ cộng đồng (học sinh, sinh viên, phụ huynh, thư viện trường học và người yêu sách) tiếp cận tài liệu giáo khoa và học tập thông qua:
1. **Tìm kiếm chính xác theo phiên bản**: Nhận diện ấn bản (Edition), nhà xuất bản, chương trình học (Kết nối tri thức, Chân trời sáng tạo, Cánh Diều).
2. **Khớp nối nhu cầu cộng đồng (Book Requests)**: Tạo nhu cầu tìm sách nguyên cuốn hoặc từng chương mục tiêu; hệ thống tự động tìm và gửi thông báo tới các chủ sách đủ điều kiện.
3. **Máy trạng thái Mượn - Trả 2 bên (Dual-Party Lending Handshake)**: Xác nhận giao nhận (`reserved` ➔ `active`) và xác nhận hoàn trả (`return_pending` ➔ `returned`) an toàn, chống giữ chỗ ảo (72h timeout), bảo vệ điểm tin cậy (Trust Score).
4. **Quản lý học tập cá nhân & Phân đoạn chương**: Theo dõi tiến độ học tập (`not_started`, `in_progress`, `completed`), quản lý tài liệu photocopy một phần theo hợp khoảng toán học (Interval Union), đề xuất sửa đổi mục lục có kiểm soát phiên bản (Conflict 409 detection).
5. **Cổng giao tiếp di động (Telegram Bot Gateway)**: Tương tác trực quan 100% qua bot Telegram với FSM wizard, keyboard điều hướng và thông báo tức thời.
6. **Bảng điều khiển Quản trị (Web Admin Console)**: Vận hành toàn diện tại `/admin` với phân quyền RBAC đa cấp, quản lý kho sách, kiểm duyệt tranh chấp, báo cáo người dùng và chẩn đoán luồng hệ thống.

---

## 🏗️ 2. Kiến trúc Hệ thống & Ngăn xếp Công nghệ

```mermaid
flowchart TD
  subgraph Clients["Tương Tác Đầu Cuối"]
    T["Telegram User (Mobile / Desktop)"]
    A["Quản Trị Viên (Web Admin Console)"]
  end

  subgraph Gateway["Tầng Giao Tiếp & Điều Hướng"]
    B["Telegram Bot Gateway (aiogram 3.x)"]
    API["FastAPI Application Services (Port 8000)"]
  end

  subgraph Core["Tầng Nghiệp Vụ & Dữ Liệu"]
    S["Identity & RBAC Engine"]
    C["Catalog & Chapter Management"]
    L["Lending & Return State Machine"]
    N["Need & Owner Matching Engine"]
    DB[("Database: SQLite (Dev) / PostgreSQL (Prod)")]
  end

  subgraph AsyncWorkers["Tầng Xử Lý Nền"]
    W["Background Outbox Job Worker"]
    Q["Outbox Event Queue"]
  end

  T <-->|Long Polling| B
  A <-->|HTTP / Session Cookie| API
  B <-->|Internal API + BOT_API_KEY| API
  API --> S & C & L & N
  S & C & L & N --> DB
  API -->|Push Event| Q
  Q --> W
  W -->|Deliver Notifications| B
```

### Công nghệ sử dụng:
- **Backend API:** FastAPI, Pydantic v2, Uvicorn ASGI.
- **ORM & Database:** SQLAlchemy 2.0 (hỗ trợ đầy đủ `asyncio` & `greenlet`), song hành SQLite (mặc định cho offline/dev) và PostgreSQL 16 (production).
- **Schema Migrations:** Alembic quản lý phiên bản database tự động.
- **Telegram Bot Gateway:** aiogram 3.x với MemoryStorage FSM, custom inline keyboards và Reply Markup.
- **Admin Console:** Server-side rendered Jinja2 templates, HTMX, Vanilla CSS hiện đại, bảo mật HttpOnly cookie và Session Server-side.
- **Background Worker:** Outbox Pattern bảo đảm sự kiện không thất thoát ngay cả khi restart.

---

## 🚀 3. Hướng dẫn Khởi chạy Nhanh

### Cách 1: Trên Ubuntu / Linux — "1 file .sh - ấn là chạy - không lỗi" (Khuyên dùng)

Kịch bản `start.sh` đã được tự động hóa 100%:
- Tự kiểm tra và cài đặt gói hệ thống (`python3-venv`, `build-essential`, `curl`).
- Tự tạo môi trường ảo `.venv/` (khắc phục hoàn toàn lỗi PEP 668 trên Ubuntu 24.04).
- Tự cài đặt và đồng bộ thư viện (bao gồm `greenlet`, `sqlalchemy[asyncio]`).
- Tự giải phóng cổng 8000 nếu bị chiếm dụng.
- Tự khởi tạo database, chạy Alembic migration và tạo tài khoản Admin mặc định.
- Khởi chạy đồng thời FastAPI Backend, Telegram Bot và Background Worker.

```bash
# Mở terminal tại thư mục dự án và chạy:
chmod +x start.sh && ./start.sh
```
*(Hoặc dùng lệnh `./run_ubuntu.sh` - cả hai tệp đều có cơ chế tương tự).*

---

### Cách 2: Trên Windows

Chạy tệp batch đã tối ưu hóa sẵn:
```cmd
start.cmd
```

---

### Cách 3: Chạy bằng Docker Compose

```bash
docker compose up --build
```

---

### Cách 4: Chạy thủ công từng bước (Dành cho Lập trình viên)

```bash
# 1. Tạo môi trường ảo
python3 -m venv .venv

# 2. Kích hoạt môi trường ảo
# Trên Linux/macOS:
source .venv/bin/activate
# Trên Windows:
# .venv\Scripts\activate

# 3. Cài đặt dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 4. Tạo tệp cấu hình .env từ mẫu
cp .env.example .env

# 5. Khởi tạo cơ sở dữ liệu & tài khoản Admin mặc định
python scripts/setup.py

# 6. Khởi chạy API Web & Admin Console
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## ⚙️ 4. Cấu hình Môi trường (.env)

Tạo tệp `.env` từ `.env.example` và cấu hình các biến phù hợp:

```dotenv
APP_ENV=development
APP_TIMEZONE=Asia/Ho_Chi_Minh
APP_BASE_URL=http://localhost:8000

# Cơ sở dữ liệu: Mặc định SQLite cục bộ (chạy ngay không cần cài đặt)
DATABASE_URL=sqlite+aiosqlite:///./data/boconic.db
# Hoặc nếu dùng PostgreSQL:
# DATABASE_URL=postgresql+asyncpg://boconic:password@localhost:5432/boconic

# Cấu hình Telegram Bot (Lấy từ @BotFather)
BOT_TOKEN=your_telegram_bot_token_here
BOT_USERNAME=your_bot_username

# Cấu hình Quản trị viên
ADMIN_USERNAME=your_admin_username
ADMIN_TELEGRAM_ID=your_numeric_telegram_id
ADMIN_LOGIN=admin

# Bảo mật (Tối thiểu 32 ký tự ngẫu nhiên)
SECRET_KEY=boconic_super_secure_secret_key_change_me_in_production_min_32_chars
BOT_API_KEY=boconic_internal_bot_api_key_32_chars_min

STORAGE_DIR=./data/storage
BACKUP_DIR=./data/backups
UPLOAD_MAX_MB=10
```

---

## 🌐 5. Địa chỉ Truy cập & Quản trị

Sau khi hệ thống khởi động thành công:

- **Admin Web Console:** `http://127.0.0.1:8000/admin`
  - **Tài khoản mặc định:** `admin`
  - **Mật khẩu mặc định:** `Boconic@2026`
- **Tài liệu API (Swagger UI):** `http://127.0.0.1:8000/docs`
- **Kiểm tra trạng thái (Health Check):** `http://127.0.0.1:8000/health/live`
- **Telegram Bot:** Tương tác trực tiếp trên Telegram theo username bot bạn đã đăng ký.

---

## 🧪 6. Kiểm thử Tự động & Đảm bảo Chất lượng

Hệ thống được bảo vệ bởi bộ kiểm thử tự động toàn diện kiểm chứng 16 kịch bản bất biến (Integrity Invariants):

```bash
# Chạy toàn bộ 66 unit & integration tests
pytest tests/ -v

# Chạy kịch bản Smoke Test E2E
python scripts/smoke_test.py
```

### Các kịch bản trọng yếu được kiểm chứng:
1. **Lending State Machine:** Xác nhận giao nhận 2 bên, xác nhận hoàn trả 2 bên, ngăn chặn tự mượn sách chính mình, chống tranh chấp giữ chỗ (atomic reservation mutex).
2. **Chapter & Need Matching:** Nhu cầu nguyên cuốn được đáp ứng bằng bản sách đầy đủ; nhu cầu theo chương được đáp ứng bởi bản photo có độ phủ giao nhau (`intersection`).
3. **Data Isolation:** Tiến độ đọc cá nhân, ghi chú riêng tư và bản photo cá nhân được cách ly tuyệt đối, không hiển thị công khai.
4. **Anti-Injection:** Chống SQL Injection, Formula Injection trong xuất CSV, xác thực quyền nghiêm ngặt với `BOT_API_KEY`.

---

## 📁 7. Cấu trúc Thư mục Dự án

```
Boconic/
├── app/                        # Mã nguồn ứng dụng chính
│   ├── admin/                  # Web Admin Console (Routes, Templates Jinja2)
│   ├── api/v1/                 # REST API endpoints (Catalog, Loans, Needs, Me)
│   ├── bot/                    # Telegram Bot Gateway (Handlers, Keyboards, Client)
│   ├── core/                   # Cấu hình, bảo mật, RBAC permissions, logging
│   ├── db/                     # Models SQLAlchemy & Database session
│   ├── jobs/                   # Background Outbox Worker & Task schedulers
│   └── services/               # Nghiệp vụ (Catalog, Lending, Need, Chapter, Identity)
├── assets/                     # Thư mục lưu trữ hình ảnh minh chứng, diagrams, screenshots
├── data/                       # Dữ liệu runtime (boconic.db, storage, backups)
├── docs/                       # Tài liệu thiết kế kỹ thuật, ERD, Sổ tay vận hành
├── migrations/                 # Alembic Database Migrations
├── scripts/                    # Scripts hỗ trợ (setup.py, seed_demo.py, backup.py, smoke_test.py)
├── tests/                      # Bộ 66 automated tests kiểm thử toàn diện
├── .env.example                # Mẫu cấu hình môi trường chuẩn
├── .gitattributes              # Chuẩn hóa kết thúc dòng Unix LF cho Linux
├── .gitignore                  # Loại trừ secrets, database và runtime cache
├── Boconic.desktop             # Phím tắt click-to-run trên Ubuntu Desktop GUI
├── compose.yaml                # Cấu hình triển khai Docker Compose
├── pyproject.toml              # Metadata dự án và cấu hình build/test
├── README.md                   # Hướng dẫn chi tiết dự án
├── requirements.txt            # Danh sách thư viện Python
├── run_ubuntu.sh               # Trình kích hoạt phụ trợ trên Ubuntu
├── start.cmd                   # Kịch bản khởi chạy 1-click trên Windows
├── start.sh                    # Kịch bản khởi chạy 1-click tự động hóa trên Ubuntu
└── UBUNTU_SETUP_GUIDE.md       # Cẩm nang cài đặt chi tiết trên Ubuntu
```

---

## 📂 8. Thư mục Tài nguyên Minh chứng (`assets/`)

Thư mục [`assets/`](assets/) được thiết kế sẵn để lưu trữ:
- Ảnh chụp màn hình giao diện Web Admin và tương tác Telegram Bot.
- Sơ đồ kiến trúc, lưu đồ nghiệp vụ (Flowcharts) và lược đồ cơ sở dữ liệu (ERD).
- Các biên bản kiểm thử, tài liệu minh chứng kỹ thuật và nghiệm thu.

---

## 📄 9. Bản quyền & Giấy phép

Phát triển bởi đội ngũ kỹ thuật **Boconic Platform**. Được phát hành theo giấy phép nội bộ phục vụ mục đích học tập và chia sẻ cộng đồng giáo dục.
