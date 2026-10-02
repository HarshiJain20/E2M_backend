"""Reviewing detected regions: relabel, delete, confirm (requirement 5.2)."""
import pytest

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
    assert balcony["id"] == wall["id"] and balcony["area_sqm"] == wall["area_sqm"]
    assert {t["label"] for t in updated["totals"]} == {"balcony", "railing"}


def test_relabel_area_to_length_is_remeasured_as_length(client):
    photo = new_project(client)["photos"][0]
    wall = region(photo, "wall")

    updated = client.patch(f"/api/v1/segments/{wall['id']}", json={"label": "railing"}).json()

    changed = next(s for s in updated["photos"][0]["segments"] if s["id"] == wall["id"])
    assert changed["measure_type"] == "length"
    assert changed["area_sqm"] is None and changed["length_m"] > 0


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


def test_user_measurement_rescales_the_photo_and_can_be_removed(client):
    photo = new_project(client)["photos"][0]
    wall = region(photo, "wall")
    assert photo["scale"]["source"] == "assumed"

    body = {"segment_id": wall["id"], "dimension": "width", "metres": 12.8}
    updated = client.put(f"/api/v1/photos/{photo['id']}/reference", json=body).json()

    p = updated["photos"][0]
    assert p["scale"]["source"] == "user" and p["reference"]["metres"] == 12.8
    # The fake wall is 0.8 × 0.6 of a 1600 × 1200 photo: 1280 × 720 px → 12.8 m × 7.2 m.
    assert region(p, "wall")["area_sqm"] == pytest.approx(92.16)

    cleared = client.delete(f"/api/v1/photos/{photo['id']}/reference").json()["photos"][0]
    assert cleared["scale"]["source"] == "assumed" and cleared["reference"] is None


def test_measurement_must_use_a_region_from_the_same_photo(client):
    first = new_project(client)["photos"][0]
    other = new_project(client)["photos"][0]

    body = {"segment_id": region(other, "wall")["id"], "dimension": "height", "metres": 3}
    assert client.put(f"/api/v1/photos/{first['id']}/reference", json=body).status_code == 422
    body["metres"] = 0
    assert client.put(f"/api/v1/photos/{first['id']}/reference", json=body).status_code == 422


def test_deleting_the_measured_region_drops_the_measurement(client):
    photo = new_project(client)["photos"][0]
    wall = region(photo, "wall")
    client.put(f"/api/v1/photos/{photo['id']}/reference",
               json={"segment_id": wall["id"], "dimension": "height", "metres": 7})

    after = client.delete(f"/api/v1/segments/{wall['id']}").json()["photos"][0]

    assert after["reference"] is None and after["scale"]["source"] == "assumed"
