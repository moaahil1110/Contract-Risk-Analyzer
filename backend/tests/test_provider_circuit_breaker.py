import httpx
import pytest

from pipeline.llm_analyser import (
    _is_provider_available,
    _mark_provider_unavailable,
    _parse_retry_after,
    _provider_circuits,
    _try_opencode_go,
    reset_provider_circuits,
    analyse_clause_sync,
    LLM_PROVIDER_COOLDOWN_SECONDS,
)
from services.analysis_pipeline import _provider_exhaustion_warning


def setup_function():
    reset_provider_circuits()


def test_provider_circuit_opens_on_429():
    # Simulate a 429 response with retry-after header
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(429, headers={"retry-after": "5"})
    exc = httpx.HTTPStatusError("Rate limited", request=request, response=response)

    # Directly exercise the parsing and marking logic
    retry_after = _parse_retry_after(exc)
    assert retry_after == 5
    _mark_provider_unavailable("groq", retry_after)
    assert not _is_provider_available("groq")


def test_provider_circuit_skips_unavailable_provider(monkeypatch):
    _mark_provider_unavailable("groq", 60)
    monkeypatch.setattr("pipeline.llm_analyser.LLM_PROVIDER_ORDER", ["groq", "openrouter", "opencode_go"])

    calls = []

    def fake_groq(prompt):
        calls.append("groq")
        return "groq-response"

    def fake_openrouter(prompt):
        calls.append("openrouter")
        return '{"clause_title": "T", "risk_level": "low", "risk_score": 10, "risk_reason": "R", "plain_english": "E", "key_concerns": ["C"], "suggested_fix": "F", "cited_benchmark_ids": [], "risk_rule_applied": "", "evidence_summary": "", "benchmark_alignment": "none"}'

    monkeypatch.setattr("pipeline.llm_analyser._try_groq", fake_groq)
    monkeypatch.setattr("pipeline.llm_analyser._try_openrouter", fake_openrouter)
    monkeypatch.setattr("pipeline.llm_analyser._try_opencode_go", lambda p: None)

    result = analyse_clause_sync("test clause", [], "nda")

    assert "groq" not in calls
    assert "openrouter" in calls
    assert result["provider_used"] == "openrouter"


def test_fallback_does_not_silently_become_medium_risk(monkeypatch):
    def fake_all_fail(prompt):
        return None

    monkeypatch.setattr("pipeline.llm_analyser._try_groq", fake_all_fail)
    monkeypatch.setattr("pipeline.llm_analyser._try_openrouter", fake_all_fail)
    monkeypatch.setattr("pipeline.llm_analyser._try_opencode_go", fake_all_fail)

    result = analyse_clause_sync("test clause", [], "nda")

    assert result["provider_used"] == "fallback"
    assert result["risk_level"] == "unknown"
    assert result["analysis_status"] == "failed"
    assert result["risk_score"] is None


def test_provider_exhaustion_warning_appears_when_many_clauses_fail():
    clauses = [
        {"provider_used": "fallback", "risk_level": "unknown"},
        {"provider_used": "fallback", "risk_level": "unknown"},
        {"provider_used": "groq", "risk_level": "low"},
    ]
    warning = _provider_exhaustion_warning(clauses)
    assert warning == "Provider quota exhausted; rerun later."


def test_provider_exhaustion_warning_absent_when_few_clauses_fail():
    clauses = [
        {"provider_used": "fallback", "risk_level": "unknown"},
        {"provider_used": "groq", "risk_level": "low"},
        {"provider_used": "groq", "risk_level": "low"},
    ]
    warning = _provider_exhaustion_warning(clauses)
    assert warning is None


def test_parse_retry_after_epoch_timestamp():
    request = httpx.Request("POST", "https://example.com")
    future_epoch = int(__import__("time").time()) + 120
    response = httpx.Response(429, headers={"x-ratelimit-reset": str(future_epoch)})
    exc = httpx.HTTPStatusError("Rate limited", request=request, response=response)
    parsed = _parse_retry_after(exc)
    assert parsed is not None
    assert 100 <= parsed <= 150


def test_parse_retry_after_epoch_milliseconds():
    request = httpx.Request("POST", "https://example.com")
    future_epoch_ms = (int(__import__("time").time()) + 120) * 1000
    response = httpx.Response(429, headers={"x-ratelimit-reset": str(future_epoch_ms)})
    exc = httpx.HTTPStatusError("Rate limited", request=request, response=response)
    parsed = _parse_retry_after(exc)
    assert parsed is not None
    assert 100 <= parsed <= 150


def test_opencode_go_429_opens_circuit(monkeypatch):
    request = httpx.Request("POST", "https://opencode.ai/zen/go/v1/chat/completions")
    response = httpx.Response(429, headers={"retry-after": "5"}, request=request)

    def fake_post(*args, **kwargs):
        return response

    monkeypatch.setattr("pipeline.llm_analyser.OPENCODE_GO_API_KEY", "test-key")
    monkeypatch.setattr("pipeline.llm_analyser.httpx.post", fake_post)

    result = _try_opencode_go("prompt")

    assert result is None
    assert not _is_provider_available("opencode_go")


def test_provider_retry_stops_when_circuit_opens(monkeypatch):
    calls = []

    def fake_groq(prompt):
        calls.append("groq")
        _mark_provider_unavailable("groq", 60)
        return None

    def fake_openrouter(prompt):
        calls.append("openrouter")
        return '{"clause_title": "T", "risk_level": "low", "risk_score": 10, "risk_reason": "R", "plain_english": "E", "key_concerns": ["C"], "suggested_fix": "F", "cited_benchmark_ids": [], "risk_rule_applied": "", "evidence_summary": "", "benchmark_alignment": "none"}'

    monkeypatch.setattr("pipeline.llm_analyser.LLM_PROVIDER_ORDER", ["groq", "openrouter"])
    monkeypatch.setattr("pipeline.llm_analyser.LLM_PROVIDER_MAX_RETRIES", 2)
    monkeypatch.setattr("pipeline.llm_analyser._try_groq", fake_groq)
    monkeypatch.setattr("pipeline.llm_analyser._try_openrouter", fake_openrouter)

    result = analyse_clause_sync("test clause", [], "nda")

    assert calls == ["groq", "openrouter"]
    assert result["provider_used"] == "openrouter"
