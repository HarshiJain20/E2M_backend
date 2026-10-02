from tests.conftest import USER_B, make_photo


def upload(client, data: bytes, name: str | None = "My house", content_type: str = "image/jpeg"):
    form = {"name": name} if name is not None else {}
    return client.post(
        "/api/v1/projects", files={"image": ("house.jpg", data, content_type)}, data=form
    )


def test_upload_creates_project_and_runs_analysis(client, geometry_calls):
    response = upload(client, make_photo())

    assert response.status_code == 201
    created = response.json()
    assert created["name"] == "My house"
    assert created["quality_report"]["usable"] is True
    assert created["image_width"] == 1600 and created["image_height"] == 1200

    # TestClient runs background tasks before returning, so the job has finished.
    detail = client.get(f"/api/v1/projects/{created['id']}").json()
    assert len(geometry_calls) == 1
    assert detail["status"] == "review"
    assert detail["latest_job"]["status"] == "succeeded"
    assert detail["latest_job"]["progress"] == 100
    assert detail["latest_job"]["result_meta"]["mock"] is True
    assert {s["label"] for s in detail["segments"]} == {"wall", "railing"}
    railing = next(s for s in detail["segments"] if s["label"] == "railing")
    assert railing["measure_type"] == "length" and railing["length_m"] == 6.2
    assert detail["image_url"].startswith("/api/v1/media/")


def test_large_upload_is_downscaled_for_processing(client):
    created = upload(client, make_photo(3000, 2000)).json()

    assert max(created["image_width"], created["image_height"]) == 2048
    assert created["image_meta"]["original_width"] == 3000


def test_default_name_when_blank(client):
    created = upload(client, make_photo(), name="  ").json()

    assert created["name"].startswith("Exterior project")


def test_unusable_photo_is_rejected_with_guidance(client, geometry_calls):
    response = upload(client, make_photo(400, 300, flat=True))

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "image_unusable"
    failed = {c["id"] for c in detail["quality_report"]["checks"] if c["status"] == "fail"}
    assert {"resolution", "contrast"} <= failed
    assert all(c["guidance"] for c in detail["quality_report"]["checks"] if c["status"] == "fail")
    assert client.get("/api/v1/projects").json() == []
    assert geometry_calls == []


def test_non_image_and_wrong_type_are_rejected(client):
    assert upload(client, b"not an image").status_code == 422
    assert upload(client, b"%PDF", content_type="application/pdf").status_code == 415


def test_list_rename_and_delete(client):
    first = upload(client, make_photo(), name="First").json()
    upload(client, make_photo(), name="Second")

    listing = client.get("/api/v1/projects").json()
    assert [p["name"] for p in listing] == ["Second", "First"]
    assert listing[0]["segment_count"] == 2
    assert listing[0]["thumbnail_url"]

    renamed = client.patch(f"/api/v1/projects/{first['id']}", json={"name": "Front elevation"})
    assert renamed.json()["name"] == "Front elevation"

    assert client.delete(f"/api/v1/projects/{first['id']}").status_code == 204
    assert client.get(f"/api/v1/projects/{first['id']}").status_code == 404
    assert len(client.get("/api/v1/projects").json()) == 1


def test_projects_are_private_to_their_owner(client):
    created = upload(client, make_photo()).json()
    job_id = created["latest_job"]["id"]

    client.as_user(USER_B)
    assert client.get("/api/v1/projects").json() == []
    assert client.get(f"/api/v1/projects/{created['id']}").status_code == 404
    assert client.get(f"/api/v1/jobs/{job_id}").status_code == 404
    assert client.delete(f"/api/v1/projects/{created['id']}").status_code == 404
    assert client.post(f"/api/v1/projects/{created['id']}/analyze").status_code == 404


def test_reanalysis_replaces_auto_segments(client, geometry_calls):
    created = upload(client, make_photo()).json()

    response = client.post(f"/api/v1/projects/{created['id']}/analyze")
    assert response.status_code == 202
    job = client.get(f"/api/v1/jobs/{response.json()['id']}").json()
    assert job["status"] == "succeeded"

    detail = client.get(f"/api/v1/projects/{created['id']}").json()
    assert len(detail["segments"]) == 2
    assert len(geometry_calls) == 2


def test_geometry_failure_marks_job_failed(client, monkeypatch):
    from app.services import ai_geometry

    async def unavailable(image: bytes, filename: str = "working.jpg") -> dict:
        raise ai_geometry.AIGeometryError("The analysis service is not reachable right now.")

    monkeypatch.setattr(ai_geometry, "analyze_image", unavailable)
    created = upload(client, make_photo()).json()

    detail = client.get(f"/api/v1/projects/{created['id']}").json()
    assert detail["status"] == "failed"
    assert detail["latest_job"]["status"] == "failed"
    assert detail["latest_job"]["error"] == "The analysis service is not reachable right now."


def test_timestamps_are_timezone_aware(client):
    created = upload(client, make_photo()).json()

    detail = client.get(f"/api/v1/projects/{created['id']}").json()

    assert created["created_at"].endswith(("Z", "+00:00"))
    assert detail["latest_job"]["finished_at"].endswith(("Z", "+00:00"))
