#!/usr/bin/env bash
# ==============================================================================
#                      BOCONIC PLATFORM - ALL-IN-ONE RUNNER
#                      Tự động hóa 100% trên Ubuntu / Debian / Linux
#                      "1 file .sh - ấn là chạy - không lỗi"
# ==============================================================================

# Chuyển tiếp tới start.sh với đầy đủ quyền và cùng thư mục
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f "$SCRIPT_DIR/start.sh" ]; then
    chmod +x "$SCRIPT_DIR/start.sh" 2>/dev/null || true
    exec "$SCRIPT_DIR/start.sh" "$@"
else
    echo "❌ Lỗi: Không tìm thấy start.sh"
    exit 1
fi
