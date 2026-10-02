"""Per-request data and storage access, scoped to the signed-in user."""
from functools import lru_cache

from fastapi import Depends

from app.core.auth import CurrentUser, get_current_user
from app.core.config import get_settings
from app.repositories.base import Repository
from app.repositories.memory import MemoryRepository, MemoryStore
from app.repositories.supabase import SupabaseRepository
from app.services.storage import LocalStorage, Storage, SupabaseStorage


@lru_cache
def memory_store() -> MemoryStore:
    """Process-wide store for storage.backend = "local" (offline development, tests)."""
    return MemoryStore()


def get_repository(user: CurrentUser = Depends(get_current_user)) -> Repository:
    settings = get_settings()
    if settings.storage.backend == "local":
        return MemoryRepository(memory_store(), str(user.id))
    return SupabaseRepository(settings, user.access_token)


def get_storage(user: CurrentUser = Depends(get_current_user)) -> Storage:
    settings = get_settings()
    if settings.storage.backend == "local":
        return LocalStorage(settings)
    return SupabaseStorage(settings, user.access_token)
