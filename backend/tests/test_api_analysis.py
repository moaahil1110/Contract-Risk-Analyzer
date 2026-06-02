from fastapi.testclient import TestClient

from api.routes import analyse, export, upload
from services import analysis_pipeline
from services.job_queue import default_worker_concurrency, default_worker_pool
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
        "cited_benchmark_ids": ["employment_001"],
        "risk_rule_applied": "Standard low-risk employment clause.",
        "evidence_summary": "The retrieved benchmark supports a low-risk classification.",
        "benchmark_alignment": "strong",
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
        "cited_benchmark_ids": [],
        "risk_rule_applied": "",
        "evidence_summary": "No benchmark-supported analysis was produced.",
        "benchmark_alignment": "none",
    }


def _disable_database(monkeypatch):
    monkeypatch.setattr(analyse, "is_supabase_configured", lambda: False)
    monkeypatch.setattr(export, "is_supabase_configured", lambda: False)

    async def _false_async(*_args, **_kwargs):
        return False

    monkeypatch.setattr(analyse, "get_active_analysis_job", lambda *_args, **_kwargs: _false_async())
    monkeypatch.setattr(analyse, "create_analysis_job", lambda *_args, **_kwargs: _false_async())
    monkeypatch.setattr(analyse, "update_contract_progress", _false_async)


def test_analysis_api_queues_once_and_status_returns_progress(monkeypatch):
    _disable_database(monkeypatch)
    monkeypatch.setattr(analyse, "enqueue_contract_analysis", lambda contract_id, task_id=None: "task-123")

    contract_id = "api-test-queued"
    upload.contract_store.clear()
    analyse.analysis_results.clear()
    upload.contract_store[contract_id] = {
        "id": contract_id,
        "user_id": None,
        "filename": "EC.pdf",
        "contract_type": "employment",
        "selected_contract_type": "employment",
        "status": "uploaded",
        "storage_path": "local:///tmp/ec.pdf",
        "progress_percent": 0,
        "status_message": "Uploaded",
        "clauses": None,
    }

    client = TestClient(app)
    response = client.post(f"/api/v1/analyse/{contract_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "queued"
    assert response.json()["task_id"]

    status = client.get(f"/api/v1/analyse/{contract_id}/status").json()
    assert status["status"] == "queued"
    assert status["progress_percent"] == 0
    assert status["has_results"] is False

    duplicate = client.post(f"/api/v1/analyse/{contract_id}")
    assert duplicate.status_code == 200
    assert duplicate.json()["message"] == "Analysis is already queued or running"


def test_api_export_includes_failed_clause_count(monkeypatch):
    _disable_database(monkeypatch)

    contract_id = "api-test-failure"
    upload.contract_store.clear()
    analyse.analysis_results.clear()
    upload.contract_store[contract_id] = {
        "id": contract_id,
        "user_id": None,
        "filename": "NDA.pdf",
        "contract_type": "nda",
        "selected_contract_type": "nda",
        "status": "complete",
        "health": {
            "score": 0,
            "grade": "N/A",
            "label": "Analysis Incomplete",
            "risk_counts": {"high": 0, "medium": 0, "low": 0},
            "total_clauses": 1,
            "unknown_count": 1,
            "failed_clause_count": 1,
            "scored_clause_count": 0,
        },
        "analysis": [_failed_clause_result := {
            "clause_title": "Analysis Failed",
            "original_text": "Confidential information must be protected.",
            "risk_level": "unknown",
            "risk_score": None,
            "risk_reason": "Unable to analyze.",
            "plain_english": "This clause could not be analyzed.",
            "key_concerns": ["Analysis service temporarily unavailable"],
            "suggested_fix": "Please retry the analysis.",
            "analysis_status": "failed",
            "retry_count": 4,
            "error_message": "all providers failed",
            "provider_used": "fallback",
            "retrieved_benchmarks": [],
        }],
    }

    client = TestClient(app)
    result = client.get(f"/api/v1/analyse/{contract_id}").json()
    assert result["health"]["grade"] == "N/A"
    assert result["health"]["failed_clause_count"] == 1
    assert result["clauses"][0]["risk_level"] == "unknown"

    export_response = client.get(f"/api/v1/export/{contract_id}")
    assert export_response.status_code == 200
    assert export_response.headers["content-type"] == "application/pdf"
    assert b"Failed Analyses: 1" in export_response.content


def test_worker_pipeline_success_records_timings(monkeypatch):
    contract_id = "worker-success"
    upload.contract_store.clear()
    upload.contract_store[contract_id] = {
        "id": contract_id,
        "user_id": "user-1",
        "filename": "EC.pdf",
        "contract_type": "employment",
        "selected_contract_type": "employment",
        "status": "uploaded",
        "text": "Employee will receive salary and benefits.",
        "clauses": ["Employee will receive salary and benefits."],
    }

    async def _false_async(*_args, **_kwargs):
        return False

    monkeypatch.setattr(analysis_pipeline, "update_contract_progress", _false_async)
    monkeypatch.setattr(analysis_pipeline, "update_analysis_job", _false_async)
    monkeypatch.setattr(analysis_pipeline, "update_contract_type_metadata", _false_async)
    monkeypatch.setattr(analysis_pipeline, "save_clause_analyses_batch", _false_async)
    monkeypatch.setattr(analysis_pipeline, "update_contract_results", _false_async)
    monkeypatch.setattr(analysis_pipeline, "retrieve_benchmarks", lambda *_args, **_kwargs: [
        {"id": "employment_001", "benchmark_id": "employment_001", "contract_type": "employment"}
    ])
    monkeypatch.setattr(analysis_pipeline, "analyse_clause", _successful_clause)

    result = analysis_pipeline.run_contract_analysis_sync(contract_id)

    assert result["status"] == "complete"
    assert upload.contract_store[contract_id]["status"] == "complete"
    assert upload.contract_store[contract_id]["analysis"][0]["retrieval_latency_ms"] >= 0
    assert upload.contract_store[contract_id]["analysis"][0]["llm_latency_ms"] >= 0


def test_worker_pipeline_invalid_pdf_marks_failed(monkeypatch):
    contract_id = "worker-invalid"
    upload.contract_store.clear()
    upload.contract_store[contract_id] = {
        "id": contract_id,
        "user_id": "user-1",
        "filename": "broken.pdf",
        "contract_type": "nda",
        "selected_contract_type": "nda",
        "status": "uploaded",
        "storage_path": "local:///tmp/broken.pdf",
    }

    async def _false_async(*_args, **_kwargs):
        return False

    async def fake_load(_storage_path):
        return b"not a real pdf"

    monkeypatch.setattr(analysis_pipeline, "update_contract_progress", _false_async)
    monkeypatch.setattr(analysis_pipeline, "update_analysis_job", _false_async)
    monkeypatch.setattr(analysis_pipeline, "load_contract_file", fake_load)
    monkeypatch.setattr(analysis_pipeline, "extract_text_from_pdf", lambda _bytes: "")

    try:
        analysis_pipeline.run_contract_analysis_sync(contract_id)
    except analysis_pipeline.NonRetryablePipelineError as exc:
        assert "No text could be extracted" in str(exc)
    else:
        raise AssertionError("Expected invalid PDF to fail")

    assert upload.contract_store[contract_id]["status"] == "failed"
    assert "No text could be extracted" in upload.contract_store[contract_id]["error"]


def test_worker_pool_defaults_are_safe_for_dev_and_prod(monkeypatch):
    assert default_worker_pool(dev_mode=True) == "solo"
    assert default_worker_concurrency(dev_mode=True) == 1

    monkeypatch.setenv("WEB_CONCURRENCY", "3")
    assert default_worker_pool(dev_mode=False) == "prefork"
    assert default_worker_concurrency(dev_mode=False) == 3
