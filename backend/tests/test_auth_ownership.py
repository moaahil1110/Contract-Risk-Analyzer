"""
Priority 4: Auth and ownership hardening tests.
Covers authentication, authorization, ownership enforcement, and production fail-closed behavior.
"""

import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric import ec

from api.middleware import auth as auth_module
from api.routes import upload, analyse, export, history
from api.middleware.auth import require_user, validate_security_config_at_startup
from main import app


_TEST_USER = {"id": "11111111-1111-4111-8111-111111111111", "email": "test@example.com"}
_OTHER_USER = {"id": "22222222-2222-4222-8222-222222222222", "email": "other@example.com"}


@contextmanager
def _authenticated_as(user_id=_TEST_USER["id"], email="test@example.com"):
    app.dependency_overrides[require_user] = lambda: {"id": user_id, "email": email}
    try:
        yield
    finally:
        app.dependency_overrides.pop(require_user, None)


def _mock_weasyprint(monkeypatch):
    class FakeHTML:
        def __init__(self, string):
            self.string = string
        def write_pdf(self):
            return self.string.encode("utf-8")

    fake_mod = type("weasyprint", (), {"HTML": FakeHTML})()
    monkeypatch.setitem(sys.modules, "weasyprint", fake_mod)


def _set_dev_mode(monkeypatch, enabled: bool):
    """Set DEV_MODE consistently across all modules that imported it."""
    val = enabled
    monkeypatch.setattr(auth_module, "DEV_MODE", val)
    monkeypatch.setattr(upload, "DEV_MODE", val)
    monkeypatch.setattr(analyse, "DEV_MODE", val)
    monkeypatch.setattr(export, "DEV_MODE", val)
    monkeypatch.setattr(history, "DEV_MODE", val)


def _set_production_secrets(monkeypatch):
    """Set fake production secrets in auth module."""
    monkeypatch.setattr(auth_module, "SUPABASE_URL", "http://localhost")
    monkeypatch.setattr(auth_module, "SUPABASE_SERVICE_KEY", "test-service-key")
    monkeypatch.setattr(auth_module, "SUPABASE_JWT_SECRET", "test-jwt-secret")


# =============================================================================
# Authentication tests
# =============================================================================

def test_upload_returns_401_when_unauthenticated_in_production(monkeypatch):
    _set_dev_mode(monkeypatch, enabled=False)
    upload.contract_store.clear()

    client = TestClient(app)
    response = client.post(
        "/api/v1/upload",
        files={"file": ("sample.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
        data={"contract_type": "nda"},
    )
    assert response.status_code == 401
    assert "Authentication" in response.json()["detail"] or "token" in response.json()["detail"].lower()


def test_analyse_returns_401_when_unauthenticated_in_production(monkeypatch):
    _set_dev_mode(monkeypatch, enabled=False)
    analyse.analysis_results.clear()
    upload.contract_store.clear()
    upload.contract_store["c-123"] = {
        "id": "c-123",
        "user_id": None,
        "filename": "test.pdf",
        "contract_type": "nda",
        "status": "uploaded",
    }

    client = TestClient(app)
    response = client.post("/api/v1/analyse/c-123")
    assert response.status_code == 401


def test_analysis_status_returns_401_when_unauthenticated_in_production(monkeypatch):
    _set_dev_mode(monkeypatch, enabled=False)
    upload.contract_store.clear()
    upload.contract_store["c-123"] = {
        "id": "c-123",
        "user_id": None,
        "filename": "test.pdf",
        "contract_type": "nda",
        "status": "uploaded",
    }

    client = TestClient(app)
    response = client.get("/api/v1/analyse/c-123/status")
    assert response.status_code == 401


def test_analysis_results_return_401_when_unauthenticated_in_production(monkeypatch):
    _set_dev_mode(monkeypatch, enabled=False)
    upload.contract_store.clear()
    upload.contract_store["c-123"] = {
        "id": "c-123",
        "user_id": None,
        "filename": "test.pdf",
        "contract_type": "nda",
        "status": "uploaded",
    }

    client = TestClient(app)
    response = client.get("/api/v1/analyse/c-123")
    assert response.status_code == 401


def test_clause_detail_returns_401_when_unauthenticated_in_production(monkeypatch):
    _set_dev_mode(monkeypatch, enabled=False)
    upload.contract_store.clear()
    upload.contract_store["c-123"] = {
        "id": "c-123",
        "user_id": None,
        "filename": "test.pdf",
        "contract_type": "nda",
        "status": "complete",
    }
    analyse.analysis_results["c-123"] = {
        "health": {"score": 50, "grade": "C", "label": "Average"},
        "clauses": [{"clause_title": "Test", "risk_level": "low"}],
    }

    client = TestClient(app)
    response = client.get("/api/v1/analyse/c-123/clauses/0")
    assert response.status_code == 401


def test_export_returns_401_when_unauthenticated_in_production(monkeypatch):
    _set_dev_mode(monkeypatch, enabled=False)
    upload.contract_store.clear()
    upload.contract_store["c-123"] = {
        "id": "c-123",
        "user_id": None,
        "filename": "test.pdf",
        "contract_type": "nda",
        "status": "complete",
        "health": {"score": 50, "grade": "C", "label": "Average"},
        "analysis": [{"clause_title": "Test", "risk_level": "low"}],
    }
    analyse.analysis_results["c-123"] = {
        "health": {"score": 50, "grade": "C", "label": "Average"},
        "clauses": [{"clause_title": "Test", "risk_level": "low"}],
    }

    client = TestClient(app)
    response = client.get("/api/v1/export/c-123")
    assert response.status_code == 401


def test_missing_jwt_secret_in_production_fails_closed(monkeypatch):
    _set_dev_mode(monkeypatch, enabled=False)
    monkeypatch.setattr(auth_module, "SUPABASE_URL", None)
    monkeypatch.setattr(auth_module, "SUPABASE_SERVICE_KEY", "test-service-key")
    monkeypatch.setattr(auth_module, "SUPABASE_JWT_SECRET", None)

    with pytest.raises(RuntimeError) as exc_info:
        validate_security_config_at_startup()

    assert "SUPABASE_URL" in str(exc_info.value)


def _jwt_payload(user_id=_TEST_USER["id"], email="test@example.com"):
    now = datetime.now(timezone.utc)
    return {
        "sub": user_id,
        "email": email,
        "role": "authenticated",
        "aud": "authenticated",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
    }


def test_hs256_supabase_jwt_is_accepted(monkeypatch):
    _set_dev_mode(monkeypatch, enabled=False)
    _set_production_secrets(monkeypatch)
    token = jwt.encode(_jwt_payload(), "test-jwt-secret", algorithm="HS256")

    user = auth_module.extract_user_from_token(token)

    assert user["id"] == _TEST_USER["id"]
    assert user["email"] == _TEST_USER["email"]


def test_es256_supabase_jwt_is_accepted_via_jwks(monkeypatch):
    _set_dev_mode(monkeypatch, enabled=False)
    _set_production_secrets(monkeypatch)
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    token = jwt.encode(_jwt_payload(), private_key, algorithm="ES256", headers={"kid": "test-key"})

    class FakeSigningKey:
        key = public_key

    class FakeJwksClient:
        def get_signing_key_from_jwt(self, _token):
            return FakeSigningKey()

    monkeypatch.setattr(auth_module, "_jwks_client", FakeJwksClient())

    user = auth_module.extract_user_from_token(token)

    assert user["id"] == _TEST_USER["id"]
    assert user["role"] == "authenticated"


def test_invalid_jwt_returns_401(monkeypatch):
    _set_dev_mode(monkeypatch, enabled=False)
    _set_production_secrets(monkeypatch)
    upload.contract_store.clear()
    upload.contract_store["c-123"] = {
        "id": "c-123",
        "user_id": _TEST_USER["id"],
        "filename": "test.pdf",
        "contract_type": "nda",
        "status": "uploaded",
    }

    client = TestClient(app)
    response = client.get(
        "/api/v1/analyse/c-123",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 401


# =============================================================================
# Ownership tests
# =============================================================================

def test_owner_can_start_analysis_and_poll_status(monkeypatch):
    _set_dev_mode(monkeypatch, enabled=False)
    monkeypatch.setattr(analyse, "is_supabase_configured", lambda: False)
    monkeypatch.setattr(analyse, "enqueue_contract_analysis", lambda contract_id, task_id=None: "task-123")

    async def _false_async(*_args, **_kwargs):
        return False

    monkeypatch.setattr(analyse, "get_active_analysis_job_for_contract", _false_async)
    monkeypatch.setattr(analyse, "create_analysis_job", lambda *_args, **_kwargs: _false_async())
    monkeypatch.setattr(analyse, "update_contract_progress", _false_async)

    contract_id = "owner-test-123"
    upload.contract_store.clear()
    analyse.analysis_results.clear()
    upload.contract_store[contract_id] = {
        "id": contract_id,
        "user_id": _TEST_USER["id"],
        "filename": "EC.pdf",
        "contract_type": "employment",
        "status": "uploaded",
        "storage_path": "local:///tmp/ec.pdf",
        "progress_percent": 0,
        "status_message": "Uploaded",
        "clauses": None,
    }

    with _authenticated_as(_TEST_USER["id"], _TEST_USER["email"]):
        client = TestClient(app)
        start = client.post(f"/api/v1/analyse/{contract_id}")
        assert start.status_code == 200
        assert start.json()["status"] == "queued"

        status = client.get(f"/api/v1/analyse/{contract_id}/status")
        assert status.status_code == 200
        assert status.json()["status"] == "queued"


def test_different_user_gets_404_for_analysis(monkeypatch):
    _set_dev_mode(monkeypatch, enabled=False)
    monkeypatch.setattr(analyse, "is_supabase_configured", lambda: False)
    monkeypatch.setattr(export, "is_supabase_configured", lambda: False)

    contract_id = "cross-user-test-123"
    upload.contract_store.clear()
    analyse.analysis_results.clear()
    upload.contract_store[contract_id] = {
        "id": contract_id,
        "user_id": _TEST_USER["id"],
        "filename": "EC.pdf",
        "contract_type": "employment",
        "status": "uploaded",
    }

    with _authenticated_as(_OTHER_USER["id"], _OTHER_USER["email"]):
        client = TestClient(app)
        response = client.post(f"/api/v1/analyse/{contract_id}")
        assert response.status_code == 404

        response = client.get(f"/api/v1/analyse/{contract_id}/status")
        assert response.status_code == 404

        response = client.get(f"/api/v1/analyse/{contract_id}")
        assert response.status_code == 404

        response = client.get(f"/api/v1/analyse/{contract_id}/clauses/0")
        assert response.status_code == 404

        response = client.get(f"/api/v1/export/{contract_id}")
        assert response.status_code == 404


def test_owner_can_fetch_results_and_clause_detail_and_export(monkeypatch):
    _set_dev_mode(monkeypatch, enabled=False)
    monkeypatch.setattr(analyse, "is_supabase_configured", lambda: False)
    monkeypatch.setattr(export, "is_supabase_configured", lambda: False)
    _mock_weasyprint(monkeypatch)

    contract_id = "owner-detail-test"
    upload.contract_store.clear()
    analyse.analysis_results.clear()
    upload.contract_store[contract_id] = {
        "id": contract_id,
        "user_id": _TEST_USER["id"],
        "filename": "NDA.pdf",
        "contract_type": "nda",
        "selected_contract_type": "nda",
        "status": "complete",
        "health": {
            "score": 80,
            "grade": "B",
            "label": "Good",
            "risk_counts": {"high": 0, "medium": 1, "low": 2},
            "total_clauses": 3,
            "unknown_count": 0,
            "failed_clause_count": 0,
            "scored_clause_count": 3,
        },
        "analysis": [
            {"clause_title": "Clause 1", "risk_level": "low", "original_text": "text"},
            {"clause_title": "Clause 2", "risk_level": "medium", "original_text": "text"},
            {"clause_title": "Clause 3", "risk_level": "low", "original_text": "text"},
        ],
    }
    analyse.analysis_results[contract_id] = {
        "health": upload.contract_store[contract_id]["health"],
        "clauses": upload.contract_store[contract_id]["analysis"],
    }

    with _authenticated_as(_TEST_USER["id"], _TEST_USER["email"]):
        client = TestClient(app)

        result = client.get(f"/api/v1/analyse/{contract_id}")
        assert result.status_code == 200
        assert result.json()["status"] == "complete"

        clause = client.get(f"/api/v1/analyse/{contract_id}/clauses/1")
        assert clause.status_code == 200
        assert clause.json()["risk_level"] == "medium"

        export_resp = client.get(f"/api/v1/export/{contract_id}")
        assert export_resp.status_code == 200
        assert export_resp.headers["content-type"] == "application/pdf"


def test_analysis_routes_fail_closed_in_production_when_supabase_errors(monkeypatch):
    _set_dev_mode(monkeypatch, enabled=False)
    monkeypatch.setattr(analyse, "is_supabase_configured", lambda: True)

    async def _raise_error(*_args, **_kwargs):
        raise RuntimeError("Simulated database failure")

    monkeypatch.setattr(analyse, "get_contract_for_user", _raise_error)
    monkeypatch.setattr(analyse, "get_contract_with_clauses_for_user", _raise_error)

    with _authenticated_as(_TEST_USER["id"], _TEST_USER["email"]):
        client = TestClient(app)
        assert client.post("/api/v1/analyse/c-123").status_code == 503
        assert client.get("/api/v1/analyse/c-123/status").status_code == 503
        assert client.get("/api/v1/analyse/c-123").status_code == 503
        assert client.get("/api/v1/analyse/c-123/clauses/0").status_code == 503


def test_export_fails_closed_in_production_when_supabase_errors(monkeypatch):
    _set_dev_mode(monkeypatch, enabled=False)
    monkeypatch.setattr(export, "is_supabase_configured", lambda: True)

    async def _raise_error(*_args, **_kwargs):
        raise RuntimeError("Simulated database failure")

    monkeypatch.setattr(export, "get_contract_with_clauses_for_user", _raise_error)

    with _authenticated_as(_TEST_USER["id"], _TEST_USER["email"]):
        client = TestClient(app)
        response = client.get("/api/v1/export/c-123")
        assert response.status_code == 503


# =============================================================================
# Upload ownership and debug endpoint tests
# =============================================================================

def test_authenticated_upload_stores_real_user_id(monkeypatch):
    async def fake_save(**_kwargs):
        return "local:///tmp/original.pdf"

    async def fake_create_contract(**kwargs):
        return {
            "id": kwargs["contract_id"],
            "storage_path": kwargs["storage_path"],
            "user_id": kwargs["user_id"],
        }

    monkeypatch.setattr(upload, "save_contract_file", fake_save)
    monkeypatch.setattr(upload, "create_contract", fake_create_contract)
    monkeypatch.setattr(upload, "is_supabase_configured", lambda: False)
    monkeypatch.setattr(upload, "_validate_pdf_bytes", lambda _bytes: None)

    upload.contract_store.clear()

    with _authenticated_as("real-user-99", "real@example.com"):
        client = TestClient(app)
        response = client.post(
            "/api/v1/upload",
            files={"file": ("sample.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
            data={"contract_type": "nda"},
        )
        assert response.status_code == 200
        record = upload.contract_store[response.json()["contract_id"]]
        assert record["user_id"] == "real-user-99"


def test_upload_debug_unavailable_in_production(monkeypatch):
    _set_dev_mode(monkeypatch, enabled=False)
    upload.contract_store.clear()
    upload.contract_store["c-123"] = {
        "id": "c-123",
        "user_id": _TEST_USER["id"],
        "filename": "test.pdf",
        "contract_type": "nda",
        "status": "uploaded",
        "text": None,
        "clauses": None,
    }

    with _authenticated_as(_TEST_USER["id"], _TEST_USER["email"]):
        client = TestClient(app)
        response = client.get("/api/v1/upload-debug/c-123")
        assert response.status_code == 404


def test_upload_debug_works_in_dev_for_owner(monkeypatch):
    _set_dev_mode(monkeypatch, enabled=True)
    upload.contract_store.clear()
    upload.contract_store["c-123"] = {
        "id": "c-123",
        "user_id": _TEST_USER["id"],
        "filename": "test.pdf",
        "contract_type": "nda",
        "status": "uploaded",
        "text": "Sample contract text here.",
        "clauses": ["Clause one text.", "Clause two text."],
    }

    with _authenticated_as(_TEST_USER["id"], _TEST_USER["email"]):
        client = TestClient(app)
        response = client.get("/api/v1/upload-debug/c-123")
        assert response.status_code == 200
        assert response.json()["contract_id"] == "c-123"


def test_upload_debug_returns_404_for_non_owner_in_dev(monkeypatch):
    _set_dev_mode(monkeypatch, enabled=True)
    upload.contract_store.clear()
    upload.contract_store["c-123"] = {
        "id": "c-123",
        "user_id": _TEST_USER["id"],
        "filename": "test.pdf",
        "contract_type": "nda",
        "status": "uploaded",
        "text": None,
        "clauses": None,
    }

    with _authenticated_as(_OTHER_USER["id"], _OTHER_USER["email"]):
        client = TestClient(app)
        response = client.get("/api/v1/upload-debug/c-123")
        assert response.status_code == 404


# =============================================================================
# History fail-closed tests
# =============================================================================

def test_history_fails_closed_in_production_when_supabase_errors(monkeypatch):
    _set_dev_mode(monkeypatch, enabled=False)
    monkeypatch.setattr(history, "is_supabase_configured", lambda: True)

    async def _raise_error(*_args, **_kwargs):
        raise RuntimeError("Simulated database failure")

    monkeypatch.setattr(history, "get_user_contracts", _raise_error)

    with _authenticated_as(_TEST_USER["id"], _TEST_USER["email"]):
        client = TestClient(app)
        response = client.get("/api/v1/history")
        assert response.status_code == 503
        assert "Database service unavailable" in response.json()["detail"]


def test_history_detail_fails_closed_in_production_when_supabase_errors(monkeypatch):
    _set_dev_mode(monkeypatch, enabled=False)
    monkeypatch.setattr(history, "is_supabase_configured", lambda: True)

    async def _raise_error(*_args, **_kwargs):
        raise RuntimeError("Simulated database failure")

    monkeypatch.setattr(history, "get_contract_with_clauses_for_user", _raise_error)

    with _authenticated_as(_TEST_USER["id"], _TEST_USER["email"]):
        client = TestClient(app)
        response = client.get("/api/v1/history/c-123")
        assert response.status_code == 503


def test_history_stats_fails_closed_in_production_when_supabase_errors(monkeypatch):
    _set_dev_mode(monkeypatch, enabled=False)
    monkeypatch.setattr(history, "is_supabase_configured", lambda: True)

    async def _raise_error(*_args, **_kwargs):
        raise RuntimeError("Simulated database failure")

    monkeypatch.setattr(history, "get_user_contracts", _raise_error)

    with _authenticated_as(_TEST_USER["id"], _TEST_USER["email"]):
        client = TestClient(app)
        response = client.get("/api/v1/history/stats")
        assert response.status_code == 503
