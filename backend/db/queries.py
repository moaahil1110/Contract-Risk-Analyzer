"""
Database Queries Module
Week 3: Supabase database operations for contracts and clause analyses
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID

from db.supabase_client import get_supabase_client, is_supabase_configured

logger = logging.getLogger(__name__)


# =============================================================================
# Contract Operations
# =============================================================================

async def create_contract(user_id: Optional[str], filename: str, contract_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
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
            "user_id": user_id,
            "filename": filename,
            "contract_type": contract_type or "other",
            "status": "processing",
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
            "health_score": health_data.get("score"),
            "health_grade": health_data.get("grade"),
            "health_label": health_data.get("label"),
            "total_clauses": total_clauses,
            "high_risk_count": risk_counts.get("high", 0),
            "medium_risk_count": risk_counts.get("medium", 0),
            "low_risk_count": risk_counts.get("low", 0),
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
            "risk_level": clause_data.get("risk_level", "medium"),
            "risk_score": clause_data.get("risk_score", 50),
            "risk_reason": clause_data.get("risk_reason", ""),
            "plain_english": clause_data.get("plain_english", ""),
            "key_concerns": key_concerns,
            "suggested_fix": clause_data.get("suggested_fix", ""),
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
                "risk_level": clause.get("risk_level", "medium"),
                "risk_score": clause.get("risk_score", 50),
                "risk_reason": clause.get("risk_reason", ""),
                "plain_english": clause.get("plain_english", ""),
                "key_concerns": key_concerns,
                "suggested_fix": clause.get("suggested_fix", ""),
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
