"""
Analysis API Route (Week 2 & 3)
Full analysis pipeline with RAG, LLM, and health scoring.
Week 3: Added Supabase integration for persistence
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks

from api.routes.upload import contract_store
from pipeline.rag_engine import retrieve_benchmarks
from pipeline.llm_analyser import analyse_clause
from pipeline.scorer import calculate_health_score
from db.queries import (
    update_contract_status,
    update_contract_type_metadata,
    update_contract_results,
    save_clause_analyses_batch,
    get_contract_with_clauses,
    get_contract,
)
from db.supabase_client import is_supabase_configured

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory store for analysis results (fallback when Supabase is not configured)
analysis_results: Dict[str, Any] = {}

SUPPORTED_CONTRACT_TYPES = {"nda", "employment", "vendor", "other"}
DETECTION_CONFIDENCE_THRESHOLD = 0.55


def _extract_clause_text(clause: Any) -> str:
    if isinstance(clause, dict):
        return str(clause.get("text", "") or clause.get("original_text", "") or clause.get("content", ""))
    return str(clause)


def _normalize_contract_type(contract_type: Optional[str]) -> str:
    normalized = (contract_type or "other").lower().strip()
    return normalized if normalized in SUPPORTED_CONTRACT_TYPES else "other"


def detect_contract_type(clauses: List[Any]) -> Dict[str, Any]:
    """
    Detect contract type based on clause content.
    
    Args:
        clauses: List of clause texts
    
    Returns:
        Dict with detected_contract_type, contract_type_confidence, and scores
    """
    combined_text = " ".join(_extract_clause_text(clause) for clause in clauses).lower()
    
    # Scoring based on keyword presence
    scores = {
        "nda": 0,
        "employment": 0,
        "vendor": 0,
    }
    
    # NDA keywords
    nda_keywords = [
        "confidential", "non-disclosure", "disclosing party", "receiving party",
        "trade secret", "proprietary information"
    ]
    for kw in nda_keywords:
        scores["nda"] += combined_text.count(kw)
    
    # Employment keywords
    employment_keywords = [
        "employment", "employee", "employer", "salary", "at-will",
        "termination", "severance", "benefits", "non-compete", "non-solicit"
    ]
    for kw in employment_keywords:
        scores["employment"] += combined_text.count(kw)
    
    # Vendor keywords
    vendor_keywords = [
        "vendor", "payment", "invoice", "liability", "indemnification",
        "warranty", "deliverables", "services", "customer"
    ]
    for kw in vendor_keywords:
        scores["vendor"] += combined_text.count(kw)
    
    # Get highest score
    max_score = max(scores.values())
    if max_score == 0:
        return {
            "detected_contract_type": "other",
            "contract_type_confidence": 0.0,
            "scores": scores,
        }
    
    detected_type = max(scores, key=scores.get)
    total_score = sum(scores.values())
    confidence = round(max_score / total_score, 4) if total_score else 0.0
    return {
        "detected_contract_type": detected_type,
        "contract_type_confidence": confidence,
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

    conflict = (
        selected != "other"
        and detected != "other"
        and selected != detected
        and confidence > 0
    )

    return {
        "selected_contract_type": selected,
        "detected_contract_type": detected,
        "contract_type_confidence": confidence,
        "contract_type": effective,
        "contract_type_conflict": conflict,
    }


async def process_contract_analysis(contract_id: str, clauses: List[Any], contract_type_metadata: Dict[str, Any]):
    """
    Background task to analyze all clauses and calculate health score.
    Saves results to Supabase if configured.
    
    Args:
        contract_id: The contract ID
        clauses: List of clause texts
        contract_type_metadata: Selected, detected, and effective contract type data
    """
    contract_type = contract_type_metadata["contract_type"]
    logger.info(f"Starting analysis for contract {contract_id} ({len(clauses)} clauses)")

    # Update status to processing in database
    await update_contract_status(contract_id, "processing")

    analyzed_clauses = []

    # DEBUG: Log first clause to inspect its structure
    if clauses:
        logger.info(f"First clause object: {clauses[0]}")

    for idx, clause in enumerate(clauses):
        logger.info(f"Analyzing clause {idx + 1}/{len(clauses)}")

        try:
            clause_text = _extract_clause_text(clause)
            logger.info(f"clause keys: {list(clause.keys()) if isinstance(clause, dict) else f'type={type(clause).__name__}'}")
            logger.info(f"clause_text preview: {clause_text[:100]}")

            # Step 1: Retrieve similar benchmarks from RAG
            benchmarks = retrieve_benchmarks(clause_text, k=3, contract_type=contract_type)
            logger.debug(f"Retrieved {len(benchmarks)} benchmarks for clause {idx}")

            # Step 2: Analyze clause with LLM
            result = await analyse_clause(
                clause_text=clause_text,
                benchmarks=benchmarks,
                contract_type=contract_type,
            )

            # Step 3: Build clause result
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
            }

            analyzed_clauses.append(clause_result)

        except Exception as e:
            import traceback
            logger.error(f"FULL TRACEBACK: {traceback.format_exc()}")
            analyzed_clauses.append({
                "id": f"{contract_id}_clause_{idx}",
                "clause_index": idx,
                "clause_title": f"Clause {idx + 1}",
                "original_text": _extract_clause_text(clause),
                "risk_level": "unknown",
                "risk_score": None,
                "risk_reason": f"Analysis failed: {str(e)}",
                "plain_english": "This clause could not be analyzed.",
                "key_concerns": ["Analysis error occurred"],
                "suggested_fix": "Please retry the analysis.",
                "analysis_status": "failed",
                "retry_count": 0,
                "error_message": str(e),
                "provider_used": "error",
                "retrieved_benchmarks": [],
            })

        await asyncio.sleep(1)
    
    # Step 4: Calculate health score
    health = calculate_health_score(analyzed_clauses)
    
    # Step 5: Save clause analyses to Supabase (batch insert)
    db_saved = await save_clause_analyses_batch(contract_id, analyzed_clauses)
    if db_saved:
        logger.info(f"Saved {len(analyzed_clauses)} clause analyses to Supabase")
    else:
        logger.warning("Failed to save clause analyses to Supabase (may not be configured)")
    
    # Step 6: Update contract with results
    db_updated = await update_contract_results(
        contract_id=contract_id,
        health_data=health,
        risk_counts=health.get("risk_counts", {"high": 0, "medium": 0, "low": 0}),
        total_clauses=len(analyzed_clauses)
    )
    if db_updated:
        logger.info(f"Updated contract {contract_id} results in Supabase")
    else:
        logger.warning("Failed to update contract results in Supabase (may not be configured)")
    
    # Step 7: Store results in memory (for fallback and caching)
    analysis_results[contract_id] = {
        "contract_id": contract_id,
        "status": "complete",
        "clauses": analyzed_clauses,
        "health": health,
        **contract_type_metadata,
    }
    
    # Update contract store status
    if contract_id in contract_store:
        contract_store[contract_id]["status"] = "complete"
        contract_store[contract_id].update(contract_type_metadata)
    
    logger.info(f"Analysis complete for contract {contract_id}. Health score: {health['score']}")


@router.post("/analyse/{contract_id}")
async def start_analysis(contract_id: str, background_tasks: BackgroundTasks):
    """
    Start analysis for a contract.
    Returns immediately, analysis runs in background.
    """
    if contract_id not in contract_store:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    record = contract_store[contract_id]
    
    if record["status"] == "failed":
        raise HTTPException(status_code=400, detail=f"Upload failed: {record.get('error')}")
    
    if not record["clauses"]:
        raise HTTPException(status_code=400, detail="No clauses found in contract")
    
    # Check if already analyzed
    if contract_id in analysis_results:
        return {
            "contract_id": contract_id,
            "status": "already_analyzed",
            "message": "Contract has already been analyzed",
        }
    
    # Mark as processing
    contract_store[contract_id]["status"] = "processing"
    
    # Detect contract type without overwriting the user's selected type.
    selected_contract_type = record.get("selected_contract_type") or record.get("contract_type")
    detection = detect_contract_type(record["clauses"])
    contract_type_metadata = resolve_contract_type(selected_contract_type, detection)
    contract_store[contract_id].update(contract_type_metadata)
    await update_contract_type_metadata(contract_id, contract_type_metadata)
    logger.info(
        "Contract type selected=%s detected=%s confidence=%s effective=%s",
        contract_type_metadata["selected_contract_type"],
        contract_type_metadata["detected_contract_type"],
        contract_type_metadata["contract_type_confidence"],
        contract_type_metadata["contract_type"],
    )
    
    # Start background analysis
    background_tasks.add_task(
        process_contract_analysis,
        contract_id=contract_id,
        clauses=record["clauses"],
        contract_type_metadata=contract_type_metadata,
    )
    
    return {
        "contract_id": contract_id,
        "status": "analysis_started",
        "message": f"Analyzing {len(record['clauses'])} clauses in background",
        "total_clauses": len(record["clauses"]),
        **contract_type_metadata,
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
            if db_contract and db_contract.get("status") == "complete":
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
                    })
                
                return {
                    "contract_id": contract_id,
                    "filename": db_contract.get("filename", ""),
                    "status": "complete",
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
        except Exception as e:
            logger.warning(f"Failed to get results from Supabase: {e}")
    
    # Fallback to in-memory store
    if contract_id not in contract_store:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    record = contract_store[contract_id]
    
    # Check if analysis is complete
    if contract_id in analysis_results:
        result = analysis_results[contract_id]
        return {
            "contract_id": contract_id,
            "filename": record["filename"],
            "status": "complete",
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
    return {
        "contract_id": contract_id,
        "filename": record["filename"],
        "status": record["status"],
        "message": "Analysis in progress. Check back shortly.",
        "total_clauses": len(record.get("clauses", [])),
        "contract_type": record.get("contract_type", "unknown"),
        "selected_contract_type": record.get("selected_contract_type", record.get("contract_type", "unknown")),
        "detected_contract_type": record.get("detected_contract_type", "unknown"),
        "contract_type_confidence": record.get("contract_type_confidence", 0),
        "contract_type_conflict": record.get("contract_type_conflict", False),
    }


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
                is_complete = db_contract.get("status") == "complete"
                return {
                    "contract_id": contract_id,
                    "status": db_contract.get("status", "unknown"),
                    "has_results": is_complete,
                }
        except Exception as e:
            logger.debug(f"Failed to get status from Supabase: {e}")
    
    # Fallback to in-memory
    if contract_id not in contract_store:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    is_complete = contract_id in analysis_results
    
    return {
        "contract_id": contract_id,
        "status": "complete" if is_complete else contract_store[contract_id].get("status", "unknown"),
        "has_results": is_complete,
    }


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
                }
        except Exception as e:
            logger.error(f"Failed to get clause from Supabase: {e}")
    
    raise HTTPException(status_code=404, detail="Analysis results not found")
