from fastapi.testclient import TestClient

from api.routes import upload
from main import app


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

    upload.contract_store.clear()

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
