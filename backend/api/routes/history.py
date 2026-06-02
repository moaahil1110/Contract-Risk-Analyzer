"""
History API Route
Get authenticated user's past contract analyses.
Week 3: Implemented with Supabase integration and auth middleware
"""

import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from datetime import datetime

from api.routes.upload import contract_store
from db.queries import get_user_contracts
from db.supabase_client import is_supabase_configured
from api.middleware.auth import require_user, get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter()


def _transform_db_contract_to_response(contract: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform a database contract record to API response format.
    
    Args:
        contract: Raw database contract record
    
    Returns:
        Formatted contract dict for API response
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
    }


def _get_in_memory_contracts_for_user(user_id: str) -> List[Dict[str, Any]]:
    """
    Get contracts from in-memory store for a specific user.
    Used as fallback when Supabase is not configured.
    
    Args:
        user_id: The user's ID
    
    Returns:
        List of contract dicts
    """
    contracts = []
    for contract_id, record in contract_store.items():
        if record.get("user_id") == user_id:
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
                "health_score": None,  # Would need analysis_results for this
                "health_grade": None,
                "health_label": None,
                "total_clauses": len(record.get("clauses", [])),
                "high_risk_count": 0,
                "medium_risk_count": 0,
                "low_risk_count": 0,
                "unknown_risk_count": 0,
                "failed_clause_count": 0,
                "scored_clause_count": 0,
                "uploaded_at": None,
                "completed_at": None,
            })
    return contracts


@router.get("/history")
async def get_history(
    user: Dict[str, Any] = Depends(require_user),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip for pagination"),
):
    """
    Get authenticated user's contract analysis history.
    
    Returns a list of contracts sorted by upload date (most recent first).
    Requires valid authentication token.
    
    Args:
        limit: Maximum number of results to return (default: 50, max: 100)
        offset: Number of results to skip for pagination (default: 0)
    
    Returns:
        List of contracts with summary information
    """
    user_id = user.get("id")
    
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found in token")
    
    logger.info(f"Fetching history for user {user_id}")
    
    # Try to get from Supabase first
    if is_supabase_configured():
        try:
            contracts = await get_user_contracts(user_id)
            
            if contracts:
                logger.info(f"Found {len(contracts)} contracts in Supabase for user {user_id}")
                
                # Transform to response format
                response_contracts = [_transform_db_contract_to_response(c) for c in contracts]
                
                # Apply pagination manually (Supabase Python client doesn't support offset/limit in query)
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
    
    # Fallback to in-memory store
    logger.warning("Supabase not configured or failed, falling back to in-memory store")
    
    in_memory_contracts = _get_in_memory_contracts_for_user(user_id)
    
    # Sort by uploaded_at (descending) - in-memory doesn't have real timestamps
    in_memory_contracts.sort(key=lambda x: x.get("id", ""), reverse=True)
    
    total_count = len(in_memory_contracts)
    paginated_contracts = in_memory_contracts[offset:offset + limit]
    
    return {
        "contracts": paginated_contracts,
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total_count,
        "source": "memory",  # Indicates this is from in-memory store
    }


@router.get("/history/{contract_id}")
async def get_history_detail(
    contract_id: str,
    user: Dict[str, Any] = Depends(require_user),
):
    """
    Get detailed information for a specific contract from history.
    
    Args:
        contract_id: The contract UUID
    
    Returns:
        Detailed contract information
    """
    user_id = user.get("id")
    
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found in token")
    
    # Check if contract exists in Supabase
    if is_supabase_configured():
        try:
            from db.queries import get_contract_with_clauses
            contract = await get_contract_with_clauses(contract_id)
            
            if contract and contract.get("user_id") == user_id:
                return {
                    "contract": _transform_db_contract_to_response(contract),
                    "clauses": contract.get("clauses", []),
                }
        except Exception as e:
            logger.error(f"Failed to fetch contract from Supabase: {e}")
    
    # Fallback to in-memory
    if contract_id in contract_store:
        record = contract_store[contract_id]
        if record.get("user_id") == user_id:
            return {
                "contract": {
                    "id": contract_id,
                    "filename": record["filename"],
                    "contract_type": record.get("contract_type", "other"),
                    "status": record["status"],
                    "total_clauses": len(record.get("clauses", [])),
                },
                "source": "memory",
            }
    
    raise HTTPException(status_code=404, detail="Contract not found")


@router.get("/history/stats")
async def get_history_stats(
    user: Dict[str, Any] = Depends(require_user),
):
    """
    Get statistics for the authenticated user's contract analyses.
    
    Returns:
        Summary statistics including total analyses, average health score, etc.
    """
    user_id = user.get("id")
    
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found in token")
    
    # Try Supabase first
    if is_supabase_configured():
        try:
            contracts = await get_user_contracts(user_id)
            
            total_contracts = len(contracts)
            completed_contracts = [c for c in contracts if c.get("status") == "complete"]
            
            # Calculate average health score
            health_scores = [c.get("health_score") for c in completed_contracts if c.get("health_score") is not None]
            avg_health_score = sum(health_scores) / len(health_scores) if health_scores else None
            
            # Count by risk level
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
