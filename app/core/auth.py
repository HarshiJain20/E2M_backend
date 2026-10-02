"""
Supabase Auth integration.

The frontend signs users in with Supabase Auth and sends the access token as a Bearer
token. The token is verified against the project's JWKS (asymmetric signing keys), so
the backend never needs the JWT secret.
"""
import uuid
from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    id: uuid.UUID
    email: str | None = None


@lru_cache
def _jwks_client() -> jwt.PyJWKClient:
    settings = get_settings()
    if not settings.SUPABASE_URL:
        raise RuntimeError("E2M_SUPABASE_URL is required to verify access tokens")
    return jwt.PyJWKClient(
        f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json",
        cache_keys=True,
        lifespan=3600,
    )


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def verify_token(token: str) -> dict:
    settings = get_settings()
    signing_key = _jwks_client().get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["ES256", "RS256"],
        audience=settings.JWT_AUDIENCE,
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> CurrentUser:
    settings = get_settings()
    if settings.AUTH_DISABLED:
        return CurrentUser(id=uuid.UUID(settings.DEV_USER_ID), email="dev@localhost")

    if credentials is None:
        raise _unauthorized("Sign in to continue.")
    try:
        claims = await run_in_threadpool(verify_token, credentials.credentials)
        return CurrentUser(id=uuid.UUID(claims["sub"]), email=claims.get("email"))
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise _unauthorized("Your session has expired. Sign in again.") from exc
