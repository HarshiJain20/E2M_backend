"""Quantities and cost, checked against hand calculations."""
import pytest

from app.catalog import MATERIALS
from app.services.estimate import estimate_variant, purchase_quantities
from tests.conftest import make_photo

M = {m["key"]: m for m in MATERIALS}
PAINT, STONE, GLASS = M["paint-acrylic-exterior"], M["stone-sandstone"], M["railing-glass"]
BY_ID = {m["id"]: m for m in MATERIALS}
PHOTOS = [{"id": "p1", "is_primary": True}, {"id": "p2", "is_primary": False}]


def seg(sid, photo, label, area=None, net=None, length=None):
    return {"id": sid, "photo_id": photo, "label": label, "measure_type": "length" if length else "area",
            "area_sqm": area, "net_area_sqm": net, "length_m": length}


SEGMENTS = [
    seg("wall", "p1", "wall", area=60, net=50),   # 60 m² wall with 10 m² of openings
    seg("pillar", "p1", "pillar", area=10),
    seg("railing", "p1", "railing", length=6),
    seg("balcony", "p1", "balcony", area=8),        # no material → reported as missing
    seg("wall-dup", "p2", "wall", area=45, net=40),  # second photo of the same side → not counted
]


def variant(*assignments):
    return {"id": "v1", "name": "Design A",
            "assignments": [{"segment_id": s, "material_id": m["id"], "color": c} for s, m, c in assignments]}


def run(var, overrides=None, include_gst=True):
    return estimate_variant(var, PHOTOS, SEGMENTS, BY_ID, overrides or {}, include_gst, 0.18)


def test_paint_and_glass_railing_by_hand():
    result = run(variant(("wall", PAINT, "#ffffff"), ("pillar", PAINT, "#ffffff"), ("railing", GLASS, None),
                         ("wall-dup", PAINT, "#ffffff")))
    paint, glass = sorted(result["lines"], key=lambda l: l["category"])

    # Paint: 50 m² wall (net) + 10 m² pillar = 60 m²; +5 % wastage = 63 m².
    assert paint["measured_qty"] == 60 and paint["quantity"] == 63
    assert paint["material_cost"] == 63 * 95 and paint["labor_cost"] == 60 * 65 and paint["total"] == 9885
    assert {w["label"]: w["count"] for w in paint["where"]} == {"wall": 1, "pillar": 1}
    litres, primer = paint["purchase"]
    assert litres == {"item": "Paint", "amount": 10.5, "unit": "litres", "packs": 1, "pack": "20 L can"}
    assert primer["item"] == "Primer" and primer["amount"] == 5.4  # 60 m² × 0.09 L

    # Glass railing: 6 m; +5 % = 6.3 m.
    assert glass["quantity"] == 6.3 and glass["material_cost"] == 40950 and glass["labor_cost"] == 7200

    assert result["subtotal"] == 58035 and result["gst"] == pytest.approx(10446.3)
    assert result["grand_total"] == pytest.approx(68481.3)
    assert result["regions_without_material"] == 1   # the balcony
    assert result["regions_not_counted"] == 1        # the duplicate photo's wall


def test_categories_add_up():
    result = run(variant(("wall", PAINT, "#ffffff"), ("railing", GLASS, None)))
    totals = {c["category"]: c["total"] for c in result["categories"]}
    assert totals == {"paint": 50 * 1.05 * 95 + 50 * 65, "railing": 48150}
    assert sum(totals.values()) == result["subtotal"]


def test_gst_can_be_switched_off():
    result = run(variant(("railing", GLASS, None)), include_gst=False)
    assert result["gst"] == 0 and result["grand_total"] == result["subtotal"] == 48150


def test_project_rate_overrides_change_only_that_material():
    overrides = {PAINT["id"]: {"material_rate": 120, "labor_rate": None}}
    result = run(variant(("wall", PAINT, "#ffffff"), ("railing", GLASS, None)), overrides)
    paint = next(l for l in result["lines"] if l["category"] == "paint")
    glass = next(l for l in result["lines"] if l["category"] == "railing")

    assert paint["material_rate"] == 120 and paint["labor_rate"] == 65 and paint["rate_changed"]
    assert paint["material_cost"] == pytest.approx(52.5 * 120)
    assert paint["catalog_material_rate"] == 95
    assert not glass["rate_changed"]


def test_different_colours_are_separate_lines():
    result = run(variant(("wall", PAINT, "#ffffff"), ("pillar", PAINT, "#aa5533")))
    assert sorted(l["color"] for l in result["lines"]) == ["#aa5533", "#ffffff"]


def test_stone_slab_count():
    [line] = run(variant(("wall", STONE, None)))["lines"]
    assert line["quantity"] == 55  # 50 m² + 10 %
    assert line["purchase"] == [{"item": "Slabs", "amount": 306, "unit": "600 × 300 mm"}]  # ⌈55 / 0.18⌉


def test_purchase_quantities_for_bags_and_sheets():
    cement = M["paint-cement-economy"]
    acp = M["panel-acp"]
    assert purchase_quantities(cement, 100, 95)[0] == {"item": "Cement paint", "amount": 33.0, "unit": "kg",
                                                       "packs": 2, "pack": "25 kg bag"}
    assert purchase_quantities(acp, 30, 27) == [{"item": "Sheets", "amount": 11, "unit": "1.22 × 2.44 m"}]


def test_empty_design_costs_nothing():
    result = run(variant())
    assert result["lines"] == [] and result["grand_total"] == 0 and result["regions_without_material"] == 4


# ── API ──

def new_project_with_design(client):
    files = [("images", ("h.jpg", make_photo(), "image/jpeg"))]
    project_id = client.post("/api/v1/projects", files=files).json()["id"]
    project = client.post(f"/api/v1/projects/{project_id}/variants", json={"name": "Design A"}).json()
    return project


def wall_id(project):
    return next(s["id"] for s in project["photos"][0]["segments"] if s["label"] == "wall")


def test_estimate_endpoint_follows_materials_and_rates(client):
    project = new_project_with_design(client)
    variant_id = project["variants"][0]["id"]
    client.put(f"/api/v1/variants/{variant_id}/assignments", json={"segment_ids": [wall_id(project)], "material_id": PAINT["id"]})

    estimate = client.get(f"/api/v1/projects/{project['id']}/estimate").json()
    [line] = estimate["variants"][0]["lines"]
    assert estimate["include_gst"] is True and estimate["gst_rate"] == 0.18
    assert line["material_rate"] == 95 and line["total"] > 0

    changed = client.put(f"/api/v1/projects/{project['id']}/rates/{PAINT['id']}", json={"labor_rate": 80}).json()
    line2 = changed["variants"][0]["lines"][0]
    assert line2["labor_rate"] == 80 and line2["material_rate"] == 95 and line2["rate_changed"]
    assert line2["labor_cost"] == pytest.approx(line["measured_qty"] * 80, abs=0.01)

    reset = client.delete(f"/api/v1/projects/{project['id']}/rates/{PAINT['id']}").json()
    assert reset["variants"][0]["lines"][0]["labor_rate"] == 65

    no_gst = client.patch(f"/api/v1/projects/{project['id']}/estimate-settings", json={"include_gst": False}).json()
    v = no_gst["variants"][0]
    assert no_gst["include_gst"] is False and v["gst"] == 0 and v["grand_total"] == v["subtotal"]


def test_rate_changes_are_per_project(client):
    first, second = new_project_with_design(client), new_project_with_design(client)
    for project in (first, second):
        client.put(f"/api/v1/variants/{project['variants'][0]['id']}/assignments",
                   json={"segment_ids": [wall_id(project)], "material_id": PAINT["id"]})

    client.put(f"/api/v1/projects/{first['id']}/rates/{PAINT['id']}", json={"material_rate": 200})

    other = client.get(f"/api/v1/projects/{second['id']}/estimate").json()
    assert other["variants"][0]["lines"][0]["material_rate"] == 95
    assert client.get("/api/v1/materials").json()  # catalog untouched
    assert next(m for m in client.get("/api/v1/materials").json() if m["id"] == PAINT["id"])["material_rate"] == 95


@pytest.mark.parametrize("body", [{}, {"material_rate": -5}])
def test_invalid_rates_are_rejected(client, body):
    project = new_project_with_design(client)
    assert client.put(f"/api/v1/projects/{project['id']}/rates/{PAINT['id']}", json=body).status_code == 422


def test_estimate_is_private(client):
    from tests.conftest import USER_B

    project = new_project_with_design(client)
    client.as_user(USER_B)
    assert client.get(f"/api/v1/projects/{project['id']}/estimate").status_code == 404
    assert client.put(f"/api/v1/projects/{project['id']}/rates/{PAINT['id']}", json={"material_rate": 1}).status_code == 404
