"""Redesign preview: only chosen regions change, openings and lighting are kept, scale is real."""
import io

import numpy as np
import pytest
from PIL import Image

from app.catalog import MATERIALS
from app.services.measurement import Scale
from app.services.render import render_design
from app.services.textures import material_texture
from tests.conftest import make_photo

M = {m["key"]: m for m in MATERIALS}
BY_ID = {m["id"]: m for m in MATERIALS}
W, H = 800, 600
SCALE = Scale("reference", "test", 0.01)  # 1 px = 1 cm, so 100 px per metre


def flat_photo(left=200, right=120) -> bytes:
    """A grey photo that is brighter on the left than on the right (lighting to preserve)."""
    array = np.zeros((H, W, 3), dtype=np.uint8)
    array[:, : W // 2] = left
    array[:, W // 2:] = right
    buffer = io.BytesIO()
    Image.fromarray(array).save(buffer, format="PNG")
    return buffer.getvalue()


def rect(sid, label, x0, y0, x1, y1):
    return {"id": sid, "label": label, "polygon": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], "bbox": [x0, y0, x1, y1],
            "depth_stats": None}


WALL = rect("wall", "wall", 0.1, 0.1, 0.9, 0.9)
WINDOW = rect("window", "window", 0.2, 0.2, 0.3, 0.3)


def render(segments, assignments, photo=None):
    jpeg = render_design(photo or flat_photo(), segments, assignments, BY_ID, SCALE, 1000)
    return np.asarray(Image.open(io.BytesIO(jpeg)).convert("RGB"), dtype=np.float32)


def paint(segment, colour="#ff0000"):
    return {"segment_id": segment["id"], "material_id": M["paint-acrylic-exterior"]["id"], "color": colour}


def test_only_assigned_regions_change():
    before = render([WALL], [])
    after = render([WALL], [paint(WALL)])

    assert np.abs(before[:40, :40] - after[:40, :40]).max() < 6        # outside the wall: unchanged
    centre = after[300, 200]
    assert centre[0] > centre[1] + 60 and centre[0] > centre[2] + 60   # inside: red paint


def test_windows_are_restored_from_the_original():
    after = render([WALL, WINDOW], [paint(WALL)])
    window_pixel = after[150, 200]  # centre of the window
    assert abs(window_pixel[0] - window_pixel[1]) < 8                    # still the original grey, not red


def test_photo_lighting_is_kept():
    after = render([WALL], [paint(WALL, "#c0c0c0")])
    assert after[300, 200].mean() > after[300, 600].mean() + 25          # bright side stays brighter


def test_no_materials_returns_the_original():
    original = render([WALL], [])
    assert np.abs(original - render([WALL, WINDOW], [])).max() < 1


def test_every_catalog_material_renders():
    for material in MATERIALS:
        target = WALL if material["category"] != "railing" else rect("rail", "railing", 0.1, 0.4, 0.9, 0.5)
        after = render([target], [{"segment_id": target["id"], "material_id": material["id"], "color": None}])
        assert after.shape == (H, W, 3), material["key"]


def test_tiles_are_drawn_at_real_size():
    # Ceramic tiles are 450 × 300 mm; at 100 px per metre the horizontal joints repeat every 30 px.
    texture, alpha = material_texture(M["tile-ceramic-elevation"], None, 300, 300, 100.0, seed=1)
    joint_rows = np.where(texture[:, :, 0].mean(axis=1) > np.median(texture[:, :, 0].mean(axis=1)) + 0.05)[0]
    starts = joint_rows[np.diff(np.concatenate([[-10], joint_rows])) > 1]
    assert alpha is None
    assert np.diff(starts) == pytest.approx(30, abs=1)


def test_render_endpoint_returns_a_jpeg(client):
    files = [("images", ("h.jpg", make_photo(), "image/jpeg"))]
    project_id = client.post("/api/v1/projects", files=files).json()["id"]
    project = client.post(f"/api/v1/projects/{project_id}/variants", json={"name": "Design A"}).json()
    variant_id, photo = project["variants"][0]["id"], project["photos"][0]
    wall = next(s["id"] for s in photo["segments"] if s["label"] == "wall")
    client.put(f"/api/v1/variants/{variant_id}/assignments", json={"segment_ids": [wall], "material_id": M["stone-sandstone"]["id"]})

    response = client.get(f"/api/v1/variants/{variant_id}/render/{photo['id']}")

    assert response.status_code == 200 and response.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(response.content)).size == (photo["image_width"], photo["image_height"])


def test_render_is_private(client):
    from tests.conftest import USER_B

    files = [("images", ("h.jpg", make_photo(), "image/jpeg"))]
    project_id = client.post("/api/v1/projects", files=files).json()["id"]
    project = client.post(f"/api/v1/projects/{project_id}/variants", json={"name": "Design A"}).json()
    client.as_user(USER_B)
    url = f"/api/v1/variants/{project['variants'][0]['id']}/render/{project['photos'][0]['id']}"
    assert client.get(url).status_code == 404


# ── Photorealistic render (AI service faked) ──

def project_with_paint(client):
    files = [("images", ("h.jpg", make_photo(), "image/jpeg"))]
    project_id = client.post("/api/v1/projects", files=files).json()["id"]
    project = client.post(f"/api/v1/projects/{project_id}/variants", json={"name": "Design A"}).json()
    variant_id, photo = project["variants"][0]["id"], project["photos"][0]
    wall = next(s["id"] for s in photo["segments"] if s["label"] == "wall")
    client.put(f"/api/v1/variants/{variant_id}/assignments",
               json={"segment_ids": [wall], "material_id": M["stone-sandstone"]["id"]})
    return variant_id, photo, wall


@pytest.fixture
def fake_renderer(monkeypatch):
    from app.services import ai_geometry

    calls = []

    async def fake(original, draft, mask_png, prompt, seed=0):
        calls.append({"prompt": prompt, "mask": mask_png, "seed": seed})
        buffer = io.BytesIO()
        Image.new("RGB", (64, 48), (10, 200, 10)).save(buffer, format="JPEG")
        return buffer.getvalue()

    monkeypatch.setattr(ai_geometry, "render_photoreal", fake)
    return calls


def test_photoreal_is_made_once_and_reused(client, fake_renderer):
    variant_id, photo, _ = project_with_paint(client)
    url = f"/api/v1/variants/{variant_id}/photoreal/{photo['id']}"

    assert client.get(url).json() == {"status": "none", "url": None}
    created = client.post(url).json()
    assert created["status"] == "ready" and created["url"].startswith("/api/v1/media/")
    assert client.get(url).json() == created
    assert client.post(url).json() == created
    assert len(fake_renderer) == 1  # second POST reused the stored image
    assert "main walls: natural sandstone cladding" in fake_renderer[0]["prompt"]


def test_changing_materials_makes_the_render_stale(client, fake_renderer):
    variant_id, photo, wall = project_with_paint(client)
    url = f"/api/v1/variants/{variant_id}/photoreal/{photo['id']}"
    client.post(url)

    client.put(f"/api/v1/variants/{variant_id}/assignments",
               json={"segment_ids": [wall], "material_id": M["stone-granite"]["id"]})

    assert client.get(url).json()["status"] == "none"


def test_photoreal_mask_covers_assigned_regions_only(client, fake_renderer):
    variant_id, photo, _ = project_with_paint(client)
    client.post(f"/api/v1/variants/{variant_id}/photoreal/{photo['id']}")

    mask = np.asarray(Image.open(io.BytesIO(fake_renderer[0]["mask"])))
    wall = next(s for s in photo["segments"] if s["label"] == "wall")
    x0, y0, x1, y1 = wall["bbox"]
    h, w = mask.shape
    assert mask[int((y0 + y1) / 2 * h), int((x0 + x1) / 2 * w)] == 255
    assert mask[2, 2] == 0


def test_photoreal_needs_materials_on_the_photo(client, fake_renderer):
    files = [("images", ("h.jpg", make_photo(), "image/jpeg"))]
    project_id = client.post("/api/v1/projects", files=files).json()["id"]
    project = client.post(f"/api/v1/projects/{project_id}/variants", json={"name": "Design A"}).json()
    response = client.post(f"/api/v1/variants/{project['variants'][0]['id']}/photoreal/{project['photos'][0]['id']}")
    assert response.status_code == 422 and fake_renderer == []


def test_photoreal_reports_when_the_ai_service_is_off(client, monkeypatch):
    from app.services import ai_geometry

    async def offline(*args, **kwargs):
        raise ai_geometry.AIGeometryError("The photorealistic renderer is not reachable. Start the Kaggle notebook, or use the standard preview.")

    monkeypatch.setattr(ai_geometry, "render_photoreal", offline)
    variant_id, photo, _ = project_with_paint(client)

    response = client.post(f"/api/v1/variants/{variant_id}/photoreal/{photo['id']}")

    assert response.status_code == 503 and "Kaggle" in response.json()["detail"]


def test_photoreal_prompt_mentions_each_part():
    from app.services.render import photoreal_prompt

    segments = [{"id": "w", "label": "wall"}, {"id": "r", "label": "railing"}]
    assignments = [{"segment_id": "w", "material_id": M["paint-acrylic-exterior"]["id"], "color": "#ffffff"},
                   {"segment_id": "r", "material_id": M["railing-glass"]["id"], "color": None}]
    prompt = photoreal_prompt(segments, assignments, BY_ID)
    assert "main walls: smooth matte exterior emulsion paint in colour #ffffff" in prompt
    assert "balcony railing: frameless clear toughened glass balcony railing" in prompt
