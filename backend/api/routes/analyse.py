"""
Analysis API Route (Week 2 & 3)
Full analysis pipeline with RAG, LLM, and health scoring.
Week 3: Added Supabase integration for persistence
"""

import logging
import uuid
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException

from api.routes.upload import contract_store
from core.status import CONTRACT_STATUS_COMPLETE, CONTRACT_STATUS_FAILED, CONTRACT_STATUS_QUEUED
from db.queries import (
    create_analysis_job,
    get_active_analysis_job,
    get_contract_with_clauses,
    get_contract,
    update_contract_progress,
)
from db.supabase_client import is_supabase_configured
from services.analysis_pipeline import detect_contract_type, resolve_contract_type
from services.job_queue import create_local_job, enqueue_contract_analysis, get_local_active_job

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory store for analysis results (fallback when Supabase is not configured)
analysis_results: Dict[str, Any] = {}

def _progress_response(contract_id: str, record: Dict[str, Any], job: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    status = record.get("status", "unknown")
    return {
        "contract_id": contract_id,
        "job_id": job.get("id") if job else None,
        "task_id": job.get("celery_task_id") if job else None,
        "status": status,
        "progress_percent": record.get("progress_percent", 100 if status == CONTRACT_STATUS_COMPLETE else 0),
        "status_message": record.get("status_message") or record.get("message") or status,
        "current_stage": job.get("current_stage") if job else status,
        "has_results": status == CONTRACT_STATUS_COMPLETE,
        "error_message": record.get("error_message") or record.get("error"),
        "total_clauses": record.get("total_clauses") or len(record.get("clauses") or []),
    }


@router.post("/analyse/{contract_id}")
async def start_analysis(contract_id: str):
    """
    Start analysis for a contract.
    Returns immediately, analysis runs in background.
    """
    record = None
    if is_supabase_configured():
        record = await get_contract(contract_id)
    if not record:
        record = contract_store.get(contract_id)
    if not record:
        raise HTTPException(status_code=404, detail="Contract not found")

    if record.get("status") == CONTRACT_STATUS_FAILED:
        raise HTTPException(status_code=400, detail=f"Upload failed: {record.get('error')}")

    if record.get("status") == CONTRACT_STATUS_COMPLETE:
        return {
            "contract_id": contract_id,
            "status": CONTRACT_STATUS_COMPLETE,
            "has_results": True,
            "message": "Contract has already been analyzed",
        }

    active_job = await get_active_analysis_job(contract_id)
    if not active_job:
        active_job = get_local_active_job(contract_id)
    if active_job:
        return {
            "contract_id": contract_id,
            "job_id": active_job.get("id"),
            "task_id": active_job.get("celery_task_id"),
            "status": record.get("status", CONTRACT_STATUS_QUEUED),
            "message": "Analysis is already queued or running",
        }

    task_id = str(uuid.uuid4())
    job = await create_analysis_job(contract_id, task_id)
    if not job:
        job = create_local_job(contract_id, task_id)

    await update_contract_progress(
        contract_id,
        CONTRACT_STATUS_QUEUED,
        0,
        "Analysis queued",
    )
    if contract_id in contract_store:
        contract_store[contract_id].update({
            "status": CONTRACT_STATUS_QUEUED,
            "progress_percent": 0,
            "status_message": "Analysis queued",
        })

    try:
        task_id = enqueue_contract_analysis(contract_id, task_id)
    except Exception as exc:
        await update_contract_progress(contract_id, CONTRACT_STATUS_FAILED, 100, "Failed to enqueue analysis", str(exc))
        if contract_id in contract_store:
            contract_store[contract_id].update({
                "status": CONTRACT_STATUS_FAILED,
                "progress_percent": 100,
                "status_message": "Failed to enqueue analysis",
                "error_message": str(exc),
            })
        raise HTTPException(status_code=503, detail=f"Failed to enqueue analysis: {str(exc)}")
    
    return {
        "contract_id": contract_id,
        "job_id": job.get("id") if job else None,
        "task_id": task_id,
        "status": CONTRACT_STATUS_QUEUED,
        "message": "Analysis queued",
    }


@router.get("/analyse/{contract_id}")
async def get_analysis(contract_id: str):
    """
    Get full analysis results for a contract.
    
    First checks Supabase if configured, then falls back to in-memory store.
    Returns cached results if analysis is complete, or status if still processing.
    """
    # First, try to get from Supabase (database of truth)
    if is_supabase_configured():
        try:
            db_contract = await get_contract_with_clauses(contract_id)
            if db_contract and db_contract.get("status") == CONTRACT_STATUS_COMPLETE:
                logger.info(f"Returning results from Supabase for contract {contract_id}")
                
                # Build health data from DB record
                health = {
                    "score": db_contract.get("health_score", 0),
                    "grade": db_contract.get("health_grade", "N/A"),
                    "label": db_contract.get("health_label", "Unknown"),
                    "risk_counts": {
                        "high": db_contract.get("high_risk_count", 0),
                        "medium": db_contract.get("medium_risk_count", 0),
                        "low": db_contract.get("low_risk_count", 0),
                    },
                    "total_clauses": db_contract.get("total_clauses", 0),
                    "unknown_count": db_contract.get("unknown_risk_count", 0),
                    "failed_clause_count": db_contract.get("failed_clause_count", 0),
                    "scored_clause_count": db_contract.get("scored_clause_count", 0),
                }
                
                # Transform clauses to response format
                clauses = []
                for clause in db_contract.get("clauses", []):
                    clauses.append({
                        "id": str(clause.get("id", "")),
                        "clause_index": clause.get("clause_index", 0),
                        "clause_title": clause.get("clause_title", ""),
                        "original_text": clause.get("original_text", ""),
                        "risk_level": clause.get("risk_level", "unknown"),
                        "risk_score": clause.get("risk_score"),
                        "risk_reason": clause.get("risk_reason", ""),
                        "plain_english": clause.get("plain_english", ""),
                        "key_concerns": clause.get("key_concerns", []),
                        "suggested_fix": clause.get("suggested_fix", ""),
                        "analysis_status": clause.get("analysis_status", "success"),
                        "retry_count": clause.get("retry_count", 0),
                        "error_message": clause.get("error_message"),
                        "provider_used": clause.get("provider_used"),
                        "retrieved_benchmarks": clause.get("retrieved_benchmarks", []),
                        "cited_benchmark_ids": clause.get("cited_benchmark_ids", []),
                        "risk_rule_applied": clause.get("risk_rule_applied", ""),
                        "evidence_summary": clause.get("evidence_summary", ""),
                        "benchmark_alignment": clause.get("benchmark_alignment", "none"),
                    })
                
                return {
                    "contract_id": contract_id,
                    "filename": db_contract.get("filename", ""),
                    "status": CONTRACT_STATUS_COMPLETE,
                    "contract_type": db_contract.get("contract_type", "unknown"),
                    "selected_contract_type": db_contract.get("selected_contract_type") or db_contract.get("contract_type", "unknown"),
                    "detected_contract_type": db_contract.get("detected_contract_type") or db_contract.get("contract_type", "unknown"),
                    "contract_type_confidence": db_contract.get("contract_type_confidence", 0),
                    "contract_type_conflict": (
                        (db_contract.get("selected_contract_type") or db_contract.get("contract_type"))
                        != (db_contract.get("detected_contract_type") or db_contract.get("contract_type"))
                    ),
                    "health": health,
                    "clauses": clauses,
                    "total_clauses": len(clauses),
                }
            if db_contract:
                active_job = await get_active_analysis_job(contract_id)
                return _progress_response(contract_id, db_contract, active_job)
        except Exception as e:
            logger.warning(f"Failed to get results from Supabase: {e}")
    
    # Fallback to in-memory store
    if contract_id not in contract_store:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    record = contract_store[contract_id]
    
    # Check if analysis is complete
    if contract_id in analysis_results or record.get("status") == CONTRACT_STATUS_COMPLETE:
        result = analysis_results.get(contract_id) or {
            "health": record.get("health"),
            "clauses": record.get("analysis", []),
        }
        return {
            "contract_id": contract_id,
            "filename": record["filename"],
            "status": CONTRACT_STATUS_COMPLETE,
            "contract_type": record.get("contract_type", "unknown"),
            "selected_contract_type": record.get("selected_contract_type", record.get("contract_type", "unknown")),
            "detected_contract_type": record.get("detected_contract_type", record.get("contract_type", "unknown")),
            "contract_type_confidence": record.get("contract_type_confidence", 0),
            "contract_type_conflict": record.get("contract_type_conflict", False),
            "health": result["health"],
            "clauses": result["clauses"],
            "total_clauses": len(result["clauses"]),
        }
    
    # Analysis still in progress or not started
    response = _progress_response(contract_id, record, get_local_active_job(contract_id))
    response["filename"] = record["filename"]
    response["contract_type"] = record.get("contract_type", "unknown")
    response["selected_contract_type"] = record.get("selected_contract_type", record.get("contract_type", "unknown"))
    response["detected_contract_type"] = record.get("detected_contract_type", "unknown")
    response["contract_type_confidence"] = record.get("contract_type_confidence", 0)
    response["contract_type_conflict"] = record.get("contract_type_conflict", False)
    return response


@router.get("/analyse/{contract_id}/status")
async def get_analysis_status(contract_id: str):
    """
    Get just the analysis status (lightweight endpoint for polling).
    """
    # First check Supabase
    if is_supabase_configured():
        try:
            db_contract = await get_contract(contract_id)
            if db_contract:
                active_job = await get_active_analysis_job(contract_id)
                return _progress_response(contract_id, db_contract, active_job)
        except Exception as e:
            logger.debug(f"Failed to get status from Supabase: {e}")
    
    # Fallback to in-memory
    if contract_id not in contract_store:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    record = contract_store[contract_id]
    if contract_id in analysis_results:
        record = {**record, "status": CONTRACT_STATUS_COMPLETE, "progress_percent": 100}
    return _progress_response(contract_id, record, get_local_active_job(contract_id))


@router.get("/analyse/{contract_id}/clauses/{clause_index}")
async def get_clause_detail(contract_id: str, clause_index: int):
    """
    Get detailed analysis for a specific clause.
    """
    # First check in-memory results
    if contract_id in analysis_results:
        result = analysis_results[contract_id]
        if clause_index < 0 or clause_index >= len(result["clauses"]):
            raise HTTPException(status_code=404, detail="Clause not found")
        return result["clauses"][clause_index]
    
    # Fallback to Supabase
    if is_supabase_configured():
        try:
            db_contract = await get_contract_with_clauses(contract_id)
            if db_contract and db_contract.get("clauses"):
                clauses = db_contract["clauses"]
                if clause_index < 0 or clause_index >= len(clauses):
                    raise HTTPException(status_code=404, detail="Clause not found")
                
                clause = clauses[clause_index]
                return {
                    "id": str(clause.get("id", "")),
                    "clause_index": clause.get("clause_index", clause_index),
                    "clause_title": clause.get("clause_title", ""),
                    "original_text": clause.get("original_text", ""),
                    "risk_level": clause.get("risk_level", "unknown"),
                    "risk_score": clause.get("risk_score"),
                    "risk_reason": clause.get("risk_reason", ""),
                    "plain_english": clause.get("plain_english", ""),
                    "key_concerns": clause.get("key_concerns", []),
                    "suggested_fix": clause.get("suggested_fix", ""),
                    "analysis_status": clause.get("analysis_status", "success"),
                    "retry_count": clause.get("retry_count", 0),
                    "error_message": clause.get("error_message"),
                    "provider_used": clause.get("provider_used"),
                    "retrieved_benchmarks": clause.get("retrieved_benchmarks", []),
                    "cited_benchmark_ids": clause.get("cited_benchmark_ids", []),
                    "risk_rule_applied": clause.get("risk_rule_applied", ""),
                    "evidence_summary": clause.get("evidence_summary", ""),
                    "benchmark_alignment": clause.get("benchmark_alignment", "none"),
                }
        except Exception as e:
            logger.error(f"Failed to get clause from Supabase: {e}")
    
    raise HTTPException(status_code=404, detail="Analysis results not found")
