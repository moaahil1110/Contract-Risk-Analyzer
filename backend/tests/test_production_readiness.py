from fastapi.testclient import TestClient

from core import embedding_config
from db import queries
from services import job_queue
import main


def test_embedding_offline_config_sets_required_env(monkeypatch, tmp_path):
    model_dir = tmp_path / "model"
    model_dir.mkdir()

    monkeypatch.setenv("EMBEDDING_OFFLINE", "true")
    monkeypatch.setenv("EMBEDDING_MODEL_PATH", str(model_dir))
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)

    config = embedding_config.validate_embedding_config()

    assert config["embedding_offline"] is True
    assert config["embedding_model_source"] == str(model_dir)
    assert config["transformers_offline"] == "1"
    assert config["hf_hub_offline"] == "1"


def test_embedding_offline_missing_path_fails_fast(monkeypatch, tmp_path):
    missing = tmp_path / "missing-model"
    monkeypatch.setenv("EMBEDDING_OFFLINE", "true")
    monkeypatch.setenv("EMBEDDING_MODEL_PATH", str(missing))

    try:
        embedding_config.validate_embedding_config()
    except RuntimeError as exc:
        assert "EMBEDDING_MODEL_PATH" in str(exc)
    else:
        raise AssertionError("Expected missing embedding model path to fail")


def test_detailed_health_reports_rag_and_queue(monkeypatch):
    monkeypatch.setattr(main, "get_collection_stats", lambda: {
        "collection_name": "contract_benchmarks",
        "total_benchmarks": 180,
        "persist_path": "/tmp/chroma",
        "embedding_model": "all-MiniLM-L6-v2",
    })
    monkeypatch.setattr(main, "get_queue_health", lambda: {
        "reachable": True,
    })
    monkeypatch.setattr(main, "_check_weasyprint_health", lambda: {"usable": True, "pdf_bytes": 1234})

    client = TestClient(main.app)
    response = client.get("/health/details")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["rag"]["loaded"] is True
    assert body["queue"]["reachable"] is True
    assert "broker_url" not in body["queue"]
    assert body["weasyprint"]["usable"] is True
    assert "pdf_bytes" in body["weasyprint"]


def test_queue_health_reports_online_workers(monkeypatch):
    class FakeRedis:
        def ping(self):
            return True
        def llen(self, _queue):
            return 2

    class FakeInspect:
        def ping(self):
            return {"celery@worker": {"ok": "pong"}}
        def active(self):
            return {"celery@worker": [{"id": "active-task"}]}
        def reserved(self):
            return {"celery@worker": []}
        def scheduled(self):
            return {"celery@worker": []}

    class FakeControl:
        def inspect(self, timeout=1):
            assert timeout == 1
            return FakeInspect()

    class FakeCelery:
        control = FakeControl()

    monkeypatch.setattr(job_queue.Redis, "from_url", lambda *_args, **_kwargs: FakeRedis())
    monkeypatch.setattr(job_queue, "celery_app", FakeCelery())
    monkeypatch.setattr(job_queue, "CELERY_TASK_ALWAYS_EAGER", False)

    health = job_queue.get_queue_health()

    assert health["reachable"] is True
    assert health["broker_reachable"] is True
    assert health["workers_online"] == 1
    assert health["worker_names"] == ["celery@worker"]
    assert health["broker_queue_depth"] == 2
    assert health["active_task_count"] == 1
    assert health["reserved_task_count"] == 0
    assert health["scheduled_task_count"] == 0
    assert "broker_url" not in health


def test_detailed_health_degrades_when_weasyprint_unusable_in_production(monkeypatch):
    monkeypatch.setattr(main, "DEV_MODE", False)
    monkeypatch.setattr(main, "get_collection_stats", lambda: {"total_benchmarks": 180})
    monkeypatch.setattr(main, "get_queue_health", lambda: {"reachable": True})
    monkeypatch.setattr(main, "_check_weasyprint_health", lambda: {"usable": False, "error": "missing lib"})

    client = TestClient(main.app)
    response = client.get("/health/details")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"

def test_production_cors_defaults_to_no_origins(monkeypatch):
    monkeypatch.setattr(main, "DEV_MODE", False)
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)

    assert main._get_cors_origins() == []


def test_mark_stale_analysis_jobs_failed(monkeypatch):
    stale = [{
        "id": "job-1",
        "contract_id": "contract-1",
        "metadata": {"existing": True},
    }]
    calls = []

    async def fake_get_stale(timeout_minutes):
        assert timeout_minutes == 15
        return stale

    async def fake_update_job(*args, **kwargs):
        calls.append(("job", args, kwargs))
        return True

    async def fake_update_contract(*args, **kwargs):
        calls.append(("contract", args, kwargs))
        return True

    monkeypatch.setattr(queries, "get_stale_analysis_jobs", fake_get_stale)
    monkeypatch.setattr(queries, "update_analysis_job", fake_update_job)
    monkeypatch.setattr(queries, "update_contract_progress", fake_update_contract)

    import asyncio
    result = asyncio.run(queries.mark_stale_analysis_jobs_failed(15))

    assert result == stale
    assert calls[0][0] == "job"
    assert calls[1][0] == "contract"
