#!/usr/bin/env bash
# ==============================================================================
#                      BOCONIC PLATFORM - ALL-IN-ONE RUNNER
#                      Tự động hóa 100% trên Ubuntu / Debian / Linux
#                      "1 file .sh - ấn là chạy - không lỗi"
# ==============================================================================

# Đảm bảo đường dẫn thực thi luôn là thư mục gốc của dự án
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 1. Hỗ trợ chế độ Docker nếu được yêu cầu
if [ "$1" = "docker" ] || [ "$1" = "--docker" ] || [ "$1" = "-d" ]; then
    echo "🐳 Đang khởi chạy hệ thống bằng Docker Compose..."
    docker compose up --build
    exit 0
fi

echo "=============================================================================="
echo "          🚀 KHỞI ĐỘNG HỆ THỐNG BOCONIC TỰ ĐỘNG TRÊN UBUNTU"
echo "=============================================================================="

# 2. Tự động kiểm tra và cài đặt các gói hệ thống nếu thiếu (apt-get)
# Trên Ubuntu 24.04/22.04: cần python3, python3-venv, python3-pip, curl, build-essential
check_system_packages() {
    local missing_pkgs=""
    if ! command -v python3 &>/dev/null; then
        missing_pkgs="$missing_pkgs python3"
    fi
    if ! python3 -c "import venv" &>/dev/null; then
        missing_pkgs="$missing_pkgs python3-venv"
    fi
    if ! command -v curl &>/dev/null; then
        missing_pkgs="$missing_pkgs curl"
    fi

    if [ -n "$missing_pkgs" ]; then
        echo "📦 Phát hiện thiếu các gói hệ thống cần thiết:$missing_pkgs"
        echo "⏳ Đang tự động cài đặt qua APT..."
        if [ "$(id -u)" -eq 0 ]; then
            apt-get update -qq && apt-get install -y -qq python3 python3-venv python3-pip curl build-essential
        elif command -v sudo &>/dev/null; then
            echo "🔑 Yêu cầu quyền sudo để tự động cài đặt gói hệ thống..."
            sudo apt-get update -qq && sudo apt-get install -y -qq python3 python3-venv python3-pip curl build-essential
        else
            echo "⚠️  Không có quyền root/sudo để cài đặt:$missing_pkgs"
            echo "👉 Vui lòng chạy lệnh: sudo apt update && sudo apt install -y python3 python3-venv python3-pip curl build-essential"
            exit 1
        fi
        echo "✅ Đã cài đặt xong gói hệ thống."
    fi
}

check_system_packages

# 3. Quản lý tệp cấu hình .env (BẢO TOÀN 100% TOKEN & CẤU HÌNH)
echo "🔍 [1/6] Kiểm tra tệp cấu hình .env & Bot Token..."
if [ -f ".env" ]; then
    echo "   ✅ Đã tìm thấy tệp .env (Token và cấu hình được bảo toàn tuyệt đối)."
elif [ -f ".env.configured" ]; then
    echo "   📋 Đang khôi phục .env từ tệp mẫu .env.configured..."
    cp .env.configured .env
    echo "   ✅ Đã khôi phục .env thành công với Bot Token."
elif [ -f ".env.example" ]; then
    echo "   ⚠️  Tạo .env từ .env.example..."
    cp .env.example .env
fi

# Hiển thị kiểm tra nhanh token để người dùng yên tâm
if [ -f ".env" ]; then
    TOKEN_MASKED=$(grep -E '^BOT_TOKEN=' .env | cut -d '=' -f2- | sed -E 's/(.{8}).*(.{4})/\1****\2/')
    ADMIN_ID=$(grep -E '^ADMIN_TELEGRAM_ID=' .env | cut -d '=' -f2-)
    echo "   🤖 Telegram Bot Token : ${TOKEN_MASKED:-'Chưa thiết lập'}"
    echo "   👑 Admin Telegram ID  : ${ADMIN_ID:-'Chưa thiết lập'}"
fi

# 4. Tạo các thư mục lưu trữ dữ liệu
echo "📁 [2/6] Chuẩn bị thư mục dữ liệu & logs..."
mkdir -p data/storage data/backups logs
chmod -R 755 data logs 2>/dev/null || true

# 5. Khởi tạo môi trường ảo Python (.venv) để tránh lỗi PEP 668 trên Ubuntu 24.04/Debian
echo "🐍 [3/6] Kiểm tra môi trường ảo Python (.venv)..."
if [ ! -d ".venv" ] || [ ! -f ".venv/bin/python" ]; then
    echo "   ⚙️  Đang tạo môi trường ảo mới .venv..."
    python3 -m venv .venv || {
        echo "❌ LỖI: Không thể tạo virtualenv. Hãy thử: sudo apt install -y python3-venv"
        exit 1
    }
    echo "   ✅ Đã khởi tạo môi trường .venv."
fi

PYTHON_BIN=".venv/bin/python"
PIP_BIN=".venv/bin/pip"

# 6. Kiểm tra và cài đặt dependencies từ requirements.txt
echo "📦 [4/6] Kiểm tra và đồng bộ thư viện Python..."
if ! $PYTHON_BIN -c "import fastapi, uvicorn, sqlalchemy, aiosqlite, alembic, aiogram, httpx, pydantic, jinja2, greenlet" &>/dev/null; then
    echo "   ⏳ Đang cài đặt/cập nhật thư viện từ requirements.txt (bao gồm greenlet & sqlalchemy[asyncio])..."
    $PIP_BIN install --quiet --upgrade pip setuptools wheel 2>/dev/null || true
    $PIP_BIN install -r requirements.txt || {
        echo "❌ LỖI khi cài đặt thư viện Python!"
        exit 1
    }
    echo "   ✅ Đã cài đặt xong toàn bộ thư viện."
else
    echo "   ✅ Môi trường Python đã có đủ các thư viện cần thiết (bao gồm greenlet)."
fi

# 7. Dọn dẹp tiến trình cũ & giải phóng cổng 8000 (tránh Address already in use)
echo "🧹 [5/6] Kiểm tra và giải phóng cổng 8000 (tránh xung đột tiến trình)..."
pkill -f "uvicorn app.main:app" 2>/dev/null || true
pkill -f "app.bot.main" 2>/dev/null || true
pkill -f "app.jobs.worker" 2>/dev/null || true
if command -v fuser &>/dev/null; then
    fuser -k 8000/tcp 2>/dev/null || true
fi
sleep 1

# 8. Đồng bộ Database Migrations (Alembic) và Phân quyền RBAC
echo "⚙️  [6/6] Đồng bộ cơ sở dữ liệu và tài khoản Admin..."
$PYTHON_BIN scripts/setup.py || {
    echo "❌ LỖI trong quá trình thiết lập cơ sở dữ liệu (setup.py)!"
    exit 1
}

# 9. Đăng ký tín hiệu dọn dẹp (Cleanup trap)
API_PID=""
BOT_PID=""
WORKER_PID=""

cleanup() {
    echo ""
    echo "🛑 Nhận tín hiệu dừng. Đang tắt toàn bộ tiến trình Boconic..."
    [ -n "$API_PID" ] && kill -TERM "$API_PID" 2>/dev/null || true
    [ -n "$BOT_PID" ] && kill -TERM "$BOT_PID" 2>/dev/null || true
    [ -n "$WORKER_PID" ] && kill -TERM "$WORKER_PID" 2>/dev/null || true
    wait 2>/dev/null || true
    echo "✅ Toàn bộ dịch vụ đã dừng an toàn. Tạm biệt!"
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

# 10. Khởi chạy 3 dịch vụ nền
echo ""
echo "=============================================================================="
echo "               ĐANG KHỞI CHẠY CÁC DỊCH VỤ BOCONIC..."
echo "=============================================================================="

echo "🚀 [1/3] Khởi chạy FastAPI Backend & Admin Console (Port 8000)..."
$PYTHON_BIN -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
API_PID=$!

echo "🚀 [2/3] Khởi chạy Telegram Bot Gateway..."
$PYTHON_BIN -m app.bot.main &
BOT_PID=$!

echo "🚀 [3/3] Khởi chạy Background Job Worker..."
$PYTHON_BIN -m app.jobs.worker &
WORKER_PID=$!

# Đợi 2 giây để các tiến trình ổn định
sleep 2

# Kiểm tra xem các tiến trình có còn sống không
if ! kill -0 "$API_PID" 2>/dev/null; then
    echo "❌ CẢNH BÁO: FastAPI Backend không khởi động được!"
fi
if ! kill -0 "$BOT_PID" 2>/dev/null; then
    echo "❌ CẢNH BÁO: Telegram Bot không khởi động được!"
fi
if ! kill -0 "$WORKER_PID" 2>/dev/null; then
    echo "❌ CẢNH BÁO: Background Worker không khởi động được!"
fi

echo ""
echo "=============================================================================="
echo "                     🎉 HỆ THỐNG ĐÃ SẴN SÀNG HOẠT ĐỘNG!                       "
echo "=============================================================================="
echo " 🌐 Admin Web Console : http://127.0.0.1:8000/admin"
echo "    • Tài khoản mặc định : admin"
echo "    • Mật khẩu mặc định : Boconic@2026"
echo ""
echo " 📖 API Docs (Swagger): http://127.0.0.1:8000/docs"
echo " 🩺 Health Check      : http://127.0.0.1:8000/health/live"
echo " 🤖 Telegram Bot      : Đang chạy kết nối Telegram"
echo " ⚙️  Job Worker        : Đang xử lý hàng đợi outbox"
echo "=============================================================================="
echo "👉 Nhấn Ctrl + C để dừng tất cả dịch vụ bất cứ lúc nào."
echo "=============================================================================="
echo ""

# Giữ script chạy và lắng nghe
wait
