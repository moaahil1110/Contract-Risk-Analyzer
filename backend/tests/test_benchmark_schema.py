from collections import Counter, defaultdict

from pipeline.benchmark_schema import format_benchmark_for_embedding, load_benchmarks, validate_benchmarks


def test_benchmark_dataset_has_required_schema_and_balance():
    benchmarks = load_benchmarks()
    errors, summary = validate_benchmarks(benchmarks)

    assert errors == []
    assert summary["total"] == 90
    assert summary["metadata_complete"] is True

    counts = defaultdict(Counter)
    for benchmark in benchmarks:
        counts[benchmark["contract_type"]][benchmark["risk_level"]] += 1

    for contract_type in ["nda", "employment", "vendor"]:
        assert counts[contract_type]["high"] == 10
        assert counts[contract_type]["medium"] == 10
        assert counts[contract_type]["low"] == 10


def test_embedding_text_contains_rag_evidence_fields():
    benchmark = load_benchmarks()[0]
    text = format_benchmark_for_embedding(benchmark)

    assert benchmark["clause_text"] in text
    assert benchmark["risk_rule"] in text
    assert benchmark["why_risky"] in text
    assert benchmark["safe_version"] in text
