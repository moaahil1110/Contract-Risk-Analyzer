"""Reusable contract analysis pipeline used by Celery workers."""

import asyncio
import logging
import time
import traceback
from typing import Any, Dict, List, Optional

from api.routes.upload import contract_store
from core.status import (
    CONTRACT_STATUS_ANALYSING,
    CONTRACT_STATUS_CLAUSES_EXTRACTED,
    CONTRACT_STATUS_COMPLETE,
    CONTRACT_STATUS_EXTRACTING,
    CONTRACT_STATUS_FAILED,
    CONTRACT_STATUS_RETRIEVING_BENCHMARKS,
    CONTRACT_STATUS_SAVING_RESULTS,
    JOB_STATUS_FAILED,
    JOB_STATUS_RUNNING,
    JOB_STATUS_SUCCEEDED,
)
from core.structured_logging import log_event
from db.queries import (
    get_contract,
    save_clause_analyses_batch,
    update_analysis_job,
    update_contract_progress,
    update_contract_results,
    update_contract_type_metadata,
)
from db.supabase_client import is_supabase_configured
from pipeline.clause_classifier import classify_clause_type
from pipeline.clause_splitter import clean_extracted_text, split_clauses
from pipeline.llm_analyser import analyse_clause
from pipeline.pdf_parser import extract_text_from_pdf
from pipeline.rag_engine import retrieve_benchmarks
from pipeline.scorer import calculate_health_score
from services.storage import load_contract_file

logger = logging.getLogger(__name__)

SUPPORTED_CONTRACT_TYPES = {"nda", "employment", "vendor", "other"}
DETECTION_CONFIDENCE_THRESHOLD = 0.55


import os

LLM_PROVIDER_FAILURE_WARNING_THRESHOLD = float(os.getenv("LLM_PROVIDER_FAILURE_WARNING_THRESHOLD", "0.5"))


def _provider_exhaustion_warning(analyzed_clauses: List[Dict[str, Any]]) -> Optional[str]:
    if not analyzed_clauses:
        return None
    fallback_count = sum(1 for c in analyzed_clauses if c.get("provider_used") == "fallback")
    if fallback_count / len(analyzed_clauses) > LLM_PROVIDER_FAILURE_WARNING_THRESHOLD:
        return "Provider quota exhausted; rerun later."
    return None

class NonRetryablePipelineError(Exception):
    """Raised when retrying the worker would not fix the input."""


def _extract_clause_text(clause: Any) -> str:
    if isinstance(clause, dict):
        return str(clause.get("text", "") or clause.get("original_text", "") or clause.get("content", ""))
    return str(clause)


def _clause_hierarchy_metadata(clause: Any, index: int) -> Dict[str, Any]:
    if not isinstance(clause, dict):
        return {
            "clause_number": str(index + 1),
            "parent_clause_number": None,
            "clause_level": 1,
            "section_type": "clause",
            "is_scored": True,
            "subclauses": [],
            "parsed_section_count": 1,
        }
    return {
        "clause_number": clause.get("clause_number") or str(index + 1),
        "parent_clause_number": clause.get("parent_clause_number"),
        "clause_level": clause.get("clause_level", 1),
        "section_type": clause.get("section_type", "clause"),
        "is_scored": clause.get("is_scored", True),
        "subclauses": clause.get("subclauses", []),
        "parsed_section_count": clause.get("parsed_section_count", 1),
    }


def _normalize_contract_type(contract_type: Optional[str]) -> str:
    normalized = (contract_type or "other").lower().strip()
    return normalized if normalized in SUPPORTED_CONTRACT_TYPES else "other"


def detect_contract_type(clauses: List[Any]) -> Dict[str, Any]:
    combined_text = " ".join(_extract_clause_text(clause) for clause in clauses).lower()
    lead_text = combined_text[:2500]
    scores = {"nda": 0, "employment": 0, "vendor": 0}

    title_markers = {
        "nda": [
            "non-disclosure agreement",
            "nondisclosure agreement",
            "confidentiality agreement",
            "mutual non-disclosure",
        ],
        "employment": [
            "employment contract",
            "employment agreement",
            "offer letter",
        ],
        "vendor": [
            "service agreement",
            "services agreement",
            "vendor agreement",
            "master services agreement",
            "statement of work",
        ],
    }

    for contract_type, markers in title_markers.items():
        for marker in markers:
            if marker in lead_text:
                scores[contract_type] += 120
            elif marker in combined_text:
                scores[contract_type] += 40

    weighted_keywords = {
        "nda": {
            "confidential information": 4,
            "non-disclosure": 8,
            "disclosing party": 5,
            "receiving party": 5,
            "trade secret": 4,
            "proprietary information": 3,
            "permitted purpose": 3,
            "confidential": 1,
        },
        "employment": {
            "base salary": 5,
            "compensation": 3,
            "benefits": 3,
            "severance": 4,
            "at-will": 5,
            "non-compete": 4,
            "non-solicit": 4,
            "termination": 2,
            "employment": 1,
            "employee": 1,
            "employer": 1,
        },
        "vendor": {
            "statement of work": 5,
            "deliverables": 4,
            "invoice": 4,
            "payment terms": 4,
            "warranty": 3,
            "indemnification": 3,
            "services": 1,
            "contractor": 1,
            "vendor": 1,
            "customer": 1,
        },
    }

    for contract_type, keywords in weighted_keywords.items():
        for keyword, weight in keywords.items():
            scores[contract_type] += combined_text.count(keyword) * weight

    max_score = max(scores.values())
    if max_score == 0:
        return {
            "detected_contract_type": "other",
            "contract_type_confidence": 0.0,
            "scores": scores,
        }

    detected_type = max(scores, key=scores.get)
    total_score = sum(scores.values())
    return {
        "detected_contract_type": detected_type,
        "contract_type_confidence": round(max_score / total_score, 4) if total_score else 0.0,
        "scores": scores,
    }


def resolve_contract_type(selected_contract_type: Optional[str], detection: Dict[str, Any]) -> Dict[str, Any]:
    selected = _normalize_contract_type(selected_contract_type)
    detected = _normalize_contract_type(detection.get("detected_contract_type"))
    confidence = float(detection.get("contract_type_confidence") or 0.0)

    if detected != "other" and confidence >= DETECTION_CONFIDENCE_THRESHOLD:
        effective = detected
    elif selected != "other":
        effective = selected
    else:
        effective = detected

    return {
        "selected_contract_type": selected,
        "detected_contract_type": detected,
        "contract_type_confidence": confidence,
        "contract_type": effective,
        "contract_type_conflict": (
            selected != "other"
            and detected != "other"
            and selected != detected
            and confidence > 0
        ),
    }


async def _load_contract_record(contract_id: str) -> Optional[Dict[str, Any]]:
    if is_supabase_configured():
        record = await get_contract(contract_id)
        if record:
            return record
    return contract_store.get(contract_id)


async def _set_progress(
    contract_id: str,
    status: str,
    progress: int,
    message: str,
    error: Optional[str] = None,
) -> None:
    await update_contract_progress(contract_id, status, progress, message, error)
    if contract_id in contract_store:
        contract_store[contract_id].update({
            "status": status,
            "progress_percent": progress,
            "status_message": message,
            "error_message": error,
        })


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _eligible_benchmarks(benchmarks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [benchmark for benchmark in benchmarks if benchmark.get("citation_eligible") is True]


def _retrieval_quality(benchmarks: List[Dict[str, Any]]) -> str:
    eligible_count = len(_eligible_benchmarks(benchmarks))
    if eligible_count >= 3:
        return "strong"
    if eligible_count >= 1:
        return "partial"
    if benchmarks:
        return "none"
    return "none"


def _enforce_citation_policy(
    result: Dict[str, Any],
    eligible_benchmarks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    eligible_ids = {
        str(benchmark.get("benchmark_id") or benchmark.get("id"))
        for benchmark in eligible_benchmarks
    }
    original_cited = [str(benchmark_id) for benchmark_id in (result.get("cited_benchmark_ids") or [])]
    cited = [
        str(benchmark_id)
        for benchmark_id in original_cited
        if str(benchmark_id) in eligible_ids
    ]
    result["cited_benchmark_ids"] = cited
    if not eligible_ids:
        result["risk_rule_applied"] = ""
        result["evidence_summary"] = "No direct benchmark met the relevance threshold."
        result["benchmark_alignment"] = "none"
        return result
    if len(cited) < len(original_cited):
        result["benchmark_alignment"] = "partial"
    return result


async def run_contract_analysis(
    contract_id: str,
    job_id: Optional[str] = None,
    celery_task_id: Optional[str] = None,
    attempt: int = 1,
) -> Dict[str, Any]:
    timings: Dict[str, Any] = {}
    total_start = time.perf_counter()
    record = await _load_contract_record(contract_id)
    if not record:
        raise NonRetryablePipelineError(f"Contract not found: {contract_id}")

    user_id = record.get("user_id")
    if job_id:
        await update_analysis_job(
            job_id,
            JOB_STATUS_RUNNING,
            stage=CONTRACT_STATUS_EXTRACTING,
            attempts=attempt,
            celery_task_id=celery_task_id,
        )

    try:
        log_event(logger, logging.INFO, "analysis_started", contract_id=contract_id, user_id=user_id, job_id=job_id, celery_task_id=celery_task_id)

        await _set_progress(contract_id, CONTRACT_STATUS_EXTRACTING, 10, "Extracting text from PDF")
        extraction_start = time.perf_counter()
        if record.get("text") and record.get("clauses"):
            text = str(record["text"])
            clauses = record["clauses"]
        else:
            storage_path = record.get("storage_path")
            if not storage_path:
                raise NonRetryablePipelineError("Uploaded PDF storage path is missing")
            file_bytes = await load_contract_file(storage_path)
            text = clean_extracted_text(extract_text_from_pdf(file_bytes))
            if not text or not text.strip():
                raise NonRetryablePipelineError("No text could be extracted from the PDF")
            clauses = await split_clauses(text)

        timings["extraction_ms"] = _elapsed_ms(extraction_start)
        if not clauses:
            raise NonRetryablePipelineError("No clauses found in contract")
        parsed_section_count = sum(
            _clause_hierarchy_metadata(clause, idx).get("parsed_section_count", 1)
            for idx, clause in enumerate(clauses)
        )

        if contract_id in contract_store:
            contract_store[contract_id]["text"] = text
            contract_store[contract_id]["clauses"] = clauses
            contract_store[contract_id]["top_level_clause_count"] = len(clauses)
            contract_store[contract_id]["parsed_section_count"] = parsed_section_count

        await _set_progress(
            contract_id,
            CONTRACT_STATUS_CLAUSES_EXTRACTED,
            25,
            f"Extracted {len(clauses)} top-level clauses ({parsed_section_count} parsed sections)",
        )
        if job_id:
            await update_analysis_job(
                job_id,
                JOB_STATUS_RUNNING,
                stage=CONTRACT_STATUS_CLAUSES_EXTRACTED,
                attempts=attempt,
                timings=timings,
                metadata={"clause_count": len(clauses), "parsed_section_count": parsed_section_count},
            )

        detection = detect_contract_type(clauses)
        selected_contract_type = record.get("selected_contract_type") or record.get("contract_type")
        contract_type_metadata = resolve_contract_type(selected_contract_type, detection)
        contract_type = contract_type_metadata["contract_type"]
        await update_contract_type_metadata(contract_id, contract_type_metadata)
        if contract_id in contract_store:
            contract_store[contract_id].update(contract_type_metadata)

        analyzed_clauses = []
        retrieval_total_ms = 0
        llm_total_ms = 0

        for idx, clause in enumerate(clauses):
            clause_text = _extract_clause_text(clause)
            hierarchy = _clause_hierarchy_metadata(clause, idx)
            progress_base = 30 + int((idx / max(len(clauses), 1)) * 55)

            await _set_progress(
                contract_id,
                CONTRACT_STATUS_RETRIEVING_BENCHMARKS,
                progress_base,
                f"Retrieving benchmarks for clause {idx + 1} of {len(clauses)}",
            )
            retrieval_start = time.perf_counter()
            clause_type_metadata = classify_clause_type(clause_text, contract_type)
            benchmarks = retrieve_benchmarks(
                clause_text,
                k=3,
                contract_type=contract_type,
                clause_type=clause_type_metadata.get("predicted_clause_type"),
                clause_type_confidence=clause_type_metadata.get("clause_type_confidence", 0.0),
            )
            eligible = _eligible_benchmarks(benchmarks)
            retrieval_latency_ms = _elapsed_ms(retrieval_start)
            retrieval_total_ms += retrieval_latency_ms

            await _set_progress(
                contract_id,
                CONTRACT_STATUS_ANALYSING,
                min(progress_base + 2, 85),
                f"Analysing clause {idx + 1} of {len(clauses)}",
            )
            llm_start = time.perf_counter()
            try:
                result = await analyse_clause(
                    clause_text=clause_text,
                    benchmarks=eligible,
                    contract_type=contract_type,
                )
                result = _enforce_citation_policy(result, eligible)
            except Exception as exc:
                result = {
                    "clause_title": f"Clause {idx + 1}",
                    "risk_level": "unknown",
                    "risk_score": None,
                    "risk_reason": f"Analysis failed: {str(exc)}",
                    "plain_english": "This clause could not be analyzed.",
                    "key_concerns": ["Analysis error occurred"],
                    "suggested_fix": "Please retry the analysis.",
                    "analysis_status": "failed",
                    "retry_count": 0,
                    "error_message": str(exc),
                    "provider_used": "error",
                    "cited_benchmark_ids": [],
                    "risk_rule_applied": "",
                    "evidence_summary": "No benchmark-supported analysis was produced.",
                    "benchmark_alignment": "none",
                }
            llm_latency_ms = _elapsed_ms(llm_start)
            llm_total_ms += llm_latency_ms

            retrieval_quality = _retrieval_quality(benchmarks)
            clause_result = {
                "id": f"{contract_id}_clause_{idx}",
                "clause_index": idx,
                "clause_title": result.get("clause_title", f"Clause {idx + 1}"),
                "original_text": clause_text,
                "risk_level": result.get("risk_level", "unknown"),
                "risk_score": result.get("risk_score"),
                "risk_reason": result.get("risk_reason", ""),
                "plain_english": result.get("plain_english", ""),
                "key_concerns": result.get("key_concerns", []),
                "suggested_fix": result.get("suggested_fix", ""),
                "analysis_status": result.get("analysis_status", "success"),
                "retry_count": result.get("retry_count", 0),
                "error_message": result.get("error_message"),
                "provider_used": result.get("provider_used", "unknown"),
                "retrieved_benchmarks": benchmarks,
                "cited_benchmark_ids": result.get("cited_benchmark_ids", []),
                "risk_rule_applied": result.get("risk_rule_applied", ""),
                "evidence_summary": result.get("evidence_summary", ""),
                "benchmark_alignment": result.get("benchmark_alignment", "none"),
                "retrieval_latency_ms": retrieval_latency_ms,
                "llm_latency_ms": llm_latency_ms,
                "predicted_clause_type": clause_type_metadata.get("predicted_clause_type"),
                "clause_type_confidence": clause_type_metadata.get("clause_type_confidence", 0.0),
                "clause_type_matched_terms": clause_type_metadata.get("clause_type_matched_terms", []),
                "retrieval_quality": retrieval_quality,
                "eligible_benchmark_count": len(eligible),
                "citation_suppressed": bool(benchmarks and not eligible),
                **hierarchy,
            }
            analyzed_clauses.append(clause_result)

            log_event(
                logger,
                logging.INFO,
                "clause_analyzed",
                contract_id=contract_id,
                user_id=user_id,
                job_id=job_id,
                celery_task_id=celery_task_id,
                clause_index=idx,
                contract_type=contract_type,
                provider_used=clause_result["provider_used"],
                retrieval_latency_ms=retrieval_latency_ms,
                llm_latency_ms=llm_latency_ms,
                retry_count=clause_result["retry_count"],
            )

        timings["retrieval_total_ms"] = retrieval_total_ms
        timings["llm_total_ms"] = llm_total_ms

        await _set_progress(contract_id, CONTRACT_STATUS_SAVING_RESULTS, 90, "Saving analysis results")
        saving_start = time.perf_counter()
        health = calculate_health_score(analyzed_clauses)
        health["top_level_clause_count"] = len(analyzed_clauses)
        health["parsed_section_count"] = parsed_section_count
        await save_clause_analyses_batch(contract_id, analyzed_clauses)
        await update_contract_results(
            contract_id=contract_id,
            health_data=health,
            risk_counts=health.get("risk_counts", {"high": 0, "medium": 0, "low": 0}),
            total_clauses=len(analyzed_clauses),
            parsed_section_count=parsed_section_count,
        )
        timings["saving_ms"] = _elapsed_ms(saving_start)
        timings["total_ms"] = _elapsed_ms(total_start)

        warning = _provider_exhaustion_warning(analyzed_clauses)
        if warning:
            logger.warning("Contract %s: %s", contract_id, warning)

        if contract_id in contract_store:
            contract_store[contract_id].update({
                "status": CONTRACT_STATUS_COMPLETE,
                "progress_percent": 100,
                "status_message": "Analysis complete",
                "clauses": clauses,
                "analysis": analyzed_clauses,
                "health": health,
                "warning": warning,
                "top_level_clause_count": len(analyzed_clauses),
                "parsed_section_count": parsed_section_count,
                **contract_type_metadata,
            })

        if job_id:
            await update_analysis_job(
                job_id,
                JOB_STATUS_SUCCEEDED,
                stage=CONTRACT_STATUS_COMPLETE,
                attempts=attempt,
                timings=timings,
                metadata={
                    "clause_count": len(clauses),
                    "parsed_section_count": parsed_section_count,
                    "health": health,
                    "warning": warning,
                },
            )

        log_event(logger, logging.INFO, "analysis_complete", contract_id=contract_id, user_id=user_id, job_id=job_id, timings=timings)
        return {
            "contract_id": contract_id,
            "status": CONTRACT_STATUS_COMPLETE,
            "clauses": analyzed_clauses,
            "health": health,
            "warning": warning,
            **contract_type_metadata,
        }

    except NonRetryablePipelineError as exc:
        await _set_progress(contract_id, CONTRACT_STATUS_FAILED, 100, "Analysis failed", str(exc))
        if job_id:
            await update_analysis_job(
                job_id,
                JOB_STATUS_FAILED,
                stage=CONTRACT_STATUS_FAILED,
                attempts=attempt,
                timings={**timings, "total_ms": _elapsed_ms(total_start)},
                error=str(exc),
            )
        if contract_id in contract_store:
            contract_store[contract_id]["error"] = str(exc)
        log_event(logger, logging.ERROR, "analysis_failed", contract_id=contract_id, user_id=user_id, job_id=job_id, error_type=type(exc).__name__, error_message=str(exc))
        raise
    except Exception as exc:
        await _set_progress(contract_id, CONTRACT_STATUS_FAILED, 100, "Analysis failed", str(exc))
        if job_id:
            await update_analysis_job(
                job_id,
                JOB_STATUS_FAILED,
                stage=CONTRACT_STATUS_FAILED,
                attempts=attempt,
                timings={**timings, "total_ms": _elapsed_ms(total_start)},
                error=str(exc),
            )
        if contract_id in contract_store:
            contract_store[contract_id]["error"] = str(exc)
        log_event(logger, logging.ERROR, "analysis_failed", contract_id=contract_id, user_id=user_id, job_id=job_id, error_type=type(exc).__name__, error_message=str(exc), traceback=traceback.format_exc())
        raise


def run_contract_analysis_sync(
    contract_id: str,
    job_id: Optional[str] = None,
    celery_task_id: Optional[str] = None,
    attempt: int = 1,
) -> Dict[str, Any]:
    return asyncio.run(run_contract_analysis(contract_id, job_id, celery_task_id, attempt))
