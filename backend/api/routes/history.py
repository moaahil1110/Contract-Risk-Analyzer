"""
History API Route
Get authenticated user's past contract analyses.
Priority 4: Fail closed in production if Supabase fails; do not silently fall back to memory.
Priority 5: Add soft delete, rerun tracking, and history filters.
"""

import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from datetime import datetime

from api.routes.upload import contract_store, _can_persist_user_to_supabase
from api.middleware.auth import require_user, DEV_MODE
from core.status import ACTIVE_JOB_STATUSES
from db.queries import (
    get_user_contracts,
    get_contract_with_clauses_for_user,
    soft_delete_contract,
    get_active_analysis_job_for_contract,
)
from db.supabase_client import is_supabase_configured
from services.job_queue import get_local_active_job

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_supabase_persistable_user(user_id: Optional[str]) -> None:
    if is_supabase_configured() and not _can_persist_user_to_supabase(user_id):
        raise HTTPException(
            status_code=401,
            detail="Please sign in before viewing contract history.",
        )


def _transform_db_contract_to_response(contract: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform a database contract record to API response format.
    """
    return {
        "id": contract.get("id"),
        "filename": contract.get("filename", "Unknown"),
        "contract_type": contract.get("contract_type", "other"),
        "selected_contract_type": contract.get("selected_contract_type") or contract.get("contract_type", "other"),
        "detected_contract_type": contract.get("detected_contract_type") or contract.get("contract_type", "other"),
        "contract_type_confidence": contract.get("contract_type_confidence", 0),
        "status": contract.get("status", "unknown"),
        "progress_percent": contract.get("progress_percent", 100 if contract.get("status") == "complete" else 0),
        "status_message": contract.get("status_message"),
        "error_message": contract.get("error_message"),
        "health_score": contract.get("health_score"),
        "health_grade": contract.get("health_grade"),
        "health_label": contract.get("health_label"),
        "total_clauses": contract.get("total_clauses", 0),
        "high_risk_count": contract.get("high_risk_count", 0),
        "medium_risk_count": contract.get("medium_risk_count", 0),
        "low_risk_count": contract.get("low_risk_count", 0),
        "unknown_risk_count": contract.get("unknown_risk_count", 0),
        "failed_clause_count": contract.get("failed_clause_count", 0),
        "scored_clause_count": contract.get("scored_clause_count", 0),
        "uploaded_at": contract.get("uploaded_at"),
        "completed_at": contract.get("completed_at"),
        "rerun_count": contract.get("rerun_count", 0),
        "last_rerun_at": contract.get("last_rerun_at"),
    }


def _get_in_memory_contracts_for_user(user_id: str) -> List[Dict[str, Any]]:
    """
    Get contracts from in-memory store for a specific user.
    Used as fallback when Supabase is not configured.
    Excludes soft-deleted contracts.
    """
    contracts = []
    for contract_id, record in contract_store.items():
        if record.get("user_id") == user_id and record.get("deleted_at") is None:
            health = record.get("health") or {}
            risk_counts = health.get("risk_counts") or {}
            contracts.append({
                "id": contract_id,
                "filename": record["filename"],
                "contract_type": record.get("contract_type", "other"),
                "selected_contract_type": record.get("selected_contract_type", record.get("contract_type", "other")),
                "detected_contract_type": record.get("detected_contract_type", record.get("contract_type", "other")),
                "contract_type_confidence": record.get("contract_type_confidence", 0),
                "status": record["status"],
                "progress_percent": record.get("progress_percent", 100 if record.get("status") == "complete" else 0),
                "status_message": record.get("status_message"),
                "error_message": record.get("error_message") or record.get("error"),
                "health_score": record.get("health_score") if record.get("health_score") is not None else health.get("score"),
                "health_grade": record.get("health_grade") if record.get("health_grade") is not None else health.get("grade"),
                "health_label": record.get("health_label") if record.get("health_label") is not None else health.get("label"),
                "total_clauses": health.get("total_clauses") or len(record.get("clauses") or record.get("analysis") or []),
                "high_risk_count": risk_counts.get("high", record.get("high_risk_count", 0)),
                "medium_risk_count": risk_counts.get("medium", record.get("medium_risk_count", 0)),
                "low_risk_count": risk_counts.get("low", record.get("low_risk_count", 0)),
                "unknown_risk_count": health.get("unknown_count", record.get("unknown_risk_count", 0)),
                "failed_clause_count": health.get("failed_clause_count", record.get("failed_clause_count", 0)),
                "scored_clause_count": health.get("scored_clause_count", record.get("scored_clause_count", 0)),
                "uploaded_at": None,
                "completed_at": None,
                "rerun_count": record.get("rerun_count", 0),
                "last_rerun_at": record.get("last_rerun_at"),
            })
    return contracts


def _apply_in_memory_filters(
    contracts: List[Dict[str, Any]],
    search: Optional[str],
    status: Optional[str],
    contract_type: Optional[str],
    grade: Optional[str],
) -> List[Dict[str, Any]]:
    filtered = contracts
    if search:
        search_lower = search.lower()
        filtered = [c for c in filtered if search_lower in c.get("filename", "").lower()]
    if status:
        filtered = [c for c in filtered if c.get("status") == status]
    if contract_type:
        filtered = [c for c in filtered if c.get("contract_type") == contract_type]
    if grade:
        filtered = [c for c in filtered if c.get("health_grade") == grade]
    return filtered


@router.get("/history")
async def get_history(
    user: Dict[str, Any] = Depends(require_user),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip for pagination"),
    search: Optional[str] = Query(None, description="Filter by filename substring"),
    status: Optional[str] = Query(None, description="Filter by contract status"),
    contract_type: Optional[str] = Query(None, description="Filter by contract type"),
    grade: Optional[str] = Query(None, description="Filter by health grade"),
):
    """
    Get authenticated user's contract analysis history.
    Returns a list of contracts sorted by upload date (most recent first).
    Requires valid authentication token.
    In production, if Supabase fails, returns a service error instead of silently falling back.
    """
    user_id = user.get("id")

    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found in token")
    _require_supabase_persistable_user(user_id)

    logger.info(f"Fetching history for user {user_id}")

    supabase_ready = is_supabase_configured()

    if not supabase_ready and not DEV_MODE:
        raise HTTPException(status_code=503, detail="Database service unavailable")

    if supabase_ready:
        try:
            contracts = await get_user_contracts(
                user_id,
                search=search,
                status=status,
                contract_type=contract_type,
                grade=grade,
            )
            logger.info(f"Found {len(contracts)} contracts in Supabase for user {user_id}")

            response_contracts = [_transform_db_contract_to_response(c) for c in contracts]
            total_count = len(response_contracts)
            paginated_contracts = response_contracts[offset:offset + limit]

            return {
                "contracts": paginated_contracts,
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total_count,
            }
        except Exception as e:
            logger.error(f"Failed to fetch contracts from Supabase: {e}")
            # In production, fail closed instead of silently falling back
            if not DEV_MODE:
                raise HTTPException(status_code=503, detail="Database service unavailable")

    # Fallback to in-memory store only when Supabase is not configured or in DEV_MODE after failure
    logger.warning("Supabase not configured or failed, falling back to in-memory store")

    in_memory_contracts = _get_in_memory_contracts_for_user(user_id)
    in_memory_contracts = _apply_in_memory_filters(
        in_memory_contracts, search, status, contract_type, grade
    )
    in_memory_contracts.sort(key=lambda x: x.get("id", ""), reverse=True)

    total_count = len(in_memory_contracts)
    paginated_contracts = in_memory_contracts[offset:offset + limit]

    return {
        "contracts": paginated_contracts,
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total_count,
        "source": "memory",
    }


@router.get("/history/stats")
async def get_history_stats(
    user: Dict[str, Any] = Depends(require_user),
):
    """
    Get statistics for the authenticated user's contract analyses.
    In production, if Supabase fails, returns a service error instead of silently falling back.
    """
    user_id = user.get("id")

    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found in token")
    _require_supabase_persistable_user(user_id)

    supabase_ready = is_supabase_configured()

    if not supabase_ready and not DEV_MODE:
        raise HTTPException(status_code=503, detail="Database service unavailable")

    if supabase_ready:
        try:
            contracts = await get_user_contracts(user_id)

            total_contracts = len(contracts)
            completed_contracts = [c for c in contracts if c.get("status") == "complete"]

            health_scores = [c.get("health_score") for c in completed_contracts if c.get("health_score") is not None]
            avg_health_score = sum(health_scores) / len(health_scores) if health_scores else None

            total_high_risk = sum(c.get("high_risk_count", 0) for c in completed_contracts)
            total_medium_risk = sum(c.get("medium_risk_count", 0) for c in completed_contracts)
            total_low_risk = sum(c.get("low_risk_count", 0) for c in completed_contracts)

            return {
                "total_contracts": total_contracts,
                "completed_analyses": len(completed_contracts),
                "pending_analyses": total_contracts - len(completed_contracts),
                "average_health_score": round(avg_health_score, 2) if avg_health_score else None,
                "total_high_risk_clauses": total_high_risk,
                "total_medium_risk_clauses": total_medium_risk,
                "total_low_risk_clauses": total_low_risk,
            }
        except Exception as e:
            logger.error(f"Failed to fetch stats from Supabase: {e}")
            if not DEV_MODE:
                raise HTTPException(status_code=503, detail="Database service unavailable")

    # Fallback to in-memory
    in_memory_contracts = _get_in_memory_contracts_for_user(user_id)
    completed = [c for c in in_memory_contracts if c.get("status") == "complete"]

    return {
        "total_contracts": len(in_memory_contracts),
        "completed_analyses": len(completed),
        "pending_analyses": len(in_memory_contracts) - len(completed),
        "average_health_score": None,
        "total_high_risk_clauses": sum(c.get("high_risk_count", 0) for c in completed),
        "total_medium_risk_clauses": sum(c.get("medium_risk_count", 0) for c in completed),
        "total_low_risk_clauses": sum(c.get("low_risk_count", 0) for c in completed),
        "source": "memory",
    }


@router.get("/history/{contract_id}")
async def get_history_detail(
    contract_id: str,
    user: Dict[str, Any] = Depends(require_user),
):
    """
    Get detailed information for a specific contract from history.
    Requires valid authentication and ownership.
    In production, if Supabase fails, returns a service error instead of silently falling back.
    """
    user_id = user.get("id")

    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found in token")
    _require_supabase_persistable_user(user_id)

    supabase_ready = is_supabase_configured()

    if not supabase_ready and not DEV_MODE:
        raise HTTPException(status_code=503, detail="Database service unavailable")

    if supabase_ready:
        try:
            contract = await get_contract_with_clauses_for_user(contract_id, user_id)

            if contract:
                return {
                    "contract": _transform_db_contract_to_response(contract),
                    "clauses": contract.get("clauses", []),
                }
        except Exception as e:
            logger.error(f"Failed to fetch contract from Supabase: {e}")
            if not DEV_MODE:
                raise HTTPException(status_code=503, detail="Database service unavailable")

    # Fallback to in-memory only when Supabase is not configured or in DEV_MODE after failure
    if contract_id in contract_store:
        record = contract_store[contract_id]
        if record.get("user_id") == user_id and record.get("deleted_at") is None:
            return {
                "contract": {
                    "id": contract_id,
                    "filename": record["filename"],
                    "contract_type": record.get("contract_type", "other"),
                    "status": record["status"],
                    "total_clauses": len(record.get("clauses") or []),
                },
                "source": "memory",
            }

    raise HTTPException(status_code=404, detail="Contract not found")


@router.delete("/history/{contract_id}", status_code=204)
async def delete_history_item(
    contract_id: str,
    user: Dict[str, Any] = Depends(require_user),
):
    """
    Soft delete a contract from history.
    Requires authentication and ownership.
    Returns 409 if the contract has an active queued/running/retrying job.
    """
    user_id = user.get("id")

    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found in token")
    _require_supabase_persistable_user(user_id)

    # Verify ownership and check active job
    if is_supabase_configured():
        try:
            contract = await get_contract_with_clauses_for_user(contract_id, user_id)
            if not contract:
                raise HTTPException(status_code=404, detail="Contract not found")

            active_job = await get_active_analysis_job_for_contract(contract_id)
            if active_job:
                raise HTTPException(
                    status_code=409,
                    detail="Cannot delete a contract with an active analysis job",
                )

            success = await soft_delete_contract(contract_id, user_id)
            if not success and not DEV_MODE:
                raise HTTPException(status_code=500, detail="Failed to delete contract")
            return
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to delete contract from Supabase: {e}")
            if not DEV_MODE:
                raise HTTPException(status_code=503, detail="Database service unavailable")

    # In-memory fallback
    record = contract_store.get(contract_id)
    if not record:
        raise HTTPException(status_code=404, detail="Contract not found")
    if DEV_MODE and record.get("user_id") is None:
        pass
    elif record.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Contract not found")

    if record.get("deleted_at"):
        raise HTTPException(status_code=404, detail="Contract not found")
    # Check active job in memory
    local_job = get_local_active_job(contract_id)
    if local_job:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete a contract with an active analysis job",
        )

    record["deleted_at"] = datetime.utcnow().isoformat()
    return
