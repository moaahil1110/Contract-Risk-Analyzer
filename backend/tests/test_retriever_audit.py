import pytest

from scripts.audit_retriever import (
    determine_failure_reason,
    validate_audit_fixture,
    audit_labeled_case,
)


def _benchmark(
    benchmark_id="nda_001",
    contract_type="nda",
    clause_type="definition",
    similarity=0.82,
    eligible=True,
    reason="eligible",
):
    return {
        "benchmark_id": benchmark_id,
        "contract_type": contract_type,
        "clause_type": clause_type,
        "risk_level": "medium",
        "similarity": similarity,
        "retrieval_scope": "contract_type_clause_type",
        "citation_eligible": eligible,
        "relevance_reason": reason,
    }


def test_audit_fixture_validation_rejects_missing_selector():
    fixture = [{
        "document_id": "doc",
        "path": "NDA.pdf",
        "expected_contract_type": "nda",
        "cases": [{
            "case_id": "case",
            "expected_clause_type": "definition",
            "expected_benchmark_clause_types": ["definition"],
        }],
    }]

    with pytest.raises(ValueError, match="clause_number or contains"):
        validate_audit_fixture(fixture)


def test_determine_failure_reason_identifies_classifier_mismatch_first():
    reason = determine_failure_reason(
        clause_found=True,
        expected_contract_type="nda",
        expected_clause_type="definition",
        expected_benchmark_clause_types=["definition"],
        acceptable_benchmark_ids=["nda_001"],
        predicted_clause_type="ip_assignment",
        clause_type_confidence=0.9,
        retrieved_benchmarks=[_benchmark()],
    )

    assert reason == "classifier_mismatch"


def test_determine_failure_reason_identifies_missing_expected_benchmark():
    reason = determine_failure_reason(
        clause_found=True,
        expected_contract_type="nda",
        expected_clause_type="definition",
        expected_benchmark_clause_types=["definition"],
        acceptable_benchmark_ids=["nda_001"],
        predicted_clause_type="definition",
        clause_type_confidence=1.0,
        retrieved_benchmarks=[_benchmark("nda_999")],
    )

    assert reason == "expected_benchmark_missing_top5"


def test_determine_failure_reason_identifies_below_threshold_only():
    reason = determine_failure_reason(
        clause_found=True,
        expected_contract_type="nda",
        expected_clause_type="definition",
        expected_benchmark_clause_types=["definition"],
        acceptable_benchmark_ids=[],
        predicted_clause_type="definition",
        clause_type_confidence=1.0,
        retrieved_benchmarks=[
            _benchmark("nda_001", similarity=0.64, eligible=False, reason="below_similarity_threshold"),
            _benchmark("nda_002", similarity=0.62, eligible=False, reason="below_similarity_threshold"),
        ],
    )

    assert reason == "below_threshold_only"


def test_audit_labeled_case_runs_with_mocked_retriever_without_llm():
    document = {
        "document_id": "nda_sample",
        "expected_contract_type": "nda",
    }
    case = {
        "case_id": "nda_definition",
        "clause_number": "1",
        "expected_clause_type": "definition",
        "expected_benchmark_clause_types": ["definition"],
        "acceptable_benchmark_ids": ["nda_001"],
    }
    clauses = [{
        "clause_number": "1",
        "text": "1. Confidential Information means non-public business information marked confidential.",
    }]

    def fake_retrieve(*_args, **_kwargs):
        return [_benchmark("nda_001", "nda", "definition", 0.91, True)]

    row = audit_labeled_case(
        document=document,
        case=case,
        clauses=clauses,
        retrieve_fn=fake_retrieve,
    )

    assert row["passed"] is True
    assert row["failure_reason"] == "pass"
    assert row["predicted_clause_type"] == "definition"
    assert row["top_benchmarks"][0]["benchmark_id"] == "nda_001"
