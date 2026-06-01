from pipeline import llm_analyser


def test_llm_total_failure_returns_unknown_failed_clause(monkeypatch):
    monkeypatch.setattr(llm_analyser, "MAX_RETRIES", 1)
    monkeypatch.setattr(llm_analyser, "_call_provider", lambda provider, prompt: None)

    result = llm_analyser.analyse_clause_sync(
        "The employee assigns all rights forever.",
        benchmarks=[],
        contract_type="employment",
    )

    assert result["analysis_status"] == "failed"
    assert result["risk_level"] == "unknown"
    assert result["risk_score"] is None
    assert result["retry_count"] == 4
    assert result["provider_used"] == "fallback"
    assert result["error_message"]
