from scripts.run_rag_eval import evaluate_retrieval, evaluate_schema_validity


def test_eval_metrics_calculate_retrieval_gates(monkeypatch):
    queries = [
        {
            "query_id": "q1",
            "contract_type": "nda",
            "query_text": "confidential information excludes public information",
        }
    ]
    expected = {
        "q1": {
            "expected_contract_type": "nda",
            "expected_clause_type": "exceptions",
            "expected_any_benchmark_ids": ["nda_022", "nda_023"],
        }
    }

    def fake_retrieve(*_args, **_kwargs):
        return [
            {
                "benchmark_id": "nda_022",
                "contract_type": "nda",
                "clause_type": "exceptions",
            }
        ]

    monkeypatch.setattr("scripts.run_rag_eval.retrieve_benchmarks", fake_retrieve)
    metrics = evaluate_retrieval(queries, expected)

    assert metrics["top3_hit_rate"] == 1.0
    assert metrics["contract_type_precision"] == 1.0
    assert metrics["clause_type_hit_rate"] == 1.0


def test_eval_schema_validity_uses_current_analyzer_contract():
    metrics = evaluate_schema_validity(
        [{"query_id": "q1"}],
        {"q1": "medium"},
    )

    assert metrics["analyzer_json_schema_validity"] == 1.0
    assert metrics["failed_analysis_rate"] == 0.0
