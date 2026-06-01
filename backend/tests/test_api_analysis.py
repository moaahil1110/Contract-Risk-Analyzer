from fastapi.testclient import TestClient

from api.routes import analyse, export, upload
from main import app


async def _no_sleep(_seconds):
    return None


async def _successful_clause(**_kwargs):
    return {
        "clause_title": "Safe Clause",
        "risk_level": "low",
        "risk_score": 10,
        "risk_reason": "This is acceptable.",
        "plain_english": "This clause is easy to understand.",
        "key_concerns": [],
        "suggested_fix": "No change needed.",
        "analysis_status": "success",
        "retry_count": 0,
        "error_message": None,
        "provider_used": "test",
    }


async def _failed_clause(**_kwargs):
    return {
        "clause_title": "Analysis Failed",
        "risk_level": "unknown",
        "risk_score": None,
        "risk_reason": "Unable to analyze due to LLM service unavailability.",
        "plain_english": "This clause could not be analyzed.",
        "key_concerns": ["Analysis service temporarily unavailable"],
        "suggested_fix": "Please retry the analysis.",
        "analysis_status": "failed",
        "retry_count": 4,
        "error_message": "all providers failed",
        "provider_used": "fallback",
    }


def _disable_database(monkeypatch):
    monkeypatch.setattr(analyse, "is_supabase_configured", lambda: False)
    monkeypatch.setattr(export, "is_supabase_configured", lambda: False)

    async def _false_async(*_args, **_kwargs):
        return False

    monkeypatch.setattr(analyse, "update_contract_status", _false_async)
    monkeypatch.setattr(analyse, "update_contract_type_metadata", _false_async)
    monkeypatch.setattr(analyse, "save_clause_analyses_batch", _false_async)
    monkeypatch.setattr(analyse, "update_contract_results", _false_async)


def test_analysis_api_preserves_selected_type_and_returns_backend_health(monkeypatch):
    _disable_database(monkeypatch)
    monkeypatch.setattr(analyse.asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(analyse, "retrieve_benchmarks", lambda *_args, **_kwargs: [
        {
            "id": "employment_1",
            "contract_type": "employment",
            "clause_type": "standard",
            "similarity": 0.91,
            "risk_notes": "Standard clause.",
        }
    ])
    monkeypatch.setattr(analyse, "analyse_clause", _successful_clause)

    contract_id = "api-test-success"
    upload.contract_store.clear()
    analyse.analysis_results.clear()
    upload.contract_store[contract_id] = {
        "id": contract_id,
        "user_id": None,
        "filename": "EC.pdf",
        "contract_type": "employment",
        "selected_contract_type": "employment",
        "status": "clauses_extracted",
        "clauses": [
            "The employee will receive salary and benefits from the employer.",
        ],
    }

    client = TestClient(app)
    response = client.post(f"/api/v1/analyse/{contract_id}")
    assert response.status_code == 200
    assert response.json()["selected_contract_type"] == "employment"

    result = client.get(f"/api/v1/analyse/{contract_id}").json()
    assert result["contract_type"] == "employment"
    assert result["selected_contract_type"] == "employment"
    assert result["health"]["grade"] == "A"
    assert result["health"]["label"] == "Low Risk"
    assert result["health"]["scored_clause_count"] == 1
    assert result["clauses"][0]["retrieved_benchmarks"][0]["id"] == "employment_1"


def test_api_export_includes_failed_clause_count(monkeypatch):
    _disable_database(monkeypatch)
    monkeypatch.setattr(analyse.asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(analyse, "retrieve_benchmarks", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(analyse, "analyse_clause", _failed_clause)

    contract_id = "api-test-failure"
    upload.contract_store.clear()
    analyse.analysis_results.clear()
    upload.contract_store[contract_id] = {
        "id": contract_id,
        "user_id": None,
        "filename": "NDA.pdf",
        "contract_type": "nda",
        "selected_contract_type": "nda",
        "status": "clauses_extracted",
        "clauses": [
            "Confidential information must be protected by the receiving party.",
        ],
    }

    client = TestClient(app)
    assert client.post(f"/api/v1/analyse/{contract_id}").status_code == 200

    result = client.get(f"/api/v1/analyse/{contract_id}").json()
    assert result["health"]["grade"] == "N/A"
    assert result["health"]["failed_clause_count"] == 1
    assert result["clauses"][0]["risk_level"] == "unknown"

    export_response = client.get(f"/api/v1/export/{contract_id}")
    assert export_response.status_code == 200
    assert export_response.headers["content-type"] == "application/pdf"
    assert b"Failed Analyses: 1" in export_response.content
