"""
Priority 5: Product polish tests.
Covers history filters, soft delete, rerun, and polished PDF export.
"""

from contextlib import contextmanager
from fastapi.testclient import TestClient

from api.middleware.auth import require_user
from api.routes import upload, analyse, export, history
from main import app


_TEST_USER = {"id": "test-user-1", "email": "test@example.com"}
_OTHER_USER = {"id": "test-user-2", "email": "other@example.com"}


@contextmanager
def _authenticated_as(user_id="test-user-1", email="test@example.com"):
    app.dependency_overrides[require_user] = lambda: {"id": user_id, "email": email}
    try:
        yield
    finally:
        app.dependency_overrides.pop(require_user, None)


def _disable_database(monkeypatch):
    monkeypatch.setattr(analyse, "is_supabase_configured", lambda: False)
    monkeypatch.setattr(export, "is_supabase_configured", lambda: False)
    monkeypatch.setattr(history, "is_supabase_configured", lambda: False)

    async def _false_async(*_args, **_kwargs):
        return False

    monkeypatch.setattr(analyse, "get_active_analysis_job_for_contract", _false_async)
    monkeypatch.setattr(analyse, "create_analysis_job", lambda *_args, **_kwargs: _false_async())
    monkeypatch.setattr(analyse, "update_contract_progress", _false_async)
    monkeypatch.setattr(analyse, "delete_clauses_for_contract", _false_async)
    monkeypatch.setattr(analyse, "rerun_contract", _false_async)


def _complete_contract_in_store(contract_id: str, user_id: str, filename: str = "NDA.pdf"):
    upload.contract_store[contract_id] = {
        "id": contract_id,
        "user_id": user_id,
        "filename": filename,
        "contract_type": "nda",
        "selected_contract_type": "nda",
        "status": "complete",
        "health": {
            "score": 62,
            "grade": "C",
            "label": "Average",
            "risk_counts": {"high": 1, "medium": 2, "low": 3},
            "total_clauses": 7,
            "unknown_count": 1,
            "failed_clause_count": 1,
            "scored_clause_count": 6,
        },
        "analysis": [
            {
                "clause_title": "Confidentiality",
                "original_text": "Party must protect info.",
                "risk_level": "high",
                "risk_score": 85,
                "risk_reason": "Broad scope.",
                "plain_english": "You must keep secrets.",
                "key_concerns": ["Too broad"],
                "suggested_fix": "Narrow the definition.",
                "analysis_status": "success",
                "retry_count": 0,
                "provider_used": "test",
                "cited_benchmark_ids": ["nda_001"],
                "risk_rule_applied": "Broad confidentiality",
                "evidence_summary": "Benchmark confirms high risk",
                "benchmark_alignment": "strong",
                "retrieved_benchmarks": [
                    {
                        "id": "nda_001",
                        "benchmark_id": "nda_001",
                        "contract_type": "nda",
                        "clause_type": "confidentiality",
                        "risk_level": "high",
                        "similarity": 0.92,
                        "risk_rule": "Broad scope",
                    }
                ],
            },
            {
                "clause_title": "Term",
                "original_text": "Term is 5 years.",
                "risk_level": "medium",
                "risk_score": 55,
                "risk_reason": "Long term.",
                "plain_english": "Five year commitment.",
                "key_concerns": [],
                "suggested_fix": "Reduce to 2 years.",
                "analysis_status": "success",
                "retry_count": 0,
                "provider_used": "test",
                "cited_benchmark_ids": [],
                "risk_rule_applied": "",
                "evidence_summary": "",
                "benchmark_alignment": "partial",
                "retrieved_benchmarks": [],
            },
            {
                "clause_title": "Failed Clause",
                "original_text": "Unclear wording.",
                "risk_level": "unknown",
                "risk_score": None,
                "risk_reason": "Could not analyze.",
                "plain_english": "Analysis failed.",
                "key_concerns": ["Service unavailable"],
                "suggested_fix": "Retry analysis.",
                "analysis_status": "failed",
                "retry_count": 3,
                "error_message": "all providers failed",
                "provider_used": "fallback",
                "cited_benchmark_ids": [],
                "risk_rule_applied": "",
                "evidence_summary": "",
                "benchmark_alignment": "none",
                "retrieved_benchmarks": [],
            },
        ],
    }
    analyse.analysis_results[contract_id] = {
        "health": upload.contract_store[contract_id]["health"],
        "clauses": upload.contract_store[contract_id]["analysis"],
    }


# =============================================================================
# History filters
# =============================================================================

def test_history_filters_applied_in_memory(monkeypatch):
    _disable_database(monkeypatch)
    monkeypatch.setattr(history, "DEV_MODE", True)

    upload.contract_store.clear()
    upload.contract_store["c-1"] = {
        "id": "c-1",
        "user_id": _TEST_USER["id"],
        "filename": "Alpha.pdf",
        "contract_type": "nda",
        "status": "complete",
        "health_score": 80,
        "health_grade": "B",
    }
    upload.contract_store["c-2"] = {
        "id": "c-2",
        "user_id": _TEST_USER["id"],
        "filename": "Beta.pdf",
        "contract_type": "employment",
        "status": "failed",
        "health_score": None,
        "health_grade": None,
    }
    upload.contract_store["c-3"] = {
        "id": "c-3",
        "user_id": _TEST_USER["id"],
        "filename": "Gamma.pdf",
        "contract_type": "nda",
        "status": "complete",
        "health_score": 90,
        "health_grade": "A",
    }

    with _authenticated_as():
        client = TestClient(app)

        # Search by filename
        r = client.get("/api/v1/history?search=Alpha")
        assert r.status_code == 200
        assert len(r.json()["contracts"]) == 1
        assert r.json()["contracts"][0]["filename"] == "Alpha.pdf"

        # Filter by status
        r = client.get("/api/v1/history?status=failed")
        assert r.status_code == 200
        assert len(r.json()["contracts"]) == 1
        assert r.json()["contracts"][0]["id"] == "c-2"

        # Filter by contract_type
        r = client.get("/api/v1/history?contract_type=nda")
        assert r.status_code == 200
        assert len(r.json()["contracts"]) == 2

        # Filter by grade
        r = client.get("/api/v1/history?grade=A")
        assert r.status_code == 200
        assert len(r.json()["contracts"]) == 1
        assert r.json()["contracts"][0]["id"] == "c-3"


def test_history_excludes_soft_deleted_contracts(monkeypatch):
    _disable_database(monkeypatch)
    monkeypatch.setattr(history, "DEV_MODE", True)

    upload.contract_store.clear()
    upload.contract_store["c-del"] = {
        "id": "c-del",
        "user_id": _TEST_USER["id"],
        "filename": "Deleted.pdf",
        "contract_type": "nda",
        "status": "complete",
        "deleted_at": "2024-01-01T00:00:00Z",
    }
    upload.contract_store["c-ok"] = {
        "id": "c-ok",
        "user_id": _TEST_USER["id"],
        "filename": "Active.pdf",
        "contract_type": "nda",
        "status": "complete",
    }

    with _authenticated_as():
        client = TestClient(app)
        r = client.get("/api/v1/history")
        assert r.status_code == 200
        ids = {c["id"] for c in r.json()["contracts"]}
        assert "c-ok" in ids
        assert "c-del" not in ids


# =============================================================================
# Soft delete
# =============================================================================

def test_soft_delete_hides_contract_and_blocks_active_job(monkeypatch):
    _disable_database(monkeypatch)
    monkeypatch.setattr(history, "DEV_MODE", True)

    upload.contract_store.clear()
    upload.contract_store["c-del"] = {
        "id": "c-del",
        "user_id": _TEST_USER["id"],
        "filename": "ToDelete.pdf",
        "contract_type": "nda",
        "status": "complete",
    }

    with _authenticated_as():
        client = TestClient(app)

        # Delete succeeds for complete contract
        r = client.delete("/api/v1/history/c-del")
        assert r.status_code == 204

        # Now hidden from history
        r = client.get("/api/v1/history")
        assert r.status_code == 200
        ids = {c["id"] for c in r.json()["contracts"]}
        assert "c-del" not in ids

        # Hidden from results/export/status/analyse
        r = client.get("/api/v1/analyse/c-del")
        assert r.status_code == 404

        r = client.get("/api/v1/export/c-del")
        assert r.status_code == 404

        r = client.get("/api/v1/analyse/c-del/status")
        assert r.status_code == 404


def test_delete_blocked_for_active_job(monkeypatch):
    _disable_database(monkeypatch)
    monkeypatch.setattr(history, "DEV_MODE", True)

    upload.contract_store.clear()
    upload.contract_store["c-active"] = {
        "id": "c-active",
        "user_id": _TEST_USER["id"],
        "filename": "ActiveJob.pdf",
        "contract_type": "nda",
        "status": "queued",
    }
    # Simulate an active local job by putting it in analysis_results with an active status
    from services.job_queue import create_local_job
    create_local_job("c-active", "task-123")

    with _authenticated_as():
        client = TestClient(app)
        r = client.delete("/api/v1/history/c-active")
        assert r.status_code == 409
        assert "active" in r.json()["detail"].lower()


def test_delete_requires_ownership(monkeypatch):
    _disable_database(monkeypatch)
    monkeypatch.setattr(history, "DEV_MODE", False)

    upload.contract_store.clear()
    upload.contract_store["c-own"] = {
        "id": "c-own",
        "user_id": _TEST_USER["id"],
        "filename": "Owned.pdf",
        "contract_type": "nda",
        "status": "complete",
    }

    with _authenticated_as(user_id=_OTHER_USER["id"]):
        client = TestClient(app)
        r = client.delete("/api/v1/history/c-own")
        assert r.status_code == 404


# =============================================================================
# Rerun
# =============================================================================

def test_rerun_allowed_for_complete_and_failed(monkeypatch):
    _disable_database(monkeypatch)
    monkeypatch.setattr(analyse, "enqueue_contract_analysis", lambda contract_id, task_id=None: "task-rerun")

    for status in ("complete", "failed"):
        upload.contract_store.clear()
        analyse.analysis_results.clear()
        contract_id = f"c-{status}"
        upload.contract_store[contract_id] = {
            "id": contract_id,
            "user_id": _TEST_USER["id"],
            "filename": "Rerun.pdf",
            "contract_type": "nda",
            "selected_contract_type": "nda",
            "status": status,
            "health": {"score": 50, "grade": "C", "label": "Average"},
            "analysis": [{"clause_title": "Test", "risk_level": "low"}],
        }
        if status == "complete":
            analyse.analysis_results[contract_id] = {
                "health": upload.contract_store[contract_id]["health"],
                "clauses": upload.contract_store[contract_id]["analysis"],
            }

        with _authenticated_as():
            client = TestClient(app)
            r = client.post(f"/api/v1/analyse/{contract_id}/rerun")
            assert r.status_code == 200, f"Expected 200 for {status}, got {r.status_code}"
            assert r.json()["status"] == "queued"

        # In-memory store should be reset
        record = upload.contract_store[contract_id]
        assert record["status"] == "queued"
        assert record.get("health") is None or record.get("health") == {}
        assert record.get("analysis") == []
        assert record.get("rerun_count", 0) > 0


def test_rerun_blocked_for_active_states(monkeypatch):
    _disable_database(monkeypatch)

    for status in ("uploaded", "queued", "extracting", "analysing"):
        upload.contract_store.clear()
        contract_id = f"c-{status}"
        upload.contract_store[contract_id] = {
            "id": contract_id,
            "user_id": _TEST_USER["id"],
            "filename": "Active.pdf",
            "contract_type": "nda",
            "status": status,
        }

        with _authenticated_as():
            client = TestClient(app)
            r = client.post(f"/api/v1/analyse/{contract_id}/rerun")
            assert r.status_code == 409, f"Expected 409 for {status}, got {r.status_code}"


def test_rerun_clears_old_clause_analyses_and_results(monkeypatch):
    _disable_database(monkeypatch)
    monkeypatch.setattr(analyse, "enqueue_contract_analysis", lambda contract_id, task_id=None: "task-rerun")

    contract_id = "c-clear"
    _complete_contract_in_store(contract_id, _TEST_USER["id"])

    with _authenticated_as():
        client = TestClient(app)
        # Verify results exist before rerun
        r = client.get(f"/api/v1/analyse/{contract_id}")
        assert r.status_code == 200
        assert len(r.json()["clauses"]) == 3

        # Rerun
        r = client.post(f"/api/v1/analyse/{contract_id}/rerun")
        assert r.status_code == 200

        # Results cleared in memory
        assert contract_id not in analyse.analysis_results
        record = upload.contract_store[contract_id]
        assert record["status"] == "queued"
        assert record.get("analysis") == []


def test_rerun_requires_ownership(monkeypatch):
    _disable_database(monkeypatch)

    contract_id = "c-rerun-own"
    _complete_contract_in_store(contract_id, _TEST_USER["id"])

    with _authenticated_as(user_id=_OTHER_USER["id"]):
        client = TestClient(app)
        r = client.post(f"/api/v1/analyse/{contract_id}/rerun")
        assert r.status_code == 404


# =============================================================================
# Polished PDF export
# =============================================================================

def test_export_includes_polished_sections_and_rag_data(monkeypatch):
    _disable_database(monkeypatch)
    class FakeHTML:
        def __init__(self, string):
            self.string = string
        def write_pdf(self):
            return self.string.encode("utf-8")
    fake_mod = type("weasyprint", (), {"HTML": FakeHTML})()
    monkeypatch.setitem(__import__("sys").modules, "weasyprint", fake_mod)
    contract_id = "c-export"
    _complete_contract_in_store(contract_id, _TEST_USER["id"])
    with _authenticated_as():
        client = TestClient(app)
        r = client.get(f"/api/v1/export/{contract_id}")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        content = r.content.decode("utf-8", errors="replace")
        # Cover summary
        assert "Contract Risk Analysis Report" in content
        assert "NDA.pdf" in content
        assert "Grade C" in content
        assert "Average" in content
        # Risk breakdown
        assert "High Risk" in content
        assert "Medium Risk" in content
        assert "Low Risk" in content
        assert "Unknown" in content
        assert "Failed" in content
        # Recommendations
        assert "Recommendations" in content
        # Top risky clauses
        assert "Top Risky Clauses" in content
        assert "Confidentiality" in content
        # Failed section
        assert "Failed Analysis" in content
        assert "Failed Clause" in content
        assert "RAG Evidence" in content
        assert "nda_001" in content
        assert "Retrieved Benchmarks" in content
        assert "Similarity" in content
        # Page numbers via @page
        assert "counter(page)" in content

def test_export_requires_auth_and_ownership(monkeypatch):
    _disable_database(monkeypatch)
    monkeypatch.setattr(export, "DEV_MODE", False)

    contract_id = "c-export-auth"
    _complete_contract_in_store(contract_id, _TEST_USER["id"])

    # Unauthenticated
    client = TestClient(app)
    r = client.get(f"/api/v1/export/{contract_id}")
    assert r.status_code == 401

    # Wrong owner
    with _authenticated_as(user_id=_OTHER_USER["id"]):
        r = client.get(f"/api/v1/export/{contract_id}")
        assert r.status_code == 404
