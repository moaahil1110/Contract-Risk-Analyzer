"""
Upload API Route
Handles PDF contract uploads and initial processing (PDF → clauses).
Week 3: Added Supabase integration with in-memory fallback
"""

import uuid
import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks, Request, Depends

from models.contract import UploadResponse
from pipeline.pdf_parser import extract_text_from_pdf
from pipeline.clause_splitter import split_clauses
from db.queries import create_contract, ensure_user_profile
from api.middleware.auth import optional_user

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory store for development fallback and caching
# contract_store: {contract_id: {filename, text, clauses, status, ...}}
contract_store: Dict[str, Dict[str, Any]] = {}


@router.post("/upload", response_model=UploadResponse)
async def upload_contract(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    contract_type: Optional[str] = Form(None),
    user: Optional[Dict[str, Any]] = Depends(optional_user),
):
    """
    Upload a contract PDF and start the analysis pipeline.
    
    Args:
        file: PDF file to analyze
        contract_type: Type of contract (nda, employment, vendor, other)
    
    Returns:
        UploadResponse with contract_id and status
    """
    # Get user ID from the authenticated user
    user_id = user.get("id") if user else None
    user_email = user.get("email") if user else None
    selected_contract_type = (contract_type or "other").lower().strip()
    if selected_contract_type not in {"nda", "employment", "vendor", "other"}:
        selected_contract_type = "other"
    
    # Validate file type
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")
    
    # Read file content
    try:
        file_bytes = await file.read()
        if len(file_bytes) == 0:
            raise HTTPException(status_code=400, detail="Empty file uploaded")
        if len(file_bytes) > 50 * 1024 * 1024:  # 50MB limit
            raise HTTPException(status_code=400, detail="File too large (max 50MB)")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reading file: {e}")
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")
    
    # Create contract in Supabase (or generate UUID for fallback)
    # In DEV_MODE, user_id may be None - Supabase will store NULL for user_id
    db_contract = None
    try:
        if user_id:
            await ensure_user_profile(user_id=user_id, email=user_email)
        
        db_contract = await create_contract(
            user_id=user_id,
            filename=file.filename,
            contract_type=selected_contract_type
        )
    except Exception as e:
        logger.error(f"Failed to create contract in database: {e}")
    
    # Use database ID if available, otherwise generate UUID
    contract_id = db_contract["id"] if db_contract else str(uuid.uuid4())
    
    # Store in memory (for both fallback and caching)
    contract_store[contract_id] = {
        "id": contract_id,
        "user_id": user_id,
        "filename": file.filename,
        "contract_type": selected_contract_type,
        "selected_contract_type": selected_contract_type,
        "detected_contract_type": None,
        "contract_type_confidence": 0,
        "contract_type_conflict": False,
        "status": "processing",
        "text": None,
        "clauses": None,
        "error": None,
        "db_record": db_contract is not None,  # Track if saved to DB
    }
    
    # Process in background (for now, run synchronously for testing)
    try:
        # Step 1: Extract text from PDF
        logger.info(f"[{contract_id}] Extracting text from PDF...")
        text = extract_text_from_pdf(file_bytes)
        contract_store[contract_id]["text"] = text
        
        if not text or len(text.strip()) == 0:
            raise ValueError("No text could be extracted from the PDF")
        
        # Step 2: Split into clauses
        logger.info(f"[{contract_id}] Splitting into clauses...")
        clauses = await split_clauses(text)
        contract_store[contract_id]["clauses"] = clauses
        
        # Update status
        contract_store[contract_id]["status"] = "clauses_extracted"
        
        logger.info(f"[{contract_id}] Pipeline complete: {len(clauses)} clauses extracted")
        
    except Exception as e:
        logger.error(f"[{contract_id}] Pipeline failed: {e}")
        contract_store[contract_id]["status"] = "failed"
        contract_store[contract_id]["error"] = str(e)
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
    
    clause_count = len(contract_store[contract_id].get("clauses", []))
    return UploadResponse(
        contract_id=contract_id,
        status="processing",
        message=f"Analysis started. PDF processed: {clause_count} clauses extracted."
    )


@router.get("/upload-debug/{contract_id}")
async def get_upload_debug(contract_id: str):
    """
    Debug endpoint to view extracted text and clauses for a contract.
    This is a temporary endpoint for Week 1 testing.
    """
    if contract_id not in contract_store:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    record = contract_store[contract_id]
    
    # Return a safe version (truncated text, clause count)
    return {
        "contract_id": contract_id,
        "filename": record["filename"],
        "status": record["status"],
        "contract_type": record["contract_type"],
        "user_id": record.get("user_id"),
        "db_record": record.get("db_record", False),
        "text_length": len(record["text"]) if record["text"] else 0,
        "text_preview": record["text"][:1000] + "..." if record["text"] else None,
        "clause_count": len(record["clauses"]) if record["clauses"] else 0,
        "clauses": [
            {
                "index": i,
                "length": len(c),
                "preview": c[:200] + "..." if len(c) > 200 else c
            }
            for i, c in enumerate(record["clauses"][:5] if record["clauses"] else [])
        ],
        "error": record.get("error"),
    }
