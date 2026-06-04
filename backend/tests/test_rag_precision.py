from pathlib import Path

import pytest

from pipeline.clause_classifier import classify_clause_type
from pipeline.clause_splitter import clean_extracted_text, split_clauses_regex, split_clauses_structured
from pipeline import rag_engine
from services.analysis_pipeline import _enforce_citation_policy


def test_clean_extracted_text_removes_repeated_headers_and_preserves_numbering():
    text = """
Employment Contract
Page 1 of 2
1. Commencement
Employment starts on January 1.

Employment Contract
Page 2 of 2
2. Duties
Employee will perform normal duties.
"""
    cleaned = clean_extracted_text(text)

    assert "Page 1 of 2" not in cleaned
    assert "Page 2 of 2" not in cleaned
    assert "Employment Contract" not in cleaned
    assert "1. Commencement" in cleaned
    assert "2. Duties" in cleaned


def test_structured_splitter_keeps_subclauses_under_parent():
    text = """
1. Definitions
Confidential Information means non-public business information.
(a) Public information is excluded.
(b) Independently developed information is excluded.

2. Term
This Agreement lasts two years.

3. Notices
Notices must be sent by email.
"""

    clauses = split_clauses_structured(text)

    assert len(clauses) == 3
    assert clauses[0]["clause_number"] == "1"
    assert clauses[0]["parsed_section_count"] == 3
    assert [sub["clause_number"] for sub in clauses[0]["subclauses"]] == ["(a)", "(b)"]
    assert all(clause["is_scored"] is True for clause in clauses)


@pytest.mark.parametrize(
    ("contract_type", "text", "expected"),
    [
        ("employment", "Employee starts on the commencement date and completes onboarding.", "commencement"),
        ("employment", "Normal working hours are 9 to 5 with approved overtime.", "work_hours"),
        ("nda", "The receiving party may disclose information if required by law or subpoena.", "compelled_disclosure"),
        ("nda", "Confidentiality obligations survive for three years after termination.", "survival"),
        ("nda", "Recipient shall not engage in direct competition with the company after termination.", "non_compete"),
        ("nda", "Recipient shall not solicit customers, employees, or business contacts.", "non_solicitation"),
        ("nda", "Recipient may not pursue any business opportunity learned through the relationship.", "business_opportunity"),
        ("nda", "Recipient must pay all legal fees and enforcement costs.", "fees_costs"),
        ("nda", "Any unenforceable provision shall be severable from the rest of this agreement.", "severability"),
        ("vendor", "Any scope change requires a written change order with fee adjustments.", "change_orders"),
        ("vendor", "Vendor must maintain insurance coverage and provide certificates.", "insurance"),
    ],
)
def test_clause_classifier_returns_expected_type(contract_type, text, expected):
    result = classify_clause_type(text, contract_type)

    assert result["predicted_clause_type"] == expected
    assert result["clause_type_confidence"] >= 0.45
    assert result["clause_type_matched_terms"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Any late payments will trigger a fee of 18.00% per month on the amount still owing.",
            "payment_terms",
        ),
        (
            "The Contractor will be reimbursed from time to time for reasonable and necessary expenses incurred in connection with providing the Services.",
            "taxes_expenses",
        ),
        (
            "Any sales tax and duties required by law will be charged to the Client in addition to the Compensation.",
            "taxes_expenses",
        ),
        (
            "Except as provided in settlement, each Party indemnifies the other against claims, losses, damages, liabilities, penalties, punitive damages, expenses, legal fees and costs.",
            "indemnification",
        ),
    ],
)
def test_vendor_classifier_routes_sa_clauses_to_benchmark_backed_types(text, expected):
    result = classify_clause_type(text, "vendor")

    assert result["predicted_clause_type"] == expected
    assert result["clause_type_confidence"] >= 0.45


def test_vendor_classifier_does_not_confidently_emit_unsupported_waiver_type():
    result = classify_clause_type(
        "Time is of the essence in this Agreement. No extension or variation will operate as a waiver.",
        "vendor",
    )

    assert result["predicted_clause_type"] != "waiver"


def test_retrieve_benchmarks_marks_ineligible_low_similarity(monkeypatch):
    class FakeCollection:
        def query(self, **_kwargs):
            return {
                "ids": [["employment_031"]],
                "metadatas": [[
                    {
                        "benchmark_id": "employment_031",
                        "contract_type": "employment",
                        "clause_type": "commencement",
                        "risk_level": "low",
                        "clause_text": "Employment starts on the stated commencement date.",
                        "risk_rule": "Clear start date.",
                        "why_risky": "Low ambiguity.",
                        "risk_notes": "Low ambiguity.",
                        "safe_version": "State the start date.",
                        "source_name": "Curated Contract Risk Benchmark Library v2",
                        "source_type": "curated",
                        "source_url": "local://backend/benchmarks/curated-v2",
                        "source_license_note": "Curated benchmark.",
                        "jurisdiction": "general/common-law",
                        "tags": "[\"commencement\"]",
                    }
                ]],
                "distances": [[0.8]],  # similarity 0.6
            }

    monkeypatch.setattr(rag_engine, "get_benchmark_collection", lambda: FakeCollection())
    monkeypatch.setattr(rag_engine, "embed_text", lambda _text: [0.1, 0.2])

    results = rag_engine.retrieve_benchmarks(
        "Employment begins on the commencement date.",
        k=1,
        contract_type="employment",
        clause_type="commencement",
        clause_type_confidence=1.0,
    )

    assert results[0]["citation_eligible"] is False
    assert results[0]["relevance_reason"] == "below_similarity_threshold"


def test_retrieve_benchmarks_prefers_clause_type_filter(monkeypatch):
    calls = []

    class FakeCollection:
        def query(self, **kwargs):
            calls.append(kwargs.get("where"))
            return {
                "ids": [["employment_031"]],
                "metadatas": [[
                    {
                        "benchmark_id": "employment_031",
                        "contract_type": "employment",
                        "clause_type": "commencement",
                        "risk_level": "low",
                        "clause_text": "Employment starts on the stated commencement date.",
                        "risk_rule": "Clear start date.",
                        "why_risky": "Low ambiguity.",
                        "risk_notes": "Low ambiguity.",
                        "safe_version": "State the start date.",
                        "source_name": "Curated Contract Risk Benchmark Library v2",
                        "source_type": "curated",
                        "source_url": "local://backend/benchmarks/curated-v2",
                        "source_license_note": "Curated benchmark.",
                        "jurisdiction": "general/common-law",
                        "tags": "[\"commencement\"]",
                    }
                ]],
                "distances": [[0.1]],
            }

    monkeypatch.setattr(rag_engine, "get_benchmark_collection", lambda: FakeCollection())
    monkeypatch.setattr(rag_engine, "embed_text", lambda _text: [0.1, 0.2])

    results = rag_engine.retrieve_benchmarks(
        "Employment begins on the commencement date.",
        k=1,
        contract_type="employment",
        clause_type="commencement",
        clause_type_confidence=1.0,
    )

    assert calls[0] == {"$and": [{"contract_type": "employment"}, {"clause_type": "commencement"}]}
    assert results[0]["retrieval_scope"] == "contract_type_clause_type"
    assert results[0]["citation_eligible"] is True


def test_llm_citations_are_stripped_when_not_eligible():
    result = {
        "cited_benchmark_ids": ["employment_999"],
        "risk_rule_applied": "Some rule",
        "evidence_summary": "Some evidence",
        "benchmark_alignment": "strong",
    }

    cleaned = _enforce_citation_policy(result, [])

    assert cleaned["cited_benchmark_ids"] == []
    assert cleaned["risk_rule_applied"] == ""
    assert cleaned["benchmark_alignment"] == "none"
    assert cleaned["evidence_summary"] == "No direct benchmark met the relevance threshold."


def test_sample_pdf_cleanup_keeps_reasonable_clause_counts():
    for filename in ["EC.pdf", "NDA.pdf", "SA.pdf"]:
        path = Path(__file__).resolve().parents[2] / filename
        if not path.exists():
            continue
        from pipeline.pdf_parser import extract_text_from_pdf

        cleaned = clean_extracted_text(extract_text_from_pdf(path.read_bytes()))
        clauses = split_clauses_regex(cleaned)

        assert len(clauses) >= 10
        assert not any("page " in clause.lower() and " of " in clause.lower() for clause in clauses)


def test_nda_structured_count_matches_numbered_sections_when_sample_exists():
    path = Path(__file__).resolve().parents[2] / "NDA.pdf"
    if not path.exists():
        pytest.skip("NDA.pdf sample not present")
    from pipeline.pdf_parser import extract_text_from_pdf

    cleaned = clean_extracted_text(extract_text_from_pdf(path.read_bytes()))
    clauses = split_clauses_structured(cleaned)

    assert len(clauses) == 38
    assert sum(clause.get("parsed_section_count", 1) for clause in clauses) == 43
    assert [clause["clause_number"] for clause in clauses][-1] == "38"
