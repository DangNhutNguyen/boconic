from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    APP_NAME: str = "Boconic"
    APP_ENV: str = "development"
    APP_TIMEZONE: str = "Asia/Ho_Chi_Minh"
    APP_BASE_URL: str = "http://localhost:8000"

    # Database: defaults to PostgreSQL when set, or fallback to local SQLite for tests/offline dev
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./data/boconic.db",
        description="Async database connection string"
    )

    # Telegram Bot
    BOT_TOKEN: str = ""
    BOT_USERNAME: str = ""
    ADMIN_USERNAME: str = "admin"
    ADMIN_TELEGRAM_ID: str = ""

    # Security
    ADMIN_LOGIN: str = "admin"
    SECRET_KEY: str = "boconic_super_secure_secret_key_change_me_in_production_min_32_chars"
    BOT_API_KEY: str = "boconic_internal_bot_api_key_32_chars_min"
    SESSION_COOKIE_NAME: str = "boconic_session"
    SESSION_MAX_AGE_SECONDS: int = 86400 * 7  # 7 days

    # Features & Limits
    DEMO_MODE: bool = False
    OCR_ENABLED: bool = False
    AI_QUERY_ENABLED: bool = False
    SEMANTIC_SEARCH_ENABLED: bool = False
    AI_PROVIDER: str = "disabled"
    AI_API_KEY: str = ""

    STORAGE_DIR: str = str(BASE_DIR / "data" / "storage")
    BACKUP_DIR: str = str(BASE_DIR / "data" / "backups")
    UPLOAD_MAX_MB: int = 10

    @property
    def is_sqlite(self) -> bool:
        return "sqlite" in self.DATABASE_URL

settings = Settings()

# Ensure local directories exist
Path(settings.STORAGE_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.BACKUP_DIR).mkdir(parents=True, exist_ok=True)
Path(BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
