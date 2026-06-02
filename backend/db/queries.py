"""
Database Queries Module
Week 3: Supabase database operations for contracts and clause analyses
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID, uuid4

from db.supabase_client import get_supabase_client, is_supabase_configured
from core.status import ACTIVE_JOB_STATUSES

logger = logging.getLogger(__name__)


# =============================================================================
# Contract Operations
# =============================================================================

async def create_contract(
    user_id: Optional[str],
    filename: str,
    contract_type: Optional[str] = None,
    contract_id: Optional[str] = None,
    storage_path: Optional[str] = None,
    file_size_bytes: Optional[int] = None,
    mime_type: Optional[str] = None,
    status: str = "uploaded",
) -> Optional[Dict[str, Any]]:
    """
    Create a new contract record in the database.
    
    Args:
        user_id: The user's UUID (None for anonymous uploads in dev mode)
        filename: The original filename of the uploaded contract
        contract_type: Type of contract (nda, employment, vendor, other)
    
    Returns:
        The created contract record including the generated ID, or None if Supabase is not configured
    """
    if not is_supabase_configured():
        logger.debug("Supabase not configured, skipping create_contract")
        return None
    
    client = get_supabase_client()
    if not client:
        return None
    
    try:
        contract_data = {
            "id": contract_id or str(uuid4()),
            "user_id": user_id,
            "filename": filename,
            "contract_type": contract_type or "other",
            "selected_contract_type": contract_type or "other",
            "detected_contract_type": contract_type or "other",
            "contract_type_confidence": 1.0 if contract_type else 0.0,
            "status": status,
            "storage_path": storage_path,
            "file_size_bytes": file_size_bytes,
            "mime_type": mime_type,
            "progress_percent": 0,
            "status_message": "Uploaded and ready for analysis",
            "uploaded_at": datetime.utcnow().isoformat(),
        }
        
        result = client.table("contracts").insert(contract_data).execute()
        
        if result.data and len(result.data) > 0:
            logger.info(f"Created contract record: {result.data[0]['id']}")
            return result.data[0]
        else:
            logger.error("Failed to create contract: no data returned")
            return None
            
    except Exception as e:
        logger.error(f"Error creating contract: {e}")
        return None


async def update_contract_type_metadata(contract_id: str, type_metadata: Dict[str, Any]) -> bool:
    """
    Persist selected, detected, and effective contract type metadata.
    """
    if not is_supabase_configured():
        logger.debug("Supabase not configured, skipping update_contract_type_metadata")
        return False

    client = get_supabase_client()
    if not client:
        return False

    try:
        update_data = {
            "contract_type": type_metadata.get("contract_type", "other"),
            "selected_contract_type": type_metadata.get("selected_contract_type", "other"),
            "detected_contract_type": type_metadata.get("detected_contract_type", "other"),
            "contract_type_confidence": type_metadata.get("contract_type_confidence", 0),
        }

        result = client.table("contracts").update(update_data).eq("id", contract_id).execute()

        if result.data:
            logger.info(f"Updated contract {contract_id} type metadata")
            return True

        logger.error(f"Failed to update contract {contract_id} type metadata")
        return False

    except Exception as e:
        logger.error(f"Error updating contract type metadata: {e}")
        return False


async def update_contract_storage_metadata(
    contract_id: str,
    storage_path: str,
    file_size_bytes: int,
    mime_type: Optional[str],
) -> bool:
    if not is_supabase_configured():
        logger.debug("Supabase not configured, skipping update_contract_storage_metadata")
        return False

    client = get_supabase_client()
    if not client:
        return False

    try:
        result = client.table("contracts").update({
            "storage_path": storage_path,
            "file_size_bytes": file_size_bytes,
            "mime_type": mime_type or "application/pdf",
        }).eq("id", contract_id).execute()
        return bool(result.data)
    except Exception as e:
        logger.error(f"Error updating contract storage metadata: {e}")
        return False


async def update_contract_status(contract_id: str, status: str) -> bool:
    """
    Update the status of a contract.
    
    Args:
        contract_id: The contract UUID
        status: New status (processing, complete, failed)
    
    Returns:
        True if successful, False otherwise
    """
    if not is_supabase_configured():
        logger.debug("Supabase not configured, skipping update_contract_status")
        return False
    
    client = get_supabase_client()
    if not client:
        return False
    
    try:
        update_data = {"status": status}
        
        if status == "complete":
            update_data["completed_at"] = datetime.utcnow().isoformat()
        
        result = client.table("contracts").update(update_data).eq("id", contract_id).execute()
        
        if result.data:
            logger.info(f"Updated contract {contract_id} status to: {status}")
            return True
        else:
            logger.error(f"Failed to update contract {contract_id} status")
            return False
            
    except Exception as e:
        logger.error(f"Error updating contract status: {e}")
        return False


async def update_contract_progress(
    contract_id: str,
    status: str,
    progress_percent: int,
    message: str,
    error: Optional[str] = None,
) -> bool:
    if not is_supabase_configured():
        logger.debug("Supabase not configured, skipping update_contract_progress")
        return False

    client = get_supabase_client()
    if not client:
        return False

    try:
        now = datetime.utcnow().isoformat()
        update_data = {
            "status": status,
            "progress_percent": max(0, min(100, int(progress_percent))),
            "status_message": message,
            "error_message": error,
        }
        if status == "queued":
            update_data["queued_at"] = now
        if status in {"extracting", "retrieving_benchmarks", "analysing"}:
            update_data["started_at"] = now
        if status in {"complete", "failed"}:
            update_data["completed_at"] = now

        result = client.table("contracts").update(update_data).eq("id", contract_id).execute()
        return bool(result.data)
    except Exception as e:
        logger.error(f"Error updating contract progress: {e}")
        return False


async def update_contract_results(
    contract_id: str,
    health_data: Dict[str, Any],
    risk_counts: Dict[str, int],
    total_clauses: int
) -> bool:
    """
    Update contract with analysis results and health score.
    
    Args:
        contract_id: The contract UUID
        health_data: Health score data containing score, grade, label
        risk_counts: Dictionary with high, medium, low counts
        total_clauses: Total number of clauses analyzed
    
    Returns:
        True if successful, False otherwise
    """
    if not is_supabase_configured():
        logger.debug("Supabase not configured, skipping update_contract_results")
        return False
    
    client = get_supabase_client()
    if not client:
        return False
    
    try:
        update_data = {
            "status": "complete",
            "progress_percent": 100,
            "status_message": "Analysis complete",
            "error_message": None,
            "health_score": health_data.get("score"),
            "health_grade": health_data.get("grade"),
            "health_label": health_data.get("label"),
            "total_clauses": total_clauses,
            "high_risk_count": risk_counts.get("high", 0),
            "medium_risk_count": risk_counts.get("medium", 0),
            "low_risk_count": risk_counts.get("low", 0),
            "unknown_risk_count": health_data.get("unknown_count", 0),
            "failed_clause_count": health_data.get("failed_clause_count", 0),
            "scored_clause_count": health_data.get("scored_clause_count", 0),
            "completed_at": datetime.utcnow().isoformat(),
        }
        
        result = client.table("contracts").update(update_data).eq("id", contract_id).execute()
        
        if result.data:
            logger.info(f"Updated contract {contract_id} with analysis results")
            return True
        else:
            logger.error(f"Failed to update contract {contract_id} results")
            return False
            
    except Exception as e:
        logger.error(f"Error updating contract results: {e}")
        return False


async def create_analysis_job(
    contract_id: str,
    celery_task_id: Optional[str] = None,
    max_retries: int = 3,
) -> Optional[Dict[str, Any]]:
    if not is_supabase_configured():
        logger.debug("Supabase not configured, skipping create_analysis_job")
        return None

    client = get_supabase_client()
    if not client:
        return None

    try:
        job_data = {
            "contract_id": contract_id,
            "celery_task_id": celery_task_id,
            "status": "queued",
            "current_stage": "queued",
            "progress_percent": 0,
            "attempts": 0,
            "max_retries": max_retries,
            "timings": {},
            "metadata": {},
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        result = client.table("analysis_jobs").insert(job_data).execute()
        if result.data:
            return result.data[0]
        return None
    except Exception as e:
        logger.error(f"Error creating analysis job: {e}")
        return None


async def update_analysis_job(
    job_id: str,
    status: str,
    stage: Optional[str] = None,
    attempts: Optional[int] = None,
    timings: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    celery_task_id: Optional[str] = None,
) -> bool:
    if not is_supabase_configured():
        logger.debug("Supabase not configured, skipping update_analysis_job")
        return False

    client = get_supabase_client()
    if not client:
        return False

    try:
        now = datetime.utcnow().isoformat()
        update_data: Dict[str, Any] = {
            "status": status,
            "updated_at": now,
        }
        if stage is not None:
            update_data["current_stage"] = stage
        if attempts is not None:
            update_data["attempts"] = attempts
        if timings is not None:
            update_data["timings"] = timings
        if metadata is not None:
            update_data["metadata"] = metadata
        if error is not None:
            update_data["last_error"] = error
        if celery_task_id is not None:
            update_data["celery_task_id"] = celery_task_id
        if status == "running":
            update_data["started_at"] = now
        if status in {"succeeded", "failed"}:
            update_data["finished_at"] = now

        result = client.table("analysis_jobs").update(update_data).eq("id", job_id).execute()
        return bool(result.data)
    except Exception as e:
        logger.error(f"Error updating analysis job: {e}")
        return False


async def get_active_analysis_job(contract_id: str) -> Optional[Dict[str, Any]]:
    if not is_supabase_configured():
        logger.debug("Supabase not configured, skipping get_active_analysis_job")
        return None

    client = get_supabase_client()
    if not client:
        return None

    try:
        result = (
            client.table("analysis_jobs")
            .select("*")
            .eq("contract_id", contract_id)
            .in_("status", list(ACTIVE_JOB_STATUSES))
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]
        return None
    except Exception as e:
        logger.error(f"Error getting active analysis job: {e}")
        return None


async def get_analysis_job_by_task_id(celery_task_id: str) -> Optional[Dict[str, Any]]:
    if not is_supabase_configured():
        logger.debug("Supabase not configured, skipping get_analysis_job_by_task_id")
        return None

    client = get_supabase_client()
    if not client:
        return None

    try:
        result = (
            client.table("analysis_jobs")
            .select("*")
            .eq("celery_task_id", celery_task_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]
        return None
    except Exception as e:
        logger.error(f"Error getting analysis job by task id: {e}")
        return None


async def get_contract(contract_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a contract by ID.
    
    Args:
        contract_id: The contract UUID
    
    Returns:
        The contract record, or None if not found
    """
    if not is_supabase_configured():
        logger.debug("Supabase not configured, skipping get_contract")
        return None
    
    client = get_supabase_client()
    if not client:
        return None
    
    try:
        result = client.table("contracts").select("*").eq("id", contract_id).single().execute()
        
        if result.data:
            return result.data
        else:
            logger.warning(f"Contract {contract_id} not found")
            return None
            
    except Exception as e:
        logger.error(f"Error getting contract: {e}")
        return None


async def get_contract_with_clauses(contract_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a contract with all its clause analyses.
    
    Args:
        contract_id: The contract UUID
    
    Returns:
        Dictionary with contract data and clauses list, or None if not found
    """
    if not is_supabase_configured():
        logger.debug("Supabase not configured, skipping get_contract_with_clauses")
        return None
    
    client = get_supabase_client()
    if not client:
        return None
    
    try:
        # Get contract
        contract_result = client.table("contracts").select("*").eq("id", contract_id).single().execute()
        
        if not contract_result.data:
            logger.warning(f"Contract {contract_id} not found")
            return None
        
        contract = contract_result.data
        
        # Get clauses
        clauses_result = client.table("clause_analyses").select("*").eq("contract_id", contract_id).order("clause_index").execute()
        
        contract["clauses"] = clauses_result.data if clauses_result.data else []
        
        return contract
        
    except Exception as e:
        logger.error(f"Error getting contract with clauses: {e}")
        return None


async def get_user_contracts(user_id: str) -> List[Dict[str, Any]]:
    """
    Get all contracts for a user.
    
    Args:
        user_id: The user's UUID
    
    Returns:
        List of contract records
    """
    if not is_supabase_configured():
        logger.debug("Supabase not configured, skipping get_user_contracts")
        return []
    
    client = get_supabase_client()
    if not client:
        return []
    
    try:
        result = client.table("contracts").select("*").eq("user_id", user_id).order("uploaded_at", desc=True).execute()
        
        return result.data if result.data else []
        
    except Exception as e:
        logger.error(f"Error getting user contracts: {e}")
        return []


# =============================================================================
# Clause Analysis Operations
# =============================================================================

async def save_clause_analysis(
    contract_id: str,
    clause_index: int,
    clause_data: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Save a single clause analysis to the database.
    
    Args:
        contract_id: The contract UUID
        clause_index: The index of the clause in the document
        clause_data: Dictionary containing clause analysis results
    
    Returns:
        The created clause analysis record, or None if failed
    """
    if not is_supabase_configured():
        logger.debug("Supabase not configured, skipping save_clause_analysis")
        return None
    
    client = get_supabase_client()
    if not client:
        return None
    
    try:
        # Convert key_concerns list to JSON if needed
        key_concerns = clause_data.get("key_concerns", [])
        if isinstance(key_concerns, str):
            import json
            try:
                key_concerns = json.loads(key_concerns)
            except:
                key_concerns = [key_concerns] if key_concerns else []
        
        analysis_data = {
            "contract_id": contract_id,
            "clause_index": clause_index,
            "clause_title": clause_data.get("clause_title", f"Clause {clause_index + 1}"),
            "original_text": clause_data.get("original_text", ""),
            "risk_level": clause_data.get("risk_level", "unknown"),
            "risk_score": clause_data.get("risk_score"),
            "risk_reason": clause_data.get("risk_reason", ""),
            "plain_english": clause_data.get("plain_english", ""),
            "key_concerns": key_concerns,
            "suggested_fix": clause_data.get("suggested_fix", ""),
            "analysis_status": clause_data.get("analysis_status", "success"),
            "retry_count": clause_data.get("retry_count", 0),
            "error_message": clause_data.get("error_message"),
            "provider_used": clause_data.get("provider_used"),
            "retrieved_benchmarks": clause_data.get("retrieved_benchmarks", []),
            "cited_benchmark_ids": clause_data.get("cited_benchmark_ids", []),
            "risk_rule_applied": clause_data.get("risk_rule_applied", ""),
            "evidence_summary": clause_data.get("evidence_summary", ""),
            "benchmark_alignment": clause_data.get("benchmark_alignment", "none"),
            "created_at": datetime.utcnow().isoformat(),
        }
        
        result = client.table("clause_analyses").insert(analysis_data).execute()
        
        if result.data and len(result.data) > 0:
            return result.data[0]
        else:
            logger.error("Failed to save clause analysis: no data returned")
            return None
            
    except Exception as e:
        logger.error(f"Error saving clause analysis: {e}")
        return None


async def save_clause_analyses_batch(
    contract_id: str,
    clauses: List[Dict[str, Any]]
) -> bool:
    """
    Save multiple clause analyses in batch.
    
    Args:
        contract_id: The contract UUID
        clauses: List of clause analysis data dictionaries
    
    Returns:
        True if all saved successfully, False otherwise
    """
    if not is_supabase_configured():
        logger.debug("Supabase not configured, skipping save_clause_analyses_batch")
        return False
    
    client = get_supabase_client()
    if not client:
        return False
    
    try:
        analyses_data = []
        for idx, clause in enumerate(clauses):
            # Convert key_concerns list to JSON if needed
            key_concerns = clause.get("key_concerns", [])
            if isinstance(key_concerns, str):
                import json
                try:
                    key_concerns = json.loads(key_concerns)
                except:
                    key_concerns = [key_concerns] if key_concerns else []
            
            analyses_data.append({
                "contract_id": contract_id,
                "clause_index": idx,
                "clause_title": clause.get("clause_title", f"Clause {idx + 1}"),
                "original_text": clause.get("original_text", ""),
                "risk_level": clause.get("risk_level", "unknown"),
                "risk_score": clause.get("risk_score"),
                "risk_reason": clause.get("risk_reason", ""),
                "plain_english": clause.get("plain_english", ""),
                "key_concerns": key_concerns,
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
                "created_at": datetime.utcnow().isoformat(),
            })
        
        result = client.table("clause_analyses").insert(analyses_data).execute()
        
        if result.data:
            logger.info(f"Saved {len(result.data)} clause analyses for contract {contract_id}")
            return True
        else:
            logger.error("Failed to save clause analyses batch: no data returned")
            return False
            
    except Exception as e:
        logger.error(f"Error saving clause analyses batch: {e}")
        return False


async def get_clauses_for_contract(contract_id: str) -> List[Dict[str, Any]]:
    """
    Get all clause analyses for a contract.
    
    Args:
        contract_id: The contract UUID
    
    Returns:
        List of clause analysis records
    """
    if not is_supabase_configured():
        logger.debug("Supabase not configured, skipping get_clauses_for_contract")
        return []
    
    client = get_supabase_client()
    if not client:
        return []
    
    try:
        result = client.table("clause_analyses").select("*").eq("contract_id", contract_id).order("clause_index").execute()
        
        return result.data if result.data else []
        
    except Exception as e:
        logger.error(f"Error getting clauses for contract: {e}")
        return []


# =============================================================================
# User Profile Operations
# =============================================================================

async def ensure_user_profile(user_id: str, email: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Ensure a user profile exists for a Supabase Auth user.
    
    Args:
        user_id: The user's UUID from auth.users
        email: The user's email address
    
    Returns:
        The existing or created user profile record, or None if failed
    """
    if not is_supabase_configured():
        logger.debug("Supabase not configured, skipping ensure_user_profile")
        return None
    
    client = get_supabase_client()
    if not client:
        return None
    
    safe_email = email or "unknown@example.com"
    
    try:
        existing = client.table("user_profiles").select("*").eq("id", user_id).limit(1).execute()
        
        if existing.data:
            profile = existing.data[0]
            if safe_email and profile.get("email") != safe_email:
                update_result = client.table("user_profiles").update({
                    "email": safe_email
                }).eq("id", user_id).execute()
                if update_result.data:
                    return update_result.data[0]
            return profile
        
        profile_data = {
            "id": user_id,
            "email": safe_email,
            "analyses_used": 0,
            "plan": "free",
            "created_at": datetime.utcnow().isoformat(),
        }
        
        result = client.table("user_profiles").insert(profile_data).execute()
        
        if result.data and len(result.data) > 0:
            logger.info(f"Ensured user profile: {user_id}")
            return result.data[0]
        
        logger.error("Failed to ensure user profile: no data returned")
        return None
        
    except Exception as e:
        logger.error(f"Error ensuring user profile: {e}")
        return None


async def create_user_profile(user_id: str, email: str) -> Optional[Dict[str, Any]]:
    """
    Create a user profile when a new user signs up.
    
    Args:
        user_id: The user's UUID from auth.users
        email: The user's email address
    
    Returns:
        The created user profile record, or None if failed
    """
    if not is_supabase_configured():
        logger.debug("Supabase not configured, skipping create_user_profile")
        return None
    
    client = get_supabase_client()
    if not client:
        return None
    
    try:
        profile_data = {
            "id": user_id,
            "email": email,
            "analyses_used": 0,
            "plan": "free",
            "created_at": datetime.utcnow().isoformat(),
        }
        
        result = client.table("user_profiles").insert(profile_data).execute()
        
        if result.data and len(result.data) > 0:
            logger.info(f"Created user profile: {user_id}")
            return result.data[0]
        else:
            logger.error("Failed to create user profile: no data returned")
            return None
            
    except Exception as e:
        logger.error(f"Error creating user profile: {e}")
        return None


async def increment_analyses_used(user_id: str) -> bool:
    """
    Increment the analyses_used counter for a user.
    
    Args:
        user_id: The user's UUID
    
    Returns:
        True if successful, False otherwise
    """
    if not is_supabase_configured():
        logger.debug("Supabase not configured, skipping increment_analyses_used")
        return False
    
    client = get_supabase_client()
    if not client:
        return False
    
    try:
        # Get current count
        result = client.table("user_profiles").select("analyses_used").eq("id", user_id).single().execute()
        
        if not result.data:
            logger.warning(f"User profile {user_id} not found")
            return False
        
        current_count = result.data.get("analyses_used", 0)
        
        # Update with incremented count
        update_result = client.table("user_profiles").update({
            "analyses_used": current_count + 1
        }).eq("id", user_id).execute()
        
        if update_result.data:
            logger.info(f"Incremented analyses used for user {user_id}: {current_count + 1}")
            return True
        else:
            logger.error(f"Failed to increment analyses used for user {user_id}")
            return False
            
    except Exception as e:
        logger.error(f"Error incrementing analyses used: {e}")
        return False
