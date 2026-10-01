# HƯỚNG DẪN CÀI ĐẶT VÀ TRIỂN KHAI BOCONIC TRÊN UBUNTU LINUX

Tài liệu này hướng dẫn chi tiết cách clone, cấu hình và khởi chạy toàn bộ nền tảng Boconic trên hệ điều hành Ubuntu (20.04, 22.04 LTS hoặc 24.04 LTS).

---

## ⚡ PHƯƠNG PHÁP 1: 1 FILE .SH - ẤN LÀ CHẠY - KHÔNG LỖI (KHUYÊN DÙNG)

Hệ thống đã được tích hợp bộ tự động hóa thông minh trong `start.sh` (và `run_ubuntu.sh`). Bạn chỉ cần chạy đúng 1 lệnh duy nhất:

```bash
chmod +x start.sh && ./start.sh
```
*(hoặc `./run_ubuntu.sh`)*

### 🎯 Tự động hóa 100% không cần can thiệp:
1. **Tự động quét & cài đặt gói hệ thống**: Phát hiện và tự cài `python3`, `python3-venv`, `python3-pip`, `build-essential`, `curl` qua `apt`.
2. **Bảo toàn tệp `.env` & Bot Token**:
   - Nếu đã có `.env`: Giữ nguyên 100%, không bị ghi đè.
   - Nếu mới clone từ git: Tự động khôi phục từ `.env.configured` với đầy đủ `BOT_TOKEN`, `ADMIN_TELEGRAM_ID`, v.v.
3. **Môi trường ảo `.venv` tự động**: Khởi tạo virtualenv cô lập, tránh triệt để lỗi PEP 668 (`externally-managed-environment`) trên Ubuntu 24.04.
4. **Cài đặt thư viện**: Tự động cài đặt và cập nhật toàn bộ `requirements.txt`.
5. **Giải phóng cổng 8000**: Tự động dọn dẹp các tiến trình cũ nếu cổng 8000 đang bị chiếm dụng (`Address already in use`).
6. **Đồng bộ cơ sở dữ liệu (Alembic & RBAC)**: Tự tạo bảng, quyền hạn và tài khoản Super Admin (`admin` / `Boconic@2026`).
7. **Khởi chạy đồng thời 3 dịch vụ**:
   - FastAPI Backend & Web Console (Port 8000)
   - Telegram Bot Gateway (Polling kết nối BotFather)
   - Background Job Worker (Xử lý outbox task)
8. **Dọn dẹp an toàn**: Nhấn `Ctrl + C` để dừng đồng thời cả 3 dịch vụ mà không để lại tiến trình rác.

---

## 📦 HƯỚNG DẪN CLONE HOẶC CHUYỂN DỰ ÁN SANG UBUNTU

### Cách A: Clone từ Git Repository (Đã mở theo dõi `.env`)
```bash
git clone <URL_REPO_CUA_BAN> Boconic
cd Boconic
chmod +x start.sh
./start.sh
```

### Cách B: Nén và chuyển qua SCP / Rsync / USB
Nếu bạn chuyển trực tiếp từ máy hiện tại sang Ubuntu:
```bash
# Trên máy Ubuntu (sau khi giải nén vào thư mục Boconic):
cd Boconic
chmod +x start.sh
./start.sh
```

---

## 🖥️ DÀNH CHO UBUNTU DESKTOP (GIAO DIỆN ĐỒ HỌA - GUI)

Nếu bạn dùng Ubuntu Desktop và muốn **click đúp chuột để chạy**:
1. Chuột phải vào tệp `Boconic.desktop` -> chọn **Properties** -> Tab **Permissions** -> tích chọn **Allow executing file as program**.
2. Chuột phải vào `Boconic.desktop` -> chọn **Allow Launching**.
3. Từ bây giờ bạn chỉ cần **click đúp** là toàn bộ hệ thống tự động khởi chạy trong cửa sổ Terminal.

---

## 🌐 ĐỊA CHỈ TRUY CẬP VÀ QUẢN TRỊ

Sau khi kịch bản chạy thành công:
- **Giao diện Quản trị (Admin Console)**: `http://localhost:8000/admin` (hoặc `http://<IP_MAY_UBUNTU>:8000/admin`)
  - **Tài khoản**: `admin`
  - **Mật khẩu**: `Boconic@2026`
- **Tài liệu API (Swagger UI)**: `http://localhost:8000/docs`
- **Kiểm tra trạng thái (Health Check)**: `http://localhost:8000/health/live`
- **Telegram Bot**: Nhắn tin trực tiếp tới `@boconic_bot` trên Telegram để bắt đầu mượn sách.

---

## 🛠️ PHƯƠNG PHÁP 2: CHẠY THỦ CÔNG TỪNG BƯỚC (NẾU CẦN DEBUG)

Nếu bạn muốn tự quản lý từng dòng lệnh thủ công:

```bash
# 1. Cài đặt các gói hệ thống
sudo apt update && sudo apt install -y python3 python3-pip python3-venv build-essential curl

# 2. Tạo và kích hoạt môi trường ảo
python3 -m venv .venv
source .venv/bin/activate

# 3. Cài đặt thư viện Python
pip install --upgrade pip
pip install -r requirements.txt

# 4. Kiểm tra cấu hình .env
cp .env.configured .env   # nếu chưa có .env

# 5. Khởi tạo cơ sở dữ liệu
python scripts/setup.py

# 6. Chạy các dịch vụ (mở 3 terminal riêng hoặc chạy nền):
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
python -m app.bot.main &
python -m app.jobs.worker &
```

---

## 🧪 CHẠY KIỂM THỬ (TEST SUITE)

Để kiểm tra toàn diện chất lượng mã nguồn trên Ubuntu:
```bash
source .venv/bin/activate
pytest tests/ -v
```
*(Hiện tại toàn bộ 66/66 test cases đều đạt kết quả PASS tuyệt đối).*
