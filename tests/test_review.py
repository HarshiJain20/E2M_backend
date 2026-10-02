"""Reviewing detected regions: relabel, delete, confirm (requirement 5.2)."""
from tests.conftest import USER_B, make_photo


def new_project(client):
    files = [("images", ("h.jpg", make_photo(), "image/jpeg"))]
    project_id = client.post("/api/v1/projects", files=files).json()["id"]
    return client.get(f"/api/v1/projects/{project_id}").json()


def region(photo, label):
    return next(s for s in photo["segments"] if s["label"] == label)


def test_relabel_within_same_measure_keeps_size(client):
    photo = new_project(client)["photos"][0]
    wall = region(photo, "wall")

    updated = client.patch(f"/api/v1/segments/{wall['id']}", json={"label": "balcony"}).json()

    balcony = region(updated["photos"][0], "balcony")
    assert balcony["id"] == wall["id"] and balcony["area_sqm"] == 42.5
    assert {t["label"] for t in updated["totals"]} == {"balcony", "railing"}


def test_relabel_area_to_length_clears_size_for_remeasurement(client):
    photo = new_project(client)["photos"][0]
    wall = region(photo, "wall")

    updated = client.patch(f"/api/v1/segments/{wall['id']}", json={"label": "railing"}).json()

    changed = next(s for s in updated["photos"][0]["segments"] if s["id"] == wall["id"])
    assert changed["measure_type"] == "length"
    assert changed["area_sqm"] is None and changed["length_m"] is None


def test_unknown_label_is_rejected(client):
    photo = new_project(client)["photos"][0]
    response = client.patch(f"/api/v1/segments/{photo['segments'][0]['id']}", json={"label": "tree"})
    assert response.status_code == 422


def test_delete_region_updates_totals(client):
    photo = new_project(client)["photos"][0]

    updated = client.delete(f"/api/v1/segments/{region(photo, 'railing')['id']}").json()

    assert [s["label"] for s in updated["photos"][0]["segments"]] == ["wall"]
    assert [t["label"] for t in updated["totals"]] == ["wall"]


def test_confirm_marks_photo_reviewed(client):
    photo = new_project(client)["photos"][0]
    assert photo["regions_confirmed"] is False

    updated = client.post(f"/api/v1/photos/{photo['id']}/confirm").json()

    assert updated["photos"][0]["regions_confirmed"] is True
    assert all(s["is_confirmed"] for s in updated["photos"][0]["segments"])


def test_reanalysis_replaces_edited_regions(client):
    project = new_project(client)
    photo = project["photos"][0]
    client.patch(f"/api/v1/segments/{region(photo, 'wall')['id']}", json={"label": "balcony"})

    assert client.post(f"/api/v1/photos/{photo['id']}/analyze").status_code == 202

    after = client.get(f"/api/v1/projects/{project['id']}").json()["photos"][0]
    assert sorted(s["label"] for s in after["segments"]) == ["railing", "wall"]  # fresh detection, no duplicates


def test_regions_are_private(client):
    photo = new_project(client)["photos"][0]
    segment_id = photo["segments"][0]["id"]

    client.as_user(USER_B)
    assert client.patch(f"/api/v1/segments/{segment_id}", json={"label": "door"}).status_code == 404
    assert client.delete(f"/api/v1/segments/{segment_id}").status_code == 404
    assert client.post(f"/api/v1/photos/{photo['id']}/confirm").status_code == 404


def test_no_house_warning_is_kept_on_the_job(client, monkeypatch):
    from app.services import ai_geometry

    async def nothing_found(image: bytes, filename: str = "working.jpg") -> dict:
        return {"mock": False, "segments": [], "warnings": ["no_house_detected"], "models": {}}

    monkeypatch.setattr(ai_geometry, "analyze_image", nothing_found)
    photo = new_project(client)["photos"][0]

    assert photo["segments"] == []
    assert photo["latest_job"]["result_meta"]["warnings"] == ["no_house_detected"]
