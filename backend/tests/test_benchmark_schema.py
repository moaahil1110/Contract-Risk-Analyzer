from collections import Counter, defaultdict

from pipeline.benchmark_schema import format_benchmark_for_embedding, load_benchmarks, validate_benchmarks


def test_benchmark_dataset_has_required_schema_and_balance():
    benchmarks = load_benchmarks()
    errors, summary = validate_benchmarks(benchmarks)

    assert errors == []
    assert summary["total"] == 180
    assert summary["metadata_complete"] is True

    counts = defaultdict(Counter)
    for benchmark in benchmarks:
        counts[benchmark["contract_type"]][benchmark["risk_level"]] += 1

    for contract_type in ["nda", "employment", "vendor"]:
        assert counts[contract_type]["high"] == 20
        assert counts[contract_type]["medium"] == 20
        assert counts[contract_type]["low"] == 20
        assert sum(counts[contract_type].values()) == 60


def test_benchmark_dataset_includes_precision_clause_types():
    benchmarks = load_benchmarks()
    clause_types = defaultdict(set)
    for benchmark in benchmarks:
        clause_types[benchmark["contract_type"]].add(benchmark["clause_type"])

    assert {
        "commencement",
        "job_duties",
        "work_hours",
        "leave",
        "company_policies",
    }.issubset(clause_types["employment"])
    assert {
        "authorized_recipients",
        "compelled_disclosure",
        "no_license",
        "standard_of_care",
        "survival",
        "non_compete",
        "non_solicitation",
        "business_opportunity",
        "ip_assignment",
        "fees_costs",
        "notices",
    }.issubset(clause_types["nda"])
    assert {
        "change_orders",
        "subcontracting",
        "audit_rights",
        "confidentiality",
        "transition_assistance",
    }.issubset(clause_types["vendor"])


def test_embedding_text_contains_rag_evidence_fields():
    benchmark = load_benchmarks()[0]
    text = format_benchmark_for_embedding(benchmark)

    assert benchmark["clause_text"] in text
    assert benchmark["risk_rule"] in text
    assert benchmark["why_risky"] in text
    assert benchmark["safe_version"] in text
