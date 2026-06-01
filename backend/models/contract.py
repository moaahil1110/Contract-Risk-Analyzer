"""
Pydantic Models for Contract data
"""

from typing import List, Optional, Literal
from pydantic import BaseModel
from datetime import datetime


class Clause(BaseModel):
    """Individual clause analysis result."""
    id: Optional[str] = None
    clause_index: int
    clause_title: str
    original_text: str
    risk_level: Literal["high", "medium", "low"]
    risk_score: int  # 0-100
    risk_reason: str
    plain_english: str
    key_concerns: List[str]
    suggested_fix: str
    provider_used: Optional[str] = None
    created_at: Optional[datetime] = None


class HealthScore(BaseModel):
    """Overall contract health assessment."""
    score: int  # 0-100
    grade: str  # A, B, C, D
    label: str  # Low Risk, Moderate Risk, High Risk, Critical Risk
    risk_counts: dict  # {"high": 4, "medium": 3, "low": 6}
    total_clauses: int


class Contract(BaseModel):
    """Contract document model."""
    id: Optional[str] = None
    user_id: Optional[str] = None
    filename: str
    contract_type: Optional[str] = None  # nda, employment, vendor, other
    status: Literal["processing", "complete", "failed"] = "processing"
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
