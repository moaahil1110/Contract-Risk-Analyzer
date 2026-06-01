from pipeline.scorer import calculate_health_score


def test_health_score_matches_blueprint_weights():
    result = calculate_health_score([
        {"clause_title": "One", "risk_level": "high", "analysis_status": "success"},
        {"clause_title": "Two", "risk_level": "medium", "analysis_status": "success"},
        {"clause_title": "Three", "risk_level": "low", "analysis_status": "success"},
    ])

    assert result["score"] == 35
    assert result["grade"] == "F"
    assert result["label"] == "Critical Risk"
    assert result["risk_counts"] == {"high": 1, "medium": 1, "low": 1}
    assert result["scored_clause_count"] == 3
    assert result["unknown_count"] == 0


def test_failed_and_unknown_clauses_are_excluded_from_score():
    result = calculate_health_score([
        {"clause_title": "One", "risk_level": "low", "analysis_status": "success"},
        {"clause_title": "Two", "risk_level": "unknown", "analysis_status": "failed"},
        {"clause_title": "Three", "risk_level": "unknown", "analysis_status": "success"},
    ])

    assert result["score"] == 100
    assert result["grade"] == "A"
    assert result["label"] == "Low Risk"
    assert result["risk_counts"] == {"high": 0, "medium": 0, "low": 1}
    assert result["failed_clause_count"] == 1
    assert result["unknown_count"] == 2
    assert result["scored_clause_count"] == 1


def test_all_failed_contract_is_incomplete():
    result = calculate_health_score([
        {"clause_title": "One", "risk_level": "unknown", "analysis_status": "failed"},
        {"clause_title": "Two", "risk_level": "unknown", "analysis_status": "failed"},
    ])

    assert result["score"] == 0
    assert result["grade"] == "N/A"
    assert result["label"] == "Analysis Incomplete"
    assert result["failed_clause_count"] == 2
    assert result["unknown_count"] == 2
    assert result["scored_clause_count"] == 0
