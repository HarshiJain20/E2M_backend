"""The Supabase repository must act as the user and build correct Data API requests."""
import asyncio
import json

import httpx
import pytest

from app.core.config import Settings
from app.repositories.base import RepositoryError
from app.repositories.supabase import SupabaseRepository
from app.services.storage import SupabaseStorage

SETTINGS = Settings.model_validate({
    "supabase": {"url": "https://ref.supabase.co", "publishable_key": "sb_publishable_test"},
})


def recorder(responder):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return responder(request)

    return calls, httpx.MockTransport(handler)


def test_requests_carry_publishable_key_and_user_token():
    calls, transport = recorder(lambda r: httpx.Response(200, json=[]))
    repo = SupabaseRepository(SETTINGS, "user-jwt", transport=transport)

    asyncio.run(repo.list_projects())

    request = calls[0]
    assert request.headers["apikey"] == "sb_publishable_test"
    assert request.headers["authorization"] == "Bearer user-jwt"
    assert request.url.path == "/rest/v1/projects"
    assert request.url.params["select"].startswith("*,photos(")
    assert request.url.params["order"] == "updated_at.desc"


def test_list_flattens_segment_counts():
    rows = [{"id": "p1", "segments": [{"count": 4}]}, {"id": "p2", "segments": []}]
    _, transport = recorder(lambda r: httpx.Response(200, json=rows))

    projects = asyncio.run(SupabaseRepository(SETTINGS, "t", transport=transport).list_projects())

    assert [p["segment_count"] for p in projects] == [4, 0]
    assert "segments" not in projects[0]


def test_get_project_embeds_photos_with_latest_job_and_segments():
    row = {"id": "p1", "photos": [{"id": "ph1", "jobs": [{"id": "j2"}]}, {"id": "ph2", "jobs": []}],
           "segments": [{"id": "s1"}],
           "design_variants": [{"id": "v1", "name": "Design A", "segment_materials": [{"segment_id": "s1"}]}]}
    calls, transport = recorder(lambda r: httpx.Response(200, json=[row]))

    project = asyncio.run(SupabaseRepository(SETTINGS, "t", transport=transport).get_project("p1"))

    params = calls[0].url.params
    assert params["id"] == "eq.p1"
    assert params["select"] == "*,photos(*,jobs(*)),segments(*),design_variants(*,segment_materials(*))"
    assert params["photos.jobs.order"] == "created_at.desc" and params["photos.jobs.limit"] == "1"
    assert [p["latest_job"] for p in project["photos"]] == [{"id": "j2"}, None]
    assert project["segments"] == [{"id": "s1"}]
    assert project["variants"] == [{"id": "v1", "name": "Design A", "assignments": [{"segment_id": "s1"}]}]


def test_project_hidden_by_rls_is_none():
    _, transport = recorder(lambda r: httpx.Response(200, json=[]))
    assert asyncio.run(SupabaseRepository(SETTINGS, "t", transport=transport).get_project("other")) is None


def test_replace_auto_segments_deletes_then_inserts():
    calls, transport = recorder(lambda r: httpx.Response(201 if r.method == "POST" else 204))

    asyncio.run(SupabaseRepository(SETTINGS, "t", transport=transport)
                .replace_auto_segments("ph1", [{"label": "wall"}]))

    assert [c.method for c in calls] == ["DELETE", "POST"]
    assert calls[0].url.params["photo_id"] == "eq.ph1" and calls[0].url.params["source"] == "eq.auto"
    assert json.loads(calls[1].content) == [{"label": "wall"}]


def test_errors_keep_status_code():
    _, transport = recorder(lambda r: httpx.Response(401, json={"message": "JWT expired"}))

    with pytest.raises(RepositoryError) as error:
        asyncio.run(SupabaseRepository(SETTINGS, "t", transport=transport).list_projects())

    assert error.value.status_code == 401 and "JWT expired" in str(error.value)


def test_missing_table_code_is_kept():
    body = {"code": "PGRST205", "message": "Could not find the table 'public.projects' in the schema cache"}
    _, transport = recorder(lambda r: httpx.Response(404, json=body))

    with pytest.raises(RepositoryError) as error:
        asyncio.run(SupabaseRepository(SETTINGS, "t", transport=transport).list_projects())

    assert error.value.code == "PGRST205"


def test_storage_signs_urls_as_the_user():
    signed = [{"path": "u/p/thumb.jpg", "signedURL": "/object/sign/project-images/u/p/thumb.jpg?token=x"}]
    calls, transport = recorder(lambda r: httpx.Response(200, json=signed))

    urls = asyncio.run(SupabaseStorage(SETTINGS, "user-jwt", transport=transport).signed_urls(["u/p/thumb.jpg"]))

    assert calls[0].headers["authorization"] == "Bearer user-jwt"
    assert urls == {"u/p/thumb.jpg": "https://ref.supabase.co/storage/v1/object/sign/project-images/u/p/thumb.jpg?token=x"}


def test_assignments_upsert_on_variant_and_segment():
    calls, transport = recorder(lambda r: httpx.Response(201))

    asyncio.run(SupabaseRepository(SETTINGS, "t", transport=transport)
                .upsert_assignments([{"variant_id": "v1", "segment_id": "s1", "material_id": "m1"}]))

    assert calls[0].url.params["on_conflict"] == "variant_id,segment_id"
    assert calls[0].headers["prefer"] == "resolution=merge-duplicates"


def test_delete_assignments_filters_by_segment_list():
    calls, transport = recorder(lambda r: httpx.Response(204))
    asyncio.run(SupabaseRepository(SETTINGS, "t", transport=transport).delete_assignments("v1", ["s1", "s2"]))
    assert calls[0].url.params["segment_id"] == "in.(s1,s2)"
