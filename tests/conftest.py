"""Test configuration: SQLite database, local storage, stubbed geometry service."""
import io
import os
import tempfile
import uuid

_tmp = tempfile.mkdtemp(prefix="e2m-tests-")
os.environ.update(
    {
        # Point at a missing file so a developer's config.json never leaks into tests.
        "E2M_CONFIG_FILE": f"{_tmp}/no-config.json",
        "E2M_STORAGE__BACKEND": "local",
        "E2M_STORAGE__UPLOAD_DIR": f"{_tmp}/uploads",
        "E2M_AUTH__DISABLED": "false",
        "E2M_SUPABASE__URL": "https://example.supabase.co",
    }
)

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.core.auth import CurrentUser, get_current_user  # noqa: E402
from app.core.deps import memory_store  # noqa: E402
from app.main import app  # noqa: E402
from app.services import ai_geometry  # noqa: E402

USER_A = CurrentUser(id=uuid.UUID("11111111-1111-1111-1111-111111111111"), email="a@test")
USER_B = CurrentUser(id=uuid.UUID("22222222-2222-2222-2222-222222222222"), email="b@test")

FAKE_ANALYSIS = {
    "mock": True,
    "camera": {"focal_length_px": 1500.0, "source": "mock"},
    "depth": {"min_m": 6.0, "max_m": 14.0, "median_m": 9.0},
    "timings_ms": {"total": 5},
    "models": {"segmentation": "mock"},
    "segments": [
        {
            "label": "wall",
            "confidence": 0.9,
            "polygon": [[0.1, 0.3], [0.9, 0.3], [0.9, 0.9], [0.1, 0.9]],
            "bbox": [0.1, 0.3, 0.9, 0.9],
            "measure_type": "area",
            "area_sqm": 42.5,
            "scale_source": "depth",
        },
        {
            "label": "railing",
            "confidence": 0.7,
            "polygon": [[0.2, 0.5], [0.8, 0.5], [0.8, 0.55], [0.2, 0.55]],
            "bbox": [0.2, 0.5, 0.8, 0.55],
            "measure_type": "length",
            "length_m": 6.2,
            "scale_source": "depth",
        },
    ],
}


def make_photo(width: int = 1600, height: int = 1200, *, flat: bool = False, fmt: str = "JPEG") -> bytes:
    """A synthetic 'facade' with edges and texture, or a flat grey frame."""
    if flat:
        array = np.full((height, width, 3), 128, dtype=np.uint8)
    else:
        rng = np.random.default_rng(0)
        array = rng.integers(60, 200, size=(height, width, 3), dtype=np.uint8)
        array[height // 3 : height // 3 + 40, :, :] = 20
        array[:, width // 4 : width // 4 + 30, :] = 230
    buffer = io.BytesIO()
    Image.fromarray(array).save(buffer, format=fmt)
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def database():
    memory_store().__init__()  # fresh in-memory data for every test
    yield


@pytest.fixture
def geometry_calls(monkeypatch):
    calls: list[bytes] = []

    async def fake_analyze(image: bytes, filename: str = "working.jpg") -> dict:
        calls.append(image)
        return FAKE_ANALYSIS

    monkeypatch.setattr(ai_geometry, "analyze_image", fake_analyze)
    return calls


@pytest.fixture
def client(geometry_calls):
    current = {"user": USER_A}
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    with TestClient(app) as test_client:
        test_client.as_user = lambda user: current.update(user=user)
        yield test_client
    app.dependency_overrides.clear()
