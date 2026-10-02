"""
E2M Backend — Core Configuration.

Loads environment variables via pydantic-settings.
All sensitive values come from .env file or OS environment.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── App ──
    APP_NAME: str = "E2M Backend"
    APP_VERSION: str = "0.2.0"
    DEBUG: bool = False

    # ── Server ──
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # ── Database (Supabase Postgres, session pooler) ──
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/e2m"
    DATABASE_URL_SYNC: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/e2m"

    # ── Supabase ──
    SUPABASE_URL: str = ""
    # Server-only key (sb_secret_...). Used for Storage; never expose to the browser.
    SUPABASE_SECRET_KEY: str = ""
    SUPABASE_STORAGE_BUCKET: str = "project-images"
    SIGNED_URL_TTL_SECONDS: int = 3600

    # ── Auth ──
    # Local development only: skip JWT verification and act as a fixed dev user.
    AUTH_DISABLED: bool = False
    DEV_USER_ID: str = "00000000-0000-0000-0000-000000000001"
    JWT_AUDIENCE: str = "authenticated"

    # ── AI-Geometry Service ──
    AI_GEOMETRY_URL: str = "http://localhost:8100"
    AI_GEOMETRY_TIMEOUT_SECONDS: float = 300.0

    # ── CORS ──
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # ── File Storage ──
    # "supabase" in deployed environments; "local" writes under UPLOAD_DIR for offline dev.
    STORAGE_BACKEND: str = "supabase"
    UPLOAD_DIR: str = "./uploads"
    MAX_FILE_SIZE_MB: int = 20
    WORKING_IMAGE_MAX_SIDE: int = 2048
    THUMBNAIL_MAX_SIDE: int = 480

    # ── Pricing Constants ──
    LABOR_CESS_RATE: float = 0.01     # 1%
    GST_RATE: float = 0.18            # 18%
    DEFAULT_WASTAGE_FACTOR: float = 0.10  # 10%

    model_config = {
        "env_prefix": "E2M_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore",
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()
