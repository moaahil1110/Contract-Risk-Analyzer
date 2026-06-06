#!/usr/bin/env python3
"""Generate a non-LLM audit of clause classification and benchmark retrieval."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

backend_dir = Path(__file__).parent.parent
repo_root = backend_dir.parent
sys.path.insert(0, str(backend_dir))

from pipeline.clause_classifier import CLAUSE_TYPE_CONFIDENCE_THRESHOLD, classify_clause_type
from pipeline.clause_splitter import clean_extracted_text, split_clauses_structured
from pipeline.pdf_parser import extract_text_from_pdf
from pipeline.rag_engine import retrieve_benchmarks
from services.analysis_pipeline import detect_contract_type

FAILURE_REASONS = {
    "pass",
    "clause_not_found",
    "classifier_mismatch",
    "classifier_low_confidence",
    "expected_benchmark_missing_top5",
    "expected_clause_type_missing_top5",
    "no_eligible_benchmark",
    "below_threshold_only",
    "cross_contract_type_result",
    "benchmark_gap",
}


def fixture_path() -> Path:
    return backend_dir / "evals" / "retriever_audit_cases.json"


def reports_dir() -> Path:
    return backend_dir / "reports" / "retriever_audit"


def load_audit_fixture(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    with (path or fixture_path()).open("r", encoding="utf-8") as handle:
        fixture = json.load(handle)
    validate_audit_fixture(fixture)
    return fixture


def validate_audit_fixture(fixture: Any) -> None:
    if not isinstance(fixture, list) or not fixture:
        raise ValueError("Retriever audit fixture must be a non-empty list")

    seen_case_ids = set()
    for document in fixture:
        for field in ("document_id", "path", "expected_contract_type", "cases"):
            if field not in document:
                raise ValueError(f"Audit document is missing required field: {field}")
        if document["expected_contract_type"] not in {"employment", "nda", "vendor"}:
            raise ValueError(f"Unsupported contract type: {document['expected_contract_type']}")
        if not isinstance(document["cases"], list) or not document["cases"]:
            raise ValueError(f"{document['document_id']} must define at least one case")

        for case in document["cases"]:
            for field in ("case_id", "expected_clause_type", "expected_benchmark_clause_types"):
                if field not in case:
                    raise ValueError(f"{document['document_id']} case is missing required field: {field}")
            if "clause_number" not in case and "contains" not in case:
                raise ValueError(f"{case['case_id']} must define clause_number or contains")
            if case["case_id"] in seen_case_ids:
                raise ValueError(f"Duplicate audit case_id: {case['case_id']}")
            seen_case_ids.add(case["case_id"])


def _clause_text(clause: Dict[str, Any]) -> str:
    return str(clause.get("text") or clause.get("original_text") or "")


def _clause_preview(text: str, limit: int = 240) -> str:
    compact = " ".join(str(text or "").split())
    return compact if len(compact) <= limit else compact[: limit - 3].rstrip() + "..."


def find_clause(clauses: List[Dict[str, Any]], case: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    clause_number = str(case.get("clause_number", "")).strip()
    if clause_number:
        for clause in clauses:
            if str(clause.get("clause_number", "")).strip() == clause_number:
                return clause

    needle = str(case.get("contains", "")).strip().lower()
    if needle:
        for clause in clauses:
            if needle in _clause_text(clause).lower():
                return clause
    return None


def _benchmark_id(benchmark: Dict[str, Any]) -> str:
    return str(benchmark.get("benchmark_id") or benchmark.get("id") or "")


def summarize_benchmark(benchmark: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "benchmark_id": _benchmark_id(benchmark),
        "contract_type": benchmark.get("contract_type"),
        "clause_type": benchmark.get("clause_type"),
        "risk_level": benchmark.get("risk_level"),
        "similarity": benchmark.get("similarity"),
        "retrieval_scope": benchmark.get("retrieval_scope"),
        "citation_eligible": bool(benchmark.get("citation_eligible")),
        "relevance_reason": benchmark.get("relevance_reason"),
    }


def determine_failure_reason(
    *,
    clause_found: bool,
    expected_contract_type: str,
    expected_clause_type: str,
    expected_benchmark_clause_types: Iterable[str],
    acceptable_benchmark_ids: Iterable[str],
    predicted_clause_type: Optional[str],
    clause_type_confidence: float,
    retrieved_benchmarks: List[Dict[str, Any]],
) -> str:
    if not clause_found:
        return "clause_not_found"

    top5 = retrieved_benchmarks[:5]
    eligible = [item for item in retrieved_benchmarks if item.get("citation_eligible")]
    expected_families = set(expected_benchmark_clause_types or [])
    acceptable_ids = set(acceptable_benchmark_ids or [])

    if any(item.get("citation_eligible") and item.get("contract_type") != expected_contract_type for item in retrieved_benchmarks):
        return "cross_contract_type_result"
    if predicted_clause_type != expected_clause_type:
        return "classifier_mismatch"
    if clause_type_confidence < CLAUSE_TYPE_CONFIDENCE_THRESHOLD:
        return "classifier_low_confidence"
    if acceptable_ids and not any(_benchmark_id(item) in acceptable_ids for item in top5):
        return "expected_benchmark_missing_top5"
    if expected_families and not any(item.get("clause_type") in expected_families for item in top5):
        return "expected_clause_type_missing_top5"
    if not eligible:
        if retrieved_benchmarks and all(item.get("relevance_reason") == "below_similarity_threshold" for item in retrieved_benchmarks):
            return "below_threshold_only"
        if expected_families and not any(item.get("clause_type") in expected_families for item in retrieved_benchmarks):
            return "benchmark_gap"
        return "no_eligible_benchmark"
    return "pass"


def _load_document_clauses(path: Path) -> tuple[str, List[Dict[str, Any]]]:
    text = clean_extracted_text(extract_text_from_pdf(path.read_bytes()))
    return text, split_clauses_structured(text)


def audit_labeled_case(
    *,
    document: Dict[str, Any],
    case: Dict[str, Any],
    clauses: List[Dict[str, Any]],
    retrieve_fn: Callable[..., List[Dict[str, Any]]] = retrieve_benchmarks,
) -> Dict[str, Any]:
    clause = find_clause(clauses, case)
    expected_contract_type = document["expected_contract_type"]

    if clause is None:
        return {
            "case_id": case["case_id"],
            "document_id": document["document_id"],
            "clause_found": False,
            "expected_contract_type": expected_contract_type,
            "expected_clause_type": case["expected_clause_type"],
            "failure_reason": "clause_not_found",
            "passed": False,
            "top_benchmarks": [],
        }

    text = _clause_text(clause)
    classifier = classify_clause_type(text, expected_contract_type)
    results = retrieve_fn(
        text,
        k=10,
        contract_type=expected_contract_type,
        clause_type=classifier.get("predicted_clause_type"),
        clause_type_confidence=classifier.get("clause_type_confidence", 0.0),
    )
    top_benchmarks = [summarize_benchmark(item) for item in results[:10]]
    failure_reason = determine_failure_reason(
        clause_found=True,
        expected_contract_type=expected_contract_type,
        expected_clause_type=case["expected_clause_type"],
        expected_benchmark_clause_types=case.get("expected_benchmark_clause_types", []),
        acceptable_benchmark_ids=case.get("acceptable_benchmark_ids", []),
        predicted_clause_type=classifier.get("predicted_clause_type"),
        clause_type_confidence=float(classifier.get("clause_type_confidence") or 0),
        retrieved_benchmarks=top_benchmarks,
    )

    return {
        "case_id": case["case_id"],
        "document_id": document["document_id"],
        "clause_found": True,
        "clause_number": clause.get("clause_number"),
        "clause_preview": _clause_preview(text),
        "expected_contract_type": expected_contract_type,
        "expected_clause_type": case["expected_clause_type"],
        "expected_benchmark_clause_types": case.get("expected_benchmark_clause_types", []),
        "acceptable_benchmark_ids": case.get("acceptable_benchmark_ids", []),
        "predicted_clause_type": classifier.get("predicted_clause_type"),
        "clause_type_confidence": classifier.get("clause_type_confidence", 0.0),
        "clause_type_matched_terms": classifier.get("clause_type_matched_terms", []),
        "eligible_benchmark_count": sum(1 for item in top_benchmarks if item["citation_eligible"]),
        "citation_suppressed": bool(top_benchmarks and not any(item["citation_eligible"] for item in top_benchmarks)),
        "top_benchmarks": top_benchmarks,
        "failure_reason": failure_reason,
        "passed": failure_reason == "pass",
    }


def audit_full_document(
    *,
    document: Dict[str, Any],
    clauses: List[Dict[str, Any]],
    retrieve_fn: Callable[..., List[Dict[str, Any]]] = retrieve_benchmarks,
) -> List[Dict[str, Any]]:
    rows = []
    expected_contract_type = document["expected_contract_type"]
    for clause in clauses:
        text = _clause_text(clause)
        classifier = classify_clause_type(text, expected_contract_type)
        results = retrieve_fn(
            text,
            k=5,
            contract_type=expected_contract_type,
            clause_type=classifier.get("predicted_clause_type"),
            clause_type_confidence=classifier.get("clause_type_confidence", 0.0),
        )
        top_benchmarks = [summarize_benchmark(item) for item in results[:5]]
        rows.append({
            "document_id": document["document_id"],
            "clause_number": clause.get("clause_number"),
            "clause_preview": _clause_preview(text),
            "predicted_clause_type": classifier.get("predicted_clause_type"),
            "clause_type_confidence": classifier.get("clause_type_confidence", 0.0),
            "clause_type_matched_terms": classifier.get("clause_type_matched_terms", []),
            "eligible_benchmark_count": sum(1 for item in top_benchmarks if item["citation_eligible"]),
            "citation_suppressed": bool(top_benchmarks and not any(item["citation_eligible"] for item in top_benchmarks)),
            "top_benchmarks": top_benchmarks,
        })
    return rows


def summarize_report(labeled_rows: List[Dict[str, Any]], full_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    failure_counts: Dict[str, int] = {}
    for row in labeled_rows:
        failure_counts[row["failure_reason"]] = failure_counts.get(row["failure_reason"], 0) + 1

    eligible = [
        benchmark
        for row in labeled_rows
        for benchmark in row.get("top_benchmarks", [])
        if benchmark.get("citation_eligible")
    ]
    return {
        "labeled_case_count": len(labeled_rows),
        "labeled_pass_count": sum(1 for row in labeled_rows if row.get("passed")),
        "full_document_clause_count": len(full_rows),
        "failure_counts": failure_counts,
        "cross_contract_type_eligible_count": sum(
            1
            for row in labeled_rows
            for benchmark in row.get("top_benchmarks", [])
            if benchmark.get("citation_eligible") and benchmark.get("contract_type") != row.get("expected_contract_type")
        ),
        "below_threshold_eligible_count": sum(
            1
            for benchmark in eligible
            if float(benchmark.get("similarity") or 0) < 0.70
        ),
    }


def run_audit(
    *,
    fixture: Optional[List[Dict[str, Any]]] = None,
    retrieve_fn: Callable[..., List[Dict[str, Any]]] = retrieve_benchmarks,
) -> Dict[str, Any]:
    documents = fixture or load_audit_fixture()
    labeled_rows: List[Dict[str, Any]] = []
    full_rows: List[Dict[str, Any]] = []
    document_summaries = []

    for document in documents:
        path = repo_root / document["path"]
        text, clauses = _load_document_clauses(path)
        detection = detect_contract_type(clauses)
        document_summaries.append({
            "document_id": document["document_id"],
            "path": document["path"],
            "expected_contract_type": document["expected_contract_type"],
            "detected_contract_type": detection.get("detected_contract_type"),
            "contract_type_confidence": detection.get("contract_type_confidence"),
            "top_level_clause_count": len(clauses),
            "parsed_section_count": sum(clause.get("parsed_section_count", 1) for clause in clauses),
            "text_char_count": len(text),
        })

        for case in document["cases"]:
            labeled_rows.append(audit_labeled_case(
                document=document,
                case=case,
                clauses=clauses,
                retrieve_fn=retrieve_fn,
            ))
        full_rows.extend(audit_full_document(
            document=document,
            clauses=clauses,
            retrieve_fn=retrieve_fn,
        ))

    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "thresholds": {
            "citation_similarity": 0.70,
            "clause_type_confidence": CLAUSE_TYPE_CONFIDENCE_THRESHOLD,
        },
        "documents": document_summaries,
        "summary": summarize_report(labeled_rows, full_rows),
        "labeled_cases": labeled_rows,
        "full_document_diagnostics": full_rows,
    }
    return report


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Retriever Audit Report",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        "## Summary",
        "",
    ]
    summary = report["summary"]
    lines.extend([
        f"- Labeled cases: `{summary['labeled_case_count']}`",
        f"- Passed labeled cases: `{summary['labeled_pass_count']}`",
        f"- Full-document clauses audited: `{summary['full_document_clause_count']}`",
        f"- Cross-contract eligible citations: `{summary['cross_contract_type_eligible_count']}`",
        f"- Below-threshold eligible citations: `{summary['below_threshold_eligible_count']}`",
        "",
        "### Failure Counts",
        "",
    ])
    for reason in sorted(FAILURE_REASONS):
        lines.append(f"- `{reason}`: `{summary['failure_counts'].get(reason, 0)}`")

    lines.extend(["", "## Documents", ""])
    for document in report["documents"]:
        lines.append(
            "- `{document_id}`: expected `{expected_contract_type}`, detected `{detected_contract_type}` "
            "({top_level_clause_count} top-level clauses, {parsed_section_count} parsed sections)".format(**document)
        )

    lines.extend(["", "## Labeled Cases", ""])
    for row in report["labeled_cases"]:
        status = "PASS" if row["passed"] else f"FAIL: {row['failure_reason']}"
        lines.extend([
            f"### {row['case_id']} - {status}",
            "",
            f"- Document: `{row['document_id']}`",
            f"- Clause: `{row.get('clause_number', 'not found')}`",
            f"- Expected type: `{row['expected_clause_type']}`",
            f"- Predicted type: `{row.get('predicted_clause_type')}` (`{row.get('clause_type_confidence', 0)}`)",
            f"- Eligible benchmarks: `{row.get('eligible_benchmark_count', 0)}`",
            f"- Preview: {row.get('clause_preview', '')}",
            "",
            "| Rank | Benchmark | Type | Risk | Similarity | Eligible | Reason | Scope |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ])
        for idx, benchmark in enumerate(row.get("top_benchmarks", [])[:10], 1):
            lines.append(
                "| {rank} | `{benchmark_id}` | `{clause_type}` | `{risk_level}` | `{similarity}` | `{eligible}` | `{reason}` | `{scope}` |".format(
                    rank=idx,
                    benchmark_id=benchmark.get("benchmark_id"),
                    clause_type=benchmark.get("clause_type"),
                    risk_level=benchmark.get("risk_level"),
                    similarity=benchmark.get("similarity"),
                    eligible="yes" if benchmark.get("citation_eligible") else "no",
                    reason=benchmark.get("relevance_reason"),
                    scope=benchmark.get("retrieval_scope"),
                )
            )
        lines.append("")

    lines.extend(["", "## Full-Document Diagnostics", ""])
    lines.append("| Document | Clause | Predicted Type | Confidence | Eligible | Suppressed | Top Benchmarks | Preview |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for row in report["full_document_diagnostics"]:
        top = ", ".join(
            f"{benchmark.get('benchmark_id')}:{benchmark.get('clause_type')}:{benchmark.get('similarity')}"
            for benchmark in row.get("top_benchmarks", [])[:5]
        )
        lines.append(
            "| `{document}` | `{clause}` | `{ctype}` | `{confidence}` | `{eligible}` | `{suppressed}` | {top} | {preview} |".format(
                document=row["document_id"],
                clause=row.get("clause_number"),
                ctype=row.get("predicted_clause_type"),
                confidence=row.get("clause_type_confidence"),
                eligible=row.get("eligible_benchmark_count"),
                suppressed="yes" if row.get("citation_suppressed") else "no",
                top=top.replace("|", "\\|"),
                preview=row.get("clause_preview", "").replace("|", "\\|"),
            )
        )
    return "\n".join(lines) + "\n"


def write_reports(report: Dict[str, Any], output_dir: Optional[Path] = None) -> Dict[str, str]:
    out_dir = output_dir or reports_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "retriever_audit.json"
    markdown_path = out_dir / "retriever_audit.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(markdown_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit clause classifier and benchmark retrieval without LLM calls")
    parser.add_argument("--json", action="store_true", help="Print JSON report to stdout")
    parser.add_argument("--markdown", action="store_true", help="Print Markdown report to stdout")
    parser.add_argument("--output-dir", type=Path, default=None, help="Directory for generated audit reports")
    args = parser.parse_args()

    try:
        report = run_audit()
        paths = write_reports(report, args.output_dir)
    except Exception as exc:
        print(f"Retriever audit failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, indent=2))
    elif args.markdown:
        print(render_markdown(report))
    else:
        print(json.dumps({"status": "ok", "reports": paths, "summary": report["summary"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
