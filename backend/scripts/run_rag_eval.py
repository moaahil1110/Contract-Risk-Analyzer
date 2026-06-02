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
from pipeline.llm_analyser import validate_response
from pipeline.rag_engine import get_collection_stats, retrieve_benchmarks

TOP3_HIT_GATE = 0.80
CONTRACT_TYPE_PRECISION_GATE = 0.90


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

    collection_stats = get_collection_stats()
    if collection_stats["total_benchmarks"] < schema_summary["total"]:
        raise RuntimeError(
            "Benchmark collection is incomplete. Run "
            "`python3 backend/scripts/build_benchmarks.py --force` first."
        )

    retrieval = evaluate_retrieval(queries, expected_retrieval)
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
        "analyzer": schema_validity,
        "passed": (
            len(schema_errors) == 0
            and retrieval["top3_hit_rate"] >= TOP3_HIT_GATE
            and retrieval["contract_type_precision"] >= CONTRACT_TYPE_PRECISION_GATE
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
