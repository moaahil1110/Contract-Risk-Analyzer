"""
Analysis API Route (Week 2 & 3)
Full analysis pipeline with RAG, LLM, and health scoring.
Week 3: Added Supabase integration for persistence
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, Request

from api.routes.upload import contract_store
from models.contract import AnalysisResponse, HealthScore, Clause
from pipeline.rag_engine import retrieve_benchmarks
from pipeline.llm_analyser import analyse_clause
from pipeline.scorer import calculate_health_score
from db.queries import (
    update_contract_status,
    update_contract_results,
    save_clause_analyses_batch,
    get_contract_with_clauses,
    get_contract,
)
from db.supabase_client import is_supabase_configured
from api.middleware.auth import optional_user

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory store for analysis results (fallback when Supabase is not configured)
analysis_results: Dict[str, Any] = {}


def detect_contract_type(clauses: List[str]) -> str:
    """
    Detect contract type based on clause content.
    
    Args:
        clauses: List of clause texts
    
    Returns:
        Detected contract type (nda, employment, vendor, other)
    """
    combined_text = " ".join(clauses).lower()
    
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
        if kw in combined_text:
            scores["nda"] += 1
    
    # Employment keywords
    employment_keywords = [
        "employment", "employee", "employer", "salary", "at-will",
        "termination", "severance", "benefits", "non-compete", "non-solicit"
    ]
    for kw in employment_keywords:
        if kw in combined_text:
            scores["employment"] += 1
    
    # Vendor keywords
    vendor_keywords = [
        "vendor", "payment", "invoice", "liability", "indemnification",
        "warranty", "deliverables", "services", "customer"
    ]
    for kw in vendor_keywords:
        if kw in combined_text:
            scores["vendor"] += 1
    
    # Get highest score
    max_score = max(scores.values())
    if max_score == 0:
        return "other"
    
    return max(scores, key=scores.get)


async def process_contract_analysis(contract_id: str, clauses: List[str], contract_type: str):
    """
    Background task to analyze all clauses and calculate health score.
    Saves results to Supabase if configured.
    
    Args:
        contract_id: The contract ID
        clauses: List of clause texts
        contract_type: Detected contract type
    """
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
            clause_text = str(clause.get("text", "") or
                          clause.get("original_text", "") or
                          clause.get("content", "")) if isinstance(clause, dict) else str(clause)
            logger.info(f"clause keys: {list(clause.keys()) if isinstance(clause, dict) else f'type={type(clause).__name__}'}")
            logger.info(f"clause_text preview: {clause_text[:100]}")

            # Step 1: Retrieve similar benchmarks from RAG
            benchmarks = retrieve_benchmarks(clause_text, k=3)
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
                "risk_level": result.get("risk_level", "medium"),
                "risk_score": result.get("risk_score", 50),
                "risk_reason": result.get("risk_reason", ""),
                "plain_english": result.get("plain_english", ""),
                "key_concerns": result.get("key_concerns", []),
                "suggested_fix": result.get("suggested_fix", ""),
                "provider_used": result.get("provider_used", "unknown"),
            }

            analyzed_clauses.append(clause_result)

        except Exception as e:
            import traceback
            logger.error(f"FULL TRACEBACK: {traceback.format_exc()}")
            analyzed_clauses.append({
                "id": f"{contract_id}_clause_{idx}",
                "clause_index": idx,
                "clause_title": f"Clause {idx + 1}",
                "original_text": str(clause) if not isinstance(clause, dict) else (clause.get("text", "") or clause.get("original_text", "") or clause.get("content", "")),
                "risk_level": "medium",
                "risk_score": 50,
                "risk_reason": f"Analysis failed: {str(e)}",
                "plain_english": "This clause could not be analyzed.",
                "key_concerns": ["Analysis error occurred"],
                "suggested_fix": "Please retry the analysis.",
                "provider_used": "error",
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
    }
    
    # Update contract store status
    if contract_id in contract_store:
        contract_store[contract_id]["status"] = "complete"
    
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
    
    # Detect contract type
    contract_type = detect_contract_type(record["clauses"])
    contract_store[contract_id]["contract_type"] = contract_type
    logger.info(f"Detected contract type: {contract_type}")
    
    # Start background analysis
    background_tasks.add_task(
        process_contract_analysis,
        contract_id=contract_id,
        clauses=record["clauses"],
        contract_type=contract_type,
    )
    
    return {
        "contract_id": contract_id,
        "status": "analysis_started",
        "message": f"Analyzing {len(record['clauses'])} clauses in background",
        "total_clauses": len(record["clauses"]),
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
                }
                
                # Transform clauses to response format
                clauses = []
                for clause in db_contract.get("clauses", []):
                    clauses.append({
                        "id": str(clause.get("id", "")),
                        "clause_index": clause.get("clause_index", 0),
                        "clause_title": clause.get("clause_title", ""),
                        "original_text": clause.get("original_text", ""),
                        "risk_level": clause.get("risk_level", "medium"),
                        "risk_score": clause.get("risk_score", 50),
                        "risk_reason": clause.get("risk_reason", ""),
                        "plain_english": clause.get("plain_english", ""),
                        "key_concerns": clause.get("key_concerns", []),
                        "suggested_fix": clause.get("suggested_fix", ""),
                    })
                
                return {
                    "contract_id": contract_id,
                    "filename": db_contract.get("filename", ""),
                    "status": "complete",
                    "contract_type": db_contract.get("contract_type", "unknown"),
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
                    "risk_level": clause.get("risk_level", "medium"),
                    "risk_score": clause.get("risk_score", 50),
                    "risk_reason": clause.get("risk_reason", ""),
                    "plain_english": clause.get("plain_english", ""),
                    "key_concerns": clause.get("key_concerns", []),
                    "suggested_fix": clause.get("suggested_fix", ""),
                }
        except Exception as e:
            logger.error(f"Failed to get clause from Supabase: {e}")
    
    raise HTTPException(status_code=404, detail="Analysis results not found")
