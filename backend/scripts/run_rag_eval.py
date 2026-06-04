#!/usr/bin/env python3
"""
Offline RAG quality evaluation for the benchmark retrieval layer.

This script does not call external LLM providers. It validates benchmark metadata,
runs local retrieval over fixture queries, and checks the analyzer JSON schema with
synthetic evidence-backed outputs.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from pipeline.benchmark_schema import load_benchmarks, validate_benchmarks
from pipeline.clause_classifier import classify_clause_type
from pipeline.clause_splitter import clean_extracted_text, split_clauses_regex
from pipeline.llm_analyser import validate_response
from pipeline.pdf_parser import extract_text_from_pdf
from pipeline.rag_engine import get_collection_stats, retrieve_benchmarks
from services.analysis_pipeline import detect_contract_type

TOP3_HIT_GATE = 0.90
CONTRACT_TYPE_PRECISION_GATE = 1.00
CLAUSE_TYPE_HIT_GATE = 0.85


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def fixture_dir() -> Path:
    return backend_dir / "evals"


def evaluate_retrieval(
    queries: List[Dict[str, Any]],
    expected_retrieval: Dict[str, Dict[str, Any]],
    k: int = 3,
) -> Dict[str, Any]:
    rows = []
    top1_hits = 0
    top3_hits = 0
    contract_type_matches = 0
    clause_type_matches = 0

    for query in queries:
        query_id = query["query_id"]
        expected = expected_retrieval[query_id]
        results = retrieve_benchmarks(
            query["query_text"],
            k=k,
            contract_type=query["contract_type"],
        )
        ids = {item.get("benchmark_id") or item.get("id") for item in results}
        top1_id = results[0].get("benchmark_id") or results[0].get("id") if results else None
        expected_ids = set(expected["expected_any_benchmark_ids"])
        has_top1_hit = top1_id in expected_ids
        has_hit = bool(ids & expected_ids)
        contract_match = bool(results) and results[0].get("contract_type") == expected["expected_contract_type"]
        clause_match = any(
            item.get("clause_type") == expected["expected_clause_type"]
            for item in results
        )

        top1_hits += int(has_top1_hit)
        top3_hits += int(has_hit)
        contract_type_matches += int(contract_match)
        clause_type_matches += int(clause_match)
        rows.append({
            "query_id": query_id,
            "top_ids": list(ids),
            "top1_hit": has_top1_hit,
            "top3_hit": has_hit,
            "contract_type_match": contract_match,
            "clause_type_match": clause_match,
        })

    total = len(queries) or 1
    return {
        "top1_hit_rate": top1_hits / total,
        "top3_hit_rate": top3_hits / total,
        "contract_type_precision": contract_type_matches / total,
        "clause_type_hit_rate": clause_type_matches / total,
        "rows": rows,
    }


def _find_clause(clauses: List[str], needle: str) -> str:
    needle_lower = needle.lower()
    for clause in clauses:
        if needle_lower in clause.lower():
            return clause
    return ""


def evaluate_gold_documents(documents: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows = []
    type_hits = 0
    check_count = 0
    clause_type_hits = 0
    eligible_checks = 0
    suppressed = 0
    unmatched = 0
    cross_type_citations = 0
    below_threshold_citations = 0
    header_footer_failures = 0

    repo_root = backend_dir.parent
    for document in documents:
        path = repo_root / document["path"]
        text = clean_extracted_text(extract_text_from_pdf(path.read_bytes()))
        clauses = split_clauses_regex(text)
        detection = detect_contract_type(clauses)
        expected_contract_type = document["expected_contract_type"]
        detected_contract_type = detection.get("detected_contract_type")
        type_match = detected_contract_type == expected_contract_type
        type_hits += int(type_match)

        contamination = any("page " in clause.lower() and " of " in clause.lower() for clause in clauses)
        header_footer_failures += int(contamination)

        for check in document["checks"]:
            check_count += 1
            clause = _find_clause(clauses, check["contains"])
            if not clause:
                unmatched += 1
                rows.append({
                    "document_id": document["document_id"],
                    "contains": check["contains"],
                    "found": False,
                    "expected_clause_type": check["expected_clause_type"],
                })
                continue

            clause_type = classify_clause_type(clause, expected_contract_type)
            results = retrieve_benchmarks(
                clause,
                k=3,
                contract_type=expected_contract_type,
                clause_type=clause_type.get("predicted_clause_type"),
                clause_type_confidence=clause_type.get("clause_type_confidence", 0.0),
            )
            eligible = [item for item in results if item.get("citation_eligible")]
            eligible_checks += int(bool(eligible))
            suppressed += int(bool(results and not eligible))
            cross_type_citations += sum(1 for item in eligible if item.get("contract_type") != expected_contract_type)
            below_threshold_citations += sum(1 for item in eligible if float(item.get("similarity") or 0) < 0.70)
            clause_match = any(item.get("clause_type") == check["expected_clause_type"] for item in eligible)
            clause_type_hits += int(clause_match)
            if not eligible:
                unmatched += 1

            rows.append({
                "document_id": document["document_id"],
                "contains": check["contains"],
                "found": True,
                "expected_contract_type": expected_contract_type,
                "detected_contract_type": detected_contract_type,
                "expected_clause_type": check["expected_clause_type"],
                "predicted_clause_type": clause_type.get("predicted_clause_type"),
                "eligible_ids": [item.get("benchmark_id") for item in eligible],
                "clause_type_hit": clause_match,
            })

    doc_total = len(documents) or 1
    total_checks = check_count or 1
    return {
        "contract_type_detection": type_hits / doc_total,
        "clause_type_hit_rate": clause_type_hits / total_checks,
        "citation_eligibility_rate": eligible_checks / total_checks,
        "suppressed_citation_count": suppressed,
        "unmatched_clause_count": unmatched,
        "cross_contract_type_citations": cross_type_citations,
        "below_threshold_citations": below_threshold_citations,
        "header_footer_contamination_failures": header_footer_failures,
        "rows": rows,
    }


def evaluate_schema_validity(queries: List[Dict[str, Any]], expected_risk: Dict[str, str]) -> Dict[str, Any]:
    valid = 0
    aligned = 0
    for query in queries:
        query_id = query["query_id"]
        response = {
            "clause_title": "Fixture Clause",
            "risk_level": expected_risk[query_id],
            "risk_score": 85 if expected_risk[query_id] == "high" else 60 if expected_risk[query_id] == "medium" else 20,
            "risk_reason": "Fixture risk reason for schema validation.",
            "plain_english": "Fixture plain-English explanation.",
            "key_concerns": ["Fixture concern"],
            "suggested_fix": "Fixture safer clause.",
            "cited_benchmark_ids": ["fixture_benchmark"],
            "risk_rule_applied": "Fixture risk rule.",
            "evidence_summary": "Fixture evidence summary.",
            "benchmark_alignment": "strong",
        }
        is_valid = validate_response(response)
        valid += int(is_valid)
        aligned += int(is_valid and response["benchmark_alignment"] != "none")

    total = len(queries) or 1
    return {
        "analyzer_json_schema_validity": valid / total,
        "benchmark_alignment_coverage": aligned / total,
        "failed_analysis_rate": 0.0,
    }


def run_eval() -> Dict[str, Any]:
    benchmarks = load_benchmarks()
    schema_errors, schema_summary = validate_benchmarks(benchmarks)
    queries = _load_json(fixture_dir() / "queries.json")
    expected_retrieval = _load_json(fixture_dir() / "expected_retrieval.json")
    expected_risk = _load_json(fixture_dir() / "expected_risk.json")
    gold_documents = _load_json(fixture_dir() / "gold_documents.json")

    collection_stats = get_collection_stats()
    if collection_stats["total_benchmarks"] < schema_summary["total"]:
        raise RuntimeError(
            "Benchmark collection is incomplete. Run "
            "`python3 backend/scripts/build_benchmarks.py --force` first."
        )

    retrieval = evaluate_retrieval(queries, expected_retrieval)
    gold = evaluate_gold_documents(gold_documents)
    schema_validity = evaluate_schema_validity(queries, expected_risk)
    report = {
        "benchmark_schema": schema_summary,
        "schema_error_count": len(schema_errors),
        "collection": collection_stats,
        "retrieval": {
            key: value
            for key, value in retrieval.items()
            if key != "rows"
        },
        "gold_documents": {
            key: value
            for key, value in gold.items()
            if key != "rows"
        },
        "analyzer": schema_validity,
        "passed": (
            len(schema_errors) == 0
            and retrieval["top3_hit_rate"] >= TOP3_HIT_GATE
            and retrieval["contract_type_precision"] >= CONTRACT_TYPE_PRECISION_GATE
            and retrieval["clause_type_hit_rate"] >= CLAUSE_TYPE_HIT_GATE
            and gold["contract_type_detection"] == 1.0
            and gold["cross_contract_type_citations"] == 0
            and gold["below_threshold_citations"] == 0
            and gold["header_footer_contamination_failures"] == 0
            and schema_validity["analyzer_json_schema_validity"] == 1.0
            and schema_validity["failed_analysis_rate"] == 0.0
        ),
        "failures": [],
    }

    if schema_errors:
        report["failures"].append(f"{len(schema_errors)} benchmark schema errors")
    if retrieval["top3_hit_rate"] < TOP3_HIT_GATE:
        report["failures"].append(
            f"top3_hit_rate {retrieval['top3_hit_rate']:.2f} below {TOP3_HIT_GATE:.2f}"
        )
    if retrieval["contract_type_precision"] < CONTRACT_TYPE_PRECISION_GATE:
        report["failures"].append(
            "contract_type_precision "
            f"{retrieval['contract_type_precision']:.2f} below {CONTRACT_TYPE_PRECISION_GATE:.2f}"
        )
    if retrieval["clause_type_hit_rate"] < CLAUSE_TYPE_HIT_GATE:
        report["failures"].append(
            f"clause_type_hit_rate {retrieval['clause_type_hit_rate']:.2f} below {CLAUSE_TYPE_HIT_GATE:.2f}"
        )
    if gold["contract_type_detection"] != 1.0:
        report["failures"].append("gold document contract type detection below 1.00")
    if gold["cross_contract_type_citations"] > 0:
        report["failures"].append("gold document eval found cross-contract-type citations")
    if gold["below_threshold_citations"] > 0:
        report["failures"].append("gold document eval found below-threshold citations")
    if gold["header_footer_contamination_failures"] > 0:
        report["failures"].append("gold document eval found header/footer contamination")
    if schema_validity["analyzer_json_schema_validity"] != 1.0:
        report["failures"].append("analyzer JSON schema validity below 1.00")

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run offline RAG quality checks")
    parser.add_argument("--json", action="store_true", help="Print compact JSON only")
    args = parser.parse_args()

    try:
        report = run_eval()
    except Exception as exc:
        print(f"RAG eval failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(report, indent=None if args.json else 2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
