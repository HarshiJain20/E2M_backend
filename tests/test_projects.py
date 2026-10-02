from tests.conftest import USER_B, make_photo


def upload(client, photos, name="My house", elevations=None):
    """photos: list of image bytes."""
    files = [("images", (f"house{i}.jpg", data, "image/jpeg")) for i, data in enumerate(photos)]
    form = {"name": name} if name is not None else {}
    if elevations:
        form["elevations"] = elevations
    return client.post("/api/v1/projects", files=files, data=form)


def add_photos(client, project_id, photos, elevations=None):
    files = [("images", (f"more{i}.jpg", data, "image/jpeg")) for i, data in enumerate(photos)]
    return client.post(f"/api/v1/projects/{project_id}/photos", files=files,
                       data={"elevations": elevations} if elevations else {})


def detail(client, project_id):
    return client.get(f"/api/v1/projects/{project_id}").json()


def by_elevation(project):
    return {p["elevation"]: p for p in project["photos"]}


def test_single_photo_project_is_created_and_analysed(client, geometry_calls):
    response = upload(client, [make_photo()])

    assert response.status_code == 201
    project = detail(client, response.json()["id"])
    assert project["name"] == "My house"
    assert project["status"] == "review"
    assert project["photo_count"] == 1
    photo = project["photos"][0]
    assert photo["elevation"] == "front" and photo["is_primary"] is True
    assert photo["latest_job"]["status"] == "succeeded"
    assert {s["label"] for s in photo["segments"]} == {"wall", "railing"}
    assert photo["image_url"].startswith("/api/v1/media/")
    assert len(geometry_calls) == 1


def test_several_photos_get_sides_in_order_and_each_is_analysed(client, geometry_calls):
    project = detail(client, upload(client, [make_photo(), make_photo(), make_photo()]).json()["id"])

    assert [p["elevation"] for p in project["photos"]] == ["front", "left", "right"]
    assert all(p["is_primary"] for p in project["photos"])
    assert len(geometry_calls) == 3
    totals = {t["label"]: t for t in project["totals"]}
    assert totals["wall"]["total"] == 42.5 * 3  # one wall per side
    assert totals["railing"]["measure_type"] == "length"


def test_requested_sides_are_used(client):
    project = upload(client, [make_photo(), make_photo()], elevations=["rear", "left"]).json()

    assert [p["elevation"] for p in project["photos"]] == ["rear", "left"]


def test_unknown_side_is_rejected(client):
    assert upload(client, [make_photo()], elevations=["roof"]).status_code == 422


def test_two_photos_of_same_side_are_not_double_counted(client):
    project = detail(client, upload(client, [make_photo(), make_photo()], elevations=["front", "front"]).json()["id"])

    assert [p["is_primary"] for p in project["photos"]] == [True, False]
    wall = next(t for t in project["totals"] if t["label"] == "wall")
    assert wall["total"] == 42.5 and wall["count"] == 1


def test_one_bad_photo_rejects_the_whole_upload_with_per_photo_guidance(client, geometry_calls):
    response = upload(client, [make_photo(), make_photo(400, 300, flat=True)])

    assert response.status_code == 422
    body = response.json()["detail"]
    assert body["code"] == "images_unusable"
    assert body["message"].startswith("1 of 2 photos")
    [problem] = body["photos"]
    assert problem["index"] == 1
    failed = {c["id"] for c in problem["quality_report"]["checks"] if c["status"] == "fail"}
    assert {"resolution", "contrast"} <= failed
    assert client.get("/api/v1/projects").json() == []  # nothing was created
    assert geometry_calls == []


def test_non_image_and_wrong_type_are_reported_per_photo(client):
    files = [("images", ("a.txt", b"not an image", "image/jpeg")), ("images", ("b.pdf", b"%PDF", "application/pdf"))]
    body = client.post("/api/v1/projects", files=files).json()["detail"]

    assert [p["index"] for p in body["photos"]] == [0, 1]
    assert "JPG, PNG or WebP" in body["photos"][1]["message"]


def test_adding_photos_later_fills_next_free_side(client, geometry_calls):
    project_id = upload(client, [make_photo()]).json()["id"]

    response = add_photos(client, project_id, [make_photo(), make_photo()])

    assert response.status_code == 201
    assert [p["elevation"] for p in detail(client, project_id)["photos"]] == ["front", "left", "right"]
    assert len(geometry_calls) == 3


def test_photo_limit(client):
    project_id = upload(client, [make_photo()] * 6).json()["id"]

    response = add_photos(client, project_id, [make_photo()] * 3)

    assert response.status_code == 422
    assert "up to 8 photos" in response.json()["detail"]


def test_choosing_the_counted_photo_for_a_side(client):
    project = upload(client, [make_photo(), make_photo()], elevations=["front", "front"]).json()
    second = project["photos"][1]["id"]

    updated = client.patch(f"/api/v1/photos/{second}", json={"is_primary": True}).json()

    assert [p["is_primary"] for p in updated["photos"]] == [False, True]


def test_moving_a_photo_to_another_side_keeps_one_primary_per_side(client):
    project = upload(client, [make_photo(), make_photo()], elevations=["front", "front"]).json()
    first, second = (p["id"] for p in project["photos"])

    updated = client.patch(f"/api/v1/photos/{first}", json={"elevation": "rear"}).json()

    sides = by_elevation(updated)
    assert sides["rear"]["id"] == first and sides["rear"]["is_primary"]
    assert sides["front"]["id"] == second and sides["front"]["is_primary"]  # promoted


def test_deleting_primary_promotes_another_photo_of_that_side(client):
    project = upload(client, [make_photo(), make_photo()], elevations=["front", "front"]).json()
    first, second = (p["id"] for p in project["photos"])

    updated = client.delete(f"/api/v1/photos/{first}").json()

    assert [(p["id"], p["is_primary"]) for p in updated["photos"]] == [(second, True)]


def test_last_photo_cannot_be_deleted(client):
    project = upload(client, [make_photo()]).json()

    assert client.delete(f"/api/v1/photos/{project['photos'][0]['id']}").status_code == 409


def test_list_rename_and_delete(client):
    first = upload(client, [make_photo()], name="First").json()
    upload(client, [make_photo(), make_photo()], name="Second")

    listing = client.get("/api/v1/projects").json()
    assert [p["name"] for p in listing] == ["Second", "First"]
    assert listing[0]["photo_count"] == 2 and listing[0]["segment_count"] == 4
    assert listing[0]["thumbnail_url"] and listing[0]["status"] == "review"

    renamed = client.patch(f"/api/v1/projects/{first['id']}", json={"name": "Front elevation"})
    assert renamed.json()["name"] == "Front elevation"

    assert client.delete(f"/api/v1/projects/{first['id']}").status_code == 204
    assert client.get(f"/api/v1/projects/{first['id']}").status_code == 404
    assert len(client.get("/api/v1/projects").json()) == 1


def test_default_name_when_blank(client):
    assert upload(client, [make_photo()], name="  ").json()["name"].startswith("Exterior project")


def test_large_upload_is_downscaled_for_processing(client):
    photo = upload(client, [make_photo(3000, 2000)]).json()["photos"][0]

    assert max(photo["image_width"], photo["image_height"]) == 2048
    assert photo["image_meta"]["original_width"] == 3000


def test_projects_and_photos_are_private_to_their_owner(client):
    project = upload(client, [make_photo()]).json()
    photo_id = project["photos"][0]["id"]
    job_id = detail(client, project["id"])["photos"][0]["latest_job"]["id"]

    client.as_user(USER_B)
    assert client.get("/api/v1/projects").json() == []
    assert client.get(f"/api/v1/projects/{project['id']}").status_code == 404
    assert add_photos(client, project["id"], [make_photo()]).status_code == 404
    assert client.patch(f"/api/v1/photos/{photo_id}", json={"elevation": "rear"}).status_code == 404
    assert client.delete(f"/api/v1/photos/{photo_id}").status_code == 404
    assert client.post(f"/api/v1/photos/{photo_id}/analyze").status_code == 404
    assert client.get(f"/api/v1/jobs/{job_id}").status_code == 404


def test_reanalysing_a_photo_replaces_its_segments(client, geometry_calls):
    project = upload(client, [make_photo(), make_photo()]).json()
    photo_id = project["photos"][0]["id"]

    response = client.post(f"/api/v1/photos/{photo_id}/analyze")

    assert response.status_code == 202
    assert client.get(f"/api/v1/jobs/{response.json()['id']}").json()["status"] == "succeeded"
    assert [len(p["segments"]) for p in detail(client, project["id"])["photos"]] == [2, 2]
    assert len(geometry_calls) == 3


def test_geometry_failure_marks_photo_failed(client, monkeypatch):
    from app.services import ai_geometry

    async def unavailable(image: bytes, filename: str = "working.jpg") -> dict:
        raise ai_geometry.AIGeometryError("The analysis service is not reachable right now.")

    monkeypatch.setattr(ai_geometry, "analyze_image", unavailable)
    project = detail(client, upload(client, [make_photo()]).json()["id"])

    assert project["status"] == "failed"
    photo = project["photos"][0]
    assert photo["status"] == "failed"
    assert photo["latest_job"]["error"] == "The analysis service is not reachable right now."


def test_timestamps_are_timezone_aware(client):
    project = detail(client, upload(client, [make_photo()]).json()["id"])

    assert project["created_at"].endswith(("Z", "+00:00"))
    assert project["photos"][0]["latest_job"]["finished_at"].endswith(("Z", "+00:00"))
