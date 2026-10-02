"""Material catalog and design variants (requirement 5.3)."""
import pytest

from app.catalog import MATERIALS
from scripts.generate_seed_sql import OUT, render
from tests.conftest import USER_B, make_photo

PAINT = next(m for m in MATERIALS if m["key"] == "paint-acrylic-exterior")
STONE = next(m for m in MATERIALS if m["key"] == "stone-sandstone")
GLASS_RAILING = next(m for m in MATERIALS if m["key"] == "railing-glass")


def new_project(client):
    files = [("images", ("h.jpg", make_photo(), "image/jpeg"))]
    project_id = client.post("/api/v1/projects", files=files).json()["id"]
    return client.get(f"/api/v1/projects/{project_id}").json()


def segment_id(project, label):
    return next(s["id"] for s in project["photos"][0]["segments"] if s["label"] == label)


def new_variant(client, project, name="Design A", **extra):
    response = client.post(f"/api/v1/projects/{project['id']}/variants", json={"name": name, **extra})
    assert response.status_code == 201
    return response.json()


def assign(client, variant_id, segment_ids, material, color=None):
    body = {"segment_ids": segment_ids, "material_id": material["id"]}
    if color:
        body["color"] = color
    return client.put(f"/api/v1/variants/{variant_id}/assignments", json=body)


def test_catalog_lists_every_material_with_rates_and_guidance(client):
    materials = client.get("/api/v1/materials").json()

    assert len(materials) == len(MATERIALS) >= 12
    for m in materials:
        assert m["material_rate"] > 0 and m["labor_rate"] > 0 and m["unit"] in ("sqm", "rmt")
        assert m["suitability"] and m["maintenance"] and m["durability"] and m["applies_to"]
        assert m["rate_source"]
    categories = {m["category"] for m in materials}
    assert {"paint", "texture", "stone_cladding", "tiles", "panels", "railing"} <= categories


def test_seed_sql_is_generated_from_the_catalog():
    assert OUT.read_text() == render(), "Run: python -m scripts.generate_seed_sql"


def test_create_variant_and_apply_materials(client):
    project = new_project(client)
    variant = new_variant(client, project)["variants"][0]
    wall, railing = segment_id(project, "wall"), segment_id(project, "railing")

    assert assign(client, variant["id"], [wall], PAINT, "#aabbcc").status_code == 200
    updated = assign(client, variant["id"], [railing], GLASS_RAILING).json()

    assignments = {a["segment_id"]: a for a in updated["variants"][0]["assignments"]}
    assert assignments[wall]["material_id"] == PAINT["id"] and assignments[wall]["color"] == "#aabbcc"
    assert assignments[railing]["material_id"] == GLASS_RAILING["id"] and assignments[railing]["color"] is None


def test_reassigning_replaces_the_material(client):
    project = new_project(client)
    variant = new_variant(client, project)["variants"][0]
    wall = segment_id(project, "wall")

    assign(client, variant["id"], [wall], PAINT)
    updated = assign(client, variant["id"], [wall], STONE).json()

    [only] = updated["variants"][0]["assignments"]
    assert only["material_id"] == STONE["id"] and only["color"] is None  # stone has no colour choice


def test_paint_without_colour_uses_its_default_swatch(client):
    project = new_project(client)
    variant = new_variant(client, project)["variants"][0]
    updated = assign(client, variant["id"], [segment_id(project, "wall")], PAINT).json()
    assert updated["variants"][0]["assignments"][0]["color"] == PAINT["swatch"]


def test_material_must_suit_the_region(client):
    project = new_project(client)
    variant = new_variant(client, project)["variants"][0]

    response = assign(client, variant["id"], [segment_id(project, "railing")], PAINT)

    assert response.status_code == 422
    assert "can't be used on: railing" in response.json()["detail"]


@pytest.mark.parametrize("color", ["red", "#12345", "#gggggg"])
def test_invalid_colour_is_rejected(client, color):
    project = new_project(client)
    variant = new_variant(client, project)["variants"][0]
    assert assign(client, variant["id"], [segment_id(project, "wall")], PAINT, color).status_code == 422


def test_clearing_a_region_material(client):
    project = new_project(client)
    variant = new_variant(client, project)["variants"][0]
    wall = segment_id(project, "wall")
    assign(client, variant["id"], [wall], PAINT)

    updated = client.delete(f"/api/v1/variants/{variant['id']}/assignments", params={"segment_ids": [wall]}).json()

    assert updated["variants"][0]["assignments"] == []


def test_duplicate_rename_and_delete_designs(client):
    project = new_project(client)
    first = new_variant(client, project)["variants"][0]
    assign(client, first["id"], [segment_id(project, "wall")], PAINT)

    both = new_variant(client, project, "Design B", copy_from=first["id"])["variants"]
    assert [v["name"] for v in both] == ["Design A", "Design B"]
    assert both[1]["assignments"][0]["material_id"] == PAINT["id"]  # copied

    renamed = client.patch(f"/api/v1/variants/{both[1]['id']}", json={"name": "Stone look"}).json()
    assert [v["name"] for v in renamed["variants"]] == ["Design A", "Stone look"]

    after = client.delete(f"/api/v1/variants/{first['id']}").json()
    assert [v["name"] for v in after["variants"]] == ["Stone look"]


def test_relabelling_a_region_clears_its_material(client):
    project = new_project(client)
    variant = new_variant(client, project)["variants"][0]
    wall = segment_id(project, "wall")
    assign(client, variant["id"], [wall], PAINT)

    updated = client.patch(f"/api/v1/segments/{wall}", json={"label": "railing"}).json()

    assert updated["variants"][0]["assignments"] == []


def test_deleting_a_region_removes_its_material(client):
    project = new_project(client)
    variant = new_variant(client, project)["variants"][0]
    wall = segment_id(project, "wall")
    assign(client, variant["id"], [wall], PAINT)

    updated = client.delete(f"/api/v1/segments/{wall}").json()

    assert updated["variants"][0]["assignments"] == []


def test_designs_are_private(client):
    project = new_project(client)
    variant = new_variant(client, project)["variants"][0]
    wall = segment_id(project, "wall")

    client.as_user(USER_B)
    assert client.post(f"/api/v1/projects/{project['id']}/variants", json={"name": "x"}).status_code == 404
    assert assign(client, variant["id"], [wall], PAINT).status_code == 404
    assert client.patch(f"/api/v1/variants/{variant['id']}", json={"name": "x"}).status_code == 404
    assert client.delete(f"/api/v1/variants/{variant['id']}").status_code == 404


def test_regions_from_another_project_are_rejected(client):
    first, second = new_project(client), new_project(client)
    variant = new_variant(client, first)["variants"][0]

    assert assign(client, variant["id"], [segment_id(second, "wall")], PAINT).status_code == 422


def test_design_names_are_unique_within_a_project(client):
    project = new_project(client)
    first = new_variant(client, project)["variants"][0]
    new_variant(client, project, "Design B")

    duplicate = client.post(f"/api/v1/projects/{project['id']}/variants", json={"name": "Design A"})
    rename = client.patch(f"/api/v1/variants/{first['id']}", json={"name": "Design B"})

    assert duplicate.status_code == 409 and "already exists" in duplicate.json()["detail"]
    assert rename.status_code == 409
    assert client.patch(f"/api/v1/variants/{first['id']}", json={"name": "Design A"}).status_code == 200  # own name
    other = new_project(client)
    assert client.post(f"/api/v1/projects/{other['id']}/variants", json={"name": "Design A"}).status_code == 201
