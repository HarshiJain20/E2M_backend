import asyncio

from app.api.routes.health import api_health_check
from app.main import app, health_check

import httpx

REAL_ASYNC_CLIENT = httpx.AsyncClient


def test_root_health_endpoint_reports_service_status() -> None:
    response = asyncio.run(health_check())

    assert response["status"] == "ok"


def test_versioned_health_endpoint_is_available() -> None:
    registered_paths = {route.path for route in app.routes}
    response = asyncio.run(api_health_check())

    assert "/api/v1/health" in registered_paths
    assert response["service"] == "E2M Backend"


def _ai_status(monkeypatch, handler) -> str:
    import httpx

    from app.services import ai_geometry

    monkeypatch.setattr(ai_geometry.httpx, "AsyncClient",
                        lambda **kw: REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setitem(ai_geometry._status_cache, "value", None)
    return asyncio.run(ai_geometry.service_status())


def test_ai_status_online_when_the_service_answers(monkeypatch) -> None:
    import httpx

    seen = {}

    def handler(request):
        seen.update(request.headers)
        return httpx.Response(200, json={"status": "ok"})

    assert _ai_status(monkeypatch, handler) == "online"
    assert seen["ngrok-skip-browser-warning"] == "1"


def test_ai_status_offline_when_unreachable_or_tunnel_has_no_service(monkeypatch) -> None:
    import httpx

    def down(request):
        raise httpx.ConnectError("refused")

    assert _ai_status(monkeypatch, down) == "offline"
    # ngrok answers for a stopped notebook with its own error page.
    assert _ai_status(monkeypatch, lambda r: httpx.Response(404, text="ERR_NGROK_3200")) == "offline"


def test_ai_status_endpoint_is_public(client) -> None:
    from app.services import ai_geometry

    ai_geometry._status_cache.update(value="offline", at=__import__("time").monotonic())
    assert client.get("/api/v1/health/ai").json() == {"status": "offline"}
