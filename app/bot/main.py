import asyncio
import sys
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.handlers import router as bot_router
from app.core.config import settings
from app.core.logging import logger

async def run_bot():
    if not settings.BOT_TOKEN or settings.BOT_TOKEN == "CHANGE_ME":
        logger.warning(
            "===============================================================\n"
            "BOT_TOKEN chưa được cấu hình trong .env!\n"
            "Telegram Bot đang ở chế độ MOCK / OFFLINE DEMO.\n"
            "Backend API và Admin Console vẫn hoạt động bình thường tại http://127.0.0.1:8000/admin\n"
            "Để kết nối Telegram thật, hãy điền BOT_TOKEN nhận từ @BotFather vào .env\n"
            "==============================================================="
        )
        # Keep process alive or exit cleanly in mock mode
        while True:
            await asyncio.sleep(3600)
        return

    logger.info("Khởi động aiogram 3.x long polling cho Telegram Bot...")
    session = AiohttpSession(timeout=45.0)
    bot = Bot(token=settings.BOT_TOKEN, session=session)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(bot_router)

    try:
        me = await bot.get_me()
        logger.info(f"Telegram Bot đã kết nối thành công: @{me.username} ({me.first_name}) [ID: {me.id}]")
        logger.info(f"Super Admin Telegram ID được cấu hình: {settings.ADMIN_TELEGRAM_ID}")
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(run_bot())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot process đã dừng an toàn.")
