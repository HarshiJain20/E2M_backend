import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from app.core import auth
from app.main import app

SUB = "33333333-3333-3333-3333-333333333333"
KEY = ec.generate_private_key(ec.SECP256R1())


class FakeJWKS:
    def get_signing_key_from_jwt(self, token):
        return type("Key", (), {"key": KEY.public_key()})()


@pytest.fixture
def anon_client(monkeypatch):
    monkeypatch.setattr(auth, "_jwks_client", lambda: FakeJWKS())
    with TestClient(app) as client:
        yield client


def token(**overrides) -> str:
    claims = {"sub": SUB, "email": "c@test", "aud": "authenticated", "exp": int(time.time()) + 600}
    claims.update(overrides)
    return jwt.encode(claims, KEY, algorithm="ES256")


def test_missing_token_is_rejected(anon_client):
    response = anon_client.get("/api/v1/projects")
    assert response.status_code == 401


def test_valid_supabase_token_is_accepted(anon_client):
    response = anon_client.get("/api/v1/projects", headers={"Authorization": f"Bearer {token()}"})
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize(
    "bad",
    [
        {"exp": int(time.time()) - 10},
        {"aud": "anon"},
    ],
)
def test_expired_or_wrong_audience_is_rejected(anon_client, bad):
    response = anon_client.get("/api/v1/projects", headers={"Authorization": f"Bearer {token(**bad)}"})
    assert response.status_code == 401


def test_token_signed_by_other_key_is_rejected(anon_client):
    other = jwt.encode(
        {"sub": SUB, "aud": "authenticated", "exp": int(time.time()) + 600},
        ec.generate_private_key(ec.SECP256R1()),
        algorithm="ES256",
    )
    response = anon_client.get("/api/v1/projects", headers={"Authorization": f"Bearer {other}"})
    assert response.status_code == 401


def test_dev_bypass_uses_fixed_user(monkeypatch):
    settings = auth.get_settings()
    monkeypatch.setattr(settings.auth, "disabled", True)
    import asyncio

    user = asyncio.run(auth.get_current_user(None))
    assert user.id == uuid.UUID(settings.auth.dev_user_id)
