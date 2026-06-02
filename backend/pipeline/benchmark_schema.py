"""
Benchmark dataset schema utilities for RAG retrieval and evaluation.
"""

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple


SUPPORTED_CONTRACT_TYPES = {"nda", "employment", "vendor"}
SUPPORTED_RISK_LEVELS = {"low", "medium", "high"}
SUPPORTED_SOURCE_TYPES = {"public_template", "sample_contract", "curated"}

REQUIRED_FIELDS = {
    "benchmark_id",
    "contract_type",
    "clause_type",
    "risk_level",
    "clause_text",
    "risk_rule",
    "why_risky",
    "safe_version",
    "source_name",
    "source_type",
    "source_url",
    "source_license_note",
    "jurisdiction",
    "tags",
}


def benchmark_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "benchmarks"


def benchmark_files(directory: Path | None = None) -> List[Path]:
    base = directory or benchmark_dir()
    return sorted(base.glob("*_benchmarks.json"))


def load_benchmarks(directory: Path | None = None) -> List[Dict[str, Any]]:
    benchmarks: List[Dict[str, Any]] = []
    for path in benchmark_files(directory):
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, list):
            raise ValueError(f"{path} must contain a JSON array")
        benchmarks.extend(data)
    return benchmarks


def validate_benchmarks(benchmarks: List[Dict[str, Any]]) -> Tuple[List[str], Dict[str, Any]]:
    errors: List[str] = []
    ids = set()
    by_contract_type: Dict[str, Counter] = defaultdict(Counter)

    for index, item in enumerate(benchmarks):
        prefix = item.get("benchmark_id") or f"index:{index}"
        missing = sorted(REQUIRED_FIELDS - set(item))
        if missing:
            errors.append(f"{prefix}: missing fields {', '.join(missing)}")
            continue

        benchmark_id = str(item["benchmark_id"])
        if benchmark_id in ids:
            errors.append(f"{benchmark_id}: duplicate benchmark_id")
        ids.add(benchmark_id)

        contract_type = item["contract_type"]
        risk_level = item["risk_level"]
        source_type = item["source_type"]

        if contract_type not in SUPPORTED_CONTRACT_TYPES:
            errors.append(f"{benchmark_id}: invalid contract_type {contract_type}")
        if risk_level not in SUPPORTED_RISK_LEVELS:
            errors.append(f"{benchmark_id}: invalid risk_level {risk_level}")
        if source_type not in SUPPORTED_SOURCE_TYPES:
            errors.append(f"{benchmark_id}: invalid source_type {source_type}")
        if not isinstance(item["tags"], list) or not item["tags"]:
            errors.append(f"{benchmark_id}: tags must be a non-empty list")

        for text_field in [
            "clause_type",
            "clause_text",
            "risk_rule",
            "why_risky",
            "safe_version",
            "source_name",
            "source_url",
            "source_license_note",
            "jurisdiction",
        ]:
            if not str(item[text_field]).strip():
                errors.append(f"{benchmark_id}: {text_field} cannot be blank")

        if contract_type in SUPPORTED_CONTRACT_TYPES and risk_level in SUPPORTED_RISK_LEVELS:
            by_contract_type[contract_type][risk_level] += 1

    summary = {
        "total": len(benchmarks),
        "by_contract_type": {
            contract_type: dict(counter)
            for contract_type, counter in sorted(by_contract_type.items())
        },
        "metadata_complete": len(errors) == 0,
    }
    return errors, summary


def format_benchmark_for_embedding(benchmark: Dict[str, Any]) -> str:
    return "\n".join([
        f"Contract type: {benchmark.get('contract_type', '')}",
        f"Clause type: {benchmark.get('clause_type', '')}",
        f"Risk level: {benchmark.get('risk_level', '')}",
        f"Clause: {benchmark.get('clause_text', '')}",
        f"Risk rule: {benchmark.get('risk_rule', '')}",
        f"Why risky: {benchmark.get('why_risky', '')}",
        f"Safer version: {benchmark.get('safe_version', '')}",
        f"Tags: {', '.join(benchmark.get('tags', []))}",
    ])
