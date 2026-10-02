import asyncio

from app.api.routes.health import api_health_check
from app.main import app, health_check


def test_root_health_endpoint_reports_service_status() -> None:
    response = asyncio.run(health_check())

    assert response["status"] == "ok"


def test_versioned_health_endpoint_is_available() -> None:
    registered_paths = {route.path for route in app.routes}
    response = asyncio.run(api_health_check())

    assert "/api/v1/health" in registered_paths
    assert response["service"] == "E2M Backend"
