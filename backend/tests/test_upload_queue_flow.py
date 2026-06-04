from contextlib import contextmanager
from fastapi.testclient import TestClient

from api.middleware.auth import require_user
from api.routes import upload
from main import app


@contextmanager
def _authenticated_as(user_id="11111111-1111-4111-8111-111111111111", email="test@example.com"):
    app.dependency_overrides[require_user] = lambda: {"id": user_id, "email": email}
    try:
        yield
    finally:
        app.dependency_overrides.pop(require_user, None)


def test_upload_creates_uploaded_contract_without_extraction(monkeypatch):
    async def fake_save(**_kwargs):
        return "local:///tmp/original.pdf"

    async def fake_create_contract(**kwargs):
        return {
            "id": kwargs["contract_id"],
            "storage_path": kwargs["storage_path"],
        }

    monkeypatch.setattr(upload, "save_contract_file", fake_save)
    monkeypatch.setattr(upload, "create_contract", fake_create_contract)
    monkeypatch.setattr(upload, "_validate_pdf_bytes", lambda _bytes: None)

    upload.contract_store.clear()

    with _authenticated_as():
        client = TestClient(app)
        response = client.post(
            "/api/v1/upload",
            files={"file": ("sample.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
            data={"contract_type": "nda"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "uploaded"

        record = upload.contract_store[body["contract_id"]]
        assert record["status"] == "uploaded"
        assert record["storage_path"] == "local:///tmp/original.pdf"
        assert record["text"] is None
        assert record["clauses"] is None
        # Verify real user_id is stored
        assert record["user_id"] == "11111111-1111-4111-8111-111111111111"


def test_supabase_backed_upload_requires_persistable_user(monkeypatch):
    async def fake_save(**_kwargs):
        raise AssertionError("Upload should fail before storage writes")

    monkeypatch.setattr(upload, "is_supabase_configured", lambda: True)
    monkeypatch.setattr(upload, "save_contract_file", fake_save)
    monkeypatch.setattr(upload, "_validate_pdf_bytes", lambda _bytes: None)

    upload.contract_store.clear()

    with _authenticated_as(user_id="dev-user-123"):
        client = TestClient(app)
        response = client.post(
            "/api/v1/upload",
            files={"file": ("sample.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
            data={"contract_type": "nda"},
        )

        assert response.status_code == 401
        assert "sign in" in response.json()["detail"].lower()
        assert upload.contract_store == {}


def test_upload_rejects_non_pdf_bytes(monkeypatch):
    upload.contract_store.clear()

    with _authenticated_as():
        client = TestClient(app)
        response = client.post(
            "/api/v1/upload",
            files={"file": ("sample.pdf", b"not a pdf", "application/pdf")},
            data={"contract_type": "nda"},
        )

        assert response.status_code == 400
        assert "valid pdf" in response.json()["detail"].lower()
        assert upload.contract_store == {}


def test_upload_rate_limit_returns_429(monkeypatch):
    async def fake_save(**_kwargs):
        return "local:///tmp/original.pdf"

    async def fake_create_contract(**kwargs):
        return {"id": kwargs["contract_id"]}

    monkeypatch.setattr(upload, "save_contract_file", fake_save)
    monkeypatch.setattr(upload, "create_contract", fake_create_contract)
    monkeypatch.setattr(upload, "_validate_pdf_bytes", lambda _bytes: None)
    monkeypatch.setenv("RATE_LIMIT_UPLOAD_COUNT", "1")
    monkeypatch.setenv("RATE_LIMIT_UPLOAD_WINDOW_SECONDS", "3600")

    upload.contract_store.clear()

    with _authenticated_as():
        client = TestClient(app)
        first = client.post(
            "/api/v1/upload",
            files={"file": ("sample.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
            data={"contract_type": "nda"},
        )
        second = client.post(
            "/api/v1/upload",
            files={"file": ("sample.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
            data={"contract_type": "nda"},
        )

        assert first.status_code == 200
        assert second.status_code == 429
