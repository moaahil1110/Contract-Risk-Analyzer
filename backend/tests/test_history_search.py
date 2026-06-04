import pytest
from fastapi.testclient import TestClient

from api.middleware.auth import require_user
from api.routes import history
from db import queries
from main import app

_TEST_USER = {"id": "11111111-1111-4111-8111-111111111111", "email": "test@example.com"}


def _set_dev_mode(monkeypatch, enabled: bool):
    monkeypatch.setattr(history, "DEV_MODE", enabled)


def test_sanitize_ilike_pattern_escapes_special_chars():
    assert queries._sanitize_ilike_pattern("100%") == "100\\%"
    assert queries._sanitize_ilike_pattern("test_file") == "test\\_file"
    assert queries._sanitize_ilike_pattern("a\\b") == "a\\\\b"
    assert queries._sanitize_ilike_pattern("%_%") == "\\%\\_\\%"


@pytest.mark.anyio
async def test_get_user_contracts_retries_once_on_failure(monkeypatch):
    calls = []

    async def fake_once(*args, **kwargs):
        calls.append("once")
        raise RuntimeError("transient db error")

    monkeypatch.setattr(queries, "_get_user_contracts_once", fake_once)

    with pytest.raises(RuntimeError, match="transient db error"):
        await queries._get_user_contracts_with_retry("user-1")

    assert calls == ["once", "once"]


def test_history_search_returns_503_after_retry_failure_in_production(monkeypatch):
    _set_dev_mode(monkeypatch, False)
    monkeypatch.setattr(queries, "is_supabase_configured", lambda: True)

    async def fake_get_user_contracts(*args, **kwargs):
        raise RuntimeError("persistent db error")

    monkeypatch.setattr(history, "get_user_contracts", fake_get_user_contracts)

    app.dependency_overrides[require_user] = lambda: _TEST_USER
    try:
        client = TestClient(app)
        response = client.get("/api/v1/history?search=nda")

        assert response.status_code == 503
        assert "Database service unavailable" in response.json()["detail"]
    finally:
        app.dependency_overrides.pop(require_user, None)


def test_history_search_fallback_in_dev_after_failure(monkeypatch):
    _set_dev_mode(monkeypatch, True)
    monkeypatch.setattr(queries, "is_supabase_configured", lambda: True)

    async def fake_get_user_contracts(*args, **kwargs):
        raise RuntimeError("persistent db error")

    monkeypatch.setattr(history, "get_user_contracts", fake_get_user_contracts)

    # Seed in-memory contract
    from api.routes.upload import contract_store
    contract_store.clear()
    contract_store["c1"] = {
        "id": "c1",
        "user_id": "11111111-1111-4111-8111-111111111111",
        "filename": "NDA.pdf",
        "status": "complete",
        "contract_type": "nda",
        "health_grade": "B",
        "deleted_at": None,
    }

    app.dependency_overrides[require_user] = lambda: _TEST_USER
    try:
        client = TestClient(app)
        response = client.get("/api/v1/history?search=NDA")

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "memory"
        assert len(data["contracts"]) == 1
        assert data["contracts"][0]["filename"] == "NDA.pdf"
    finally:
        app.dependency_overrides.pop(require_user, None)
