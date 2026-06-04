"""
Pydantic Models for Contract data
"""

from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel
from datetime import datetime


class Clause(BaseModel):
    """Individual clause analysis result."""
    id: Optional[str] = None
    clause_index: int
    clause_title: str
    original_text: str
    risk_level: Literal["high", "medium", "low", "unknown"]
    risk_score: Optional[int] = None  # 0-100 when analysis succeeds
    risk_reason: str
    plain_english: str
    key_concerns: List[str]
    suggested_fix: str
    analysis_status: Literal["success", "retried", "failed"] = "success"
    retry_count: int = 0
    error_message: Optional[str] = None
    provider_used: Optional[str] = None
    retrieved_benchmarks: List[Dict[str, Any]] = []
    cited_benchmark_ids: List[str] = []
    risk_rule_applied: Optional[str] = None
    evidence_summary: Optional[str] = None
    benchmark_alignment: Literal["strong", "partial", "weak", "none"] = "none"
    predicted_clause_type: Optional[str] = None
    clause_type_confidence: float = 0.0
    clause_type_matched_terms: List[str] = []
    retrieval_quality: Literal["strong", "partial", "none"] = "none"
    eligible_benchmark_count: int = 0
    citation_suppressed: bool = False
    clause_number: Optional[str] = None
    parent_clause_number: Optional[str] = None
    clause_level: int = 1
    section_type: str = "clause"
    is_scored: bool = True
    subclauses: List[Dict[str, Any]] = []
    parsed_section_count: int = 1
    created_at: Optional[datetime] = None


class HealthScore(BaseModel):
    """Overall contract health assessment."""
    score: int  # 0-100
    grade: str  # A, B, C, D, F, or N/A
    label: str  # Low Risk, Moderate Risk, High Risk, Critical Risk, etc.
    risk_counts: dict  # {"high": 4, "medium": 3, "low": 6}
    total_clauses: int
    unknown_count: int = 0
    failed_clause_count: int = 0
    scored_clause_count: int = 0
    top_level_clause_count: Optional[int] = None
    parsed_section_count: Optional[int] = None


class Contract(BaseModel):
    """Contract document model."""
    id: Optional[str] = None
    user_id: Optional[str] = None
    filename: str
    contract_type: Optional[str] = None  # effective type for compatibility
    selected_contract_type: Optional[str] = None
    detected_contract_type: Optional[str] = None
    contract_type_confidence: Optional[float] = None
    status: Literal[
        "uploaded",
        "queued",
        "extracting",
        "clauses_extracted",
        "retrieving_benchmarks",
        "analysing",
        "saving_results",
        "complete",
        "failed",
    ] = "uploaded"
    progress_percent: int = 0
    status_message: Optional[str] = None
    error_message: Optional[str] = None
    storage_path: Optional[str] = None
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    health: Optional[HealthScore] = None
    clauses: Optional[List[Clause]] = None
    uploaded_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class UploadResponse(BaseModel):
    """Response from upload endpoint."""
    contract_id: str
    status: str
    message: str


class AnalysisResponse(BaseModel):
    """Response from analysis endpoint."""
    contract_id: str
    filename: str
    status: str
    health: Optional[HealthScore] = None
    clauses: List[Clause] = []
