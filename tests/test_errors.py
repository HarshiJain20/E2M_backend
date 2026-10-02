from app.core.deps import get_repository
from app.main import app
from app.repositories.base import RepositoryError


class BrokenRepository:
    def __init__(self, status_code=None, code=None):
        self.status_code = status_code
        self.code = code

    async def list_projects(self):
        raise RepositoryError("Supabase request failed", self.status_code, self.code)


def test_unreachable_supabase_returns_503_with_message(client):
    app.dependency_overrides[get_repository] = lambda: BrokenRepository()
    response = client.get("/api/v1/projects")

    assert response.status_code == 503
    assert "database" in response.json()["detail"]


def test_rejected_token_returns_401(client):
    app.dependency_overrides[get_repository] = lambda: BrokenRepository(status_code=401)
    response = client.get("/api/v1/projects")

    assert response.status_code == 401
    assert "Sign in again" in response.json()["detail"]


def test_new_user_sees_empty_project_list(client):
    response = client.get("/api/v1/projects")

    assert response.status_code == 200
    assert response.json() == []


def test_missing_tables_tell_you_to_run_schema(client):
    app.dependency_overrides[get_repository] = lambda: BrokenRepository(status_code=404, code="PGRST205")
    response = client.get("/api/v1/projects")

    assert response.status_code == 503
    assert "supabase/schema.sql" in response.json()["detail"]
