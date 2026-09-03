from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict
from backend.app.db.models.document import DocumentStatus


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime


class DisputedCodeItem(BaseModel):
    cpt_code: str
    billed_description: str
    standard_description: str
    billed_amount: float
    medicare_baseline: float
    issue: str  # UPCODING | UNBUNDLING | OUT_OF_NETWORK | PRICE_DISPARITY


class DocumentDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    status: DocumentStatus
    patient_info: Optional[Dict[str, Any]] = None
    provider_info: Optional[Dict[str, Any]] = None
    disputed_codes: Optional[List[DisputedCodeItem]] = None
    agent_reasoning: Optional[str] = None
    dispute_letter_markdown: Optional[str] = None
    created_at: datetime
    updated_at: datetime
