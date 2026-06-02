"""
Upload API Route
Handles PDF contract uploads and initial processing (PDF → clauses).
Priority 4: Production uploads require authenticated user; dev uploads use deterministic dummy user.
"""

import uuid
import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request, Depends

from models.contract import UploadResponse
from core.status import CONTRACT_STATUS_UPLOADED
from db.queries import create_contract, ensure_user_profile, update_contract_storage_metadata
from db.supabase_client import is_supabase_configured
from api.middleware.auth import require_user, DEV_MODE
from services.storage import save_contract_file

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory store for development fallback and caching
# contract_store: {contract_id: {filename, text, clauses, status, ...}}
contract_store: Dict[str, Dict[str, Any]] = {}


@router.post("/upload", response_model=UploadResponse)
async def upload_contract(
    request: Request,
    file: UploadFile = File(...),
    contract_type: Optional[str] = Form(None),
    user: Dict[str, Any] = Depends(require_user),
):
    """
    Upload a contract PDF and start the analysis pipeline.
    Production requires a valid authenticated user.
    Dev mode falls back to a deterministic dummy user.
    """
    user_id = user.get("id")
    user_email = user.get("email")

    # In production, require a real user_id
    if not DEV_MODE and not user_id:
        raise HTTPException(status_code=401, detail="Authentication required to upload contracts.")

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

    contract_id = str(uuid.uuid4())
    mime_type = file.content_type or "application/pdf"

    try:
        storage_path = await save_contract_file(
            contract_id=contract_id,
            user_id=user_id,
            filename=file.filename,
            file_bytes=file_bytes,
            mime_type=mime_type,
        )
    except Exception as e:
        logger.error(f"Failed to store contract PDF: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to store contract PDF: {str(e)}")

    db_contract = None
    try:
        if user_id:
            await ensure_user_profile(user_id=user_id, email=user_email)

        db_contract = await create_contract(
            user_id=user_id,
            filename=file.filename,
            contract_type=selected_contract_type,
            contract_id=contract_id,
            storage_path=storage_path,
            file_size_bytes=len(file_bytes),
            mime_type=mime_type,
            status=CONTRACT_STATUS_UPLOADED,
        )
        if not db_contract:
            await update_contract_storage_metadata(contract_id, storage_path, len(file_bytes), mime_type)
            if is_supabase_configured():
                raise RuntimeError("Contract metadata could not be saved to Supabase")
    except Exception as e:
        logger.error(f"Failed to create contract in database: {e}")
        if is_supabase_configured():
            raise HTTPException(status_code=500, detail="Failed to save contract metadata")

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
        "status": CONTRACT_STATUS_UPLOADED,
        "progress_percent": 0,
        "status_message": "Uploaded and ready for analysis",
        "storage_path": storage_path,
        "file_size_bytes": len(file_bytes),
        "mime_type": mime_type,
        "text": None,
        "clauses": None,
        "error": None,
        "db_record": db_contract is not None,  # Track if saved to DB
    }

    return UploadResponse(
        contract_id=contract_id,
        status=CONTRACT_STATUS_UPLOADED,
        message="PDF uploaded. Start analysis when ready."
    )


@router.get("/upload-debug/{contract_id}")
async def get_upload_debug(
    contract_id: str,
    request: Request,
    user: Dict[str, Any] = Depends(require_user),
):
    """
    Debug endpoint to view extracted text and clauses for a contract.
    Disabled in production; only available in DEV_MODE for the contract owner.
    """
    if not DEV_MODE:
        raise HTTPException(status_code=404, detail="Not found")

    # Even in dev, require ownership
    user_id = user.get("id")

    # Check in-memory first
    if contract_id in contract_store:
        record = contract_store[contract_id]
        if record.get("user_id") == user_id:
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

    raise HTTPException(status_code=404, detail="Contract not found")
