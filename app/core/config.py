"""
E2M Backend — Configuration.

Settings are read from `config.json` in the repository root (copy `config.example.json`).
Set `E2M_CONFIG_FILE` to load a different file. Individual values can be overridden with
environment variables named `E2M_<SECTION>__<KEY>`, e.g. `E2M_DATABASE__URL`; this is
how tests and container deployments inject values. Precedence: environment > file > defaults.
"""
import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import (
    BaseSettings,
    JsonConfigSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

ROOT_DIR = Path(__file__).resolve().parents[2]


def config_path() -> Path:
    return Path(os.environ.get("E2M_CONFIG_FILE", ROOT_DIR / "config.json"))


class AppConfig(BaseModel):
    name: str = "E2M Backend"
    version: str = "0.2.0"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]


class SupabaseConfig(BaseModel):
    url: str = ""
    # Public key (sb_publishable_...). Requests also carry the signed-in user's token, so
    # Row Level Security in supabase/schema.sql decides what each user can read and write.
    publishable_key: str = ""
    storage_bucket: str = "project-images"
    signed_url_ttl_seconds: int = 3600
    timeout_seconds: float = 30.0


class AuthConfig(BaseModel):
    # Local development only: skip JWT verification and act as a fixed dev user.
    disabled: bool = False
    dev_user_id: str = "00000000-0000-0000-0000-000000000001"
    jwt_audience: str = "authenticated"


class AIGeometryConfig(BaseModel):
    url: str = "http://localhost:8100"
    # Must match auth.api_key in the AI service's config (required when it runs on Kaggle).
    api_key: str = ""
    timeout_seconds: float = 300.0


class StorageConfig(BaseModel):
    # "supabase": data in Supabase Postgres, photos in Supabase Storage.
    # "local": offline development — data in memory (lost on restart), photos under upload_dir.
    backend: str = "supabase"
    upload_dir: str = "./uploads"
    max_file_size_mb: int = 20
    working_image_max_side: int = 2048
    thumbnail_max_side: int = 480

    @property
    def upload_path(self) -> Path:
        """upload_dir resolved against the repository root, not the working directory."""
        return (ROOT_DIR / self.upload_dir).resolve()


class PricingConfig(BaseModel):
    labor_cess_rate: float = 0.01
    gst_rate: float = 0.18
    default_wastage_factor: float = 0.10


class Settings(BaseSettings):
    app: AppConfig = AppConfig()
    supabase: SupabaseConfig = SupabaseConfig()
    auth: AuthConfig = AuthConfig()
    ai_geometry: AIGeometryConfig = AIGeometryConfig()
    storage: StorageConfig = StorageConfig()
    pricing: PricingConfig = PricingConfig()

    model_config = SettingsConfigDict(
        env_prefix="E2M_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            JsonConfigSettingsSource(settings_cls, json_file=config_path()),
        )


@lru_cache()
def get_settings() -> Settings:
    return Settings()


def configuration_problems(settings: Settings) -> list[str]:
    """Human-readable problems with config.json that will stop the app working."""
    if settings.storage.backend == "local":
        return []
    problems = []
    if not settings.supabase.url or "<" in settings.supabase.url:
        problems.append("supabase.url is not set. Use https://<project-ref>.supabase.co.")
    if not settings.supabase.publishable_key.startswith(("sb_publishable_", "eyJ")) or \
            settings.supabase.publishable_key.endswith("..."):
        problems.append(
            "supabase.publishable_key is not set. Copy the publishable key (sb_publishable_…) "
            "from Supabase Dashboard → Project Settings → API Keys."
        )
    return problems
