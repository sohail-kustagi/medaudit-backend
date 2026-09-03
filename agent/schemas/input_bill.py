"""
Agent Input Schema
==================
Mirrors backend/app/schemas/bill.py (EnrichedBill) but as a standalone
Pydantic model so the agent package has no circular import dependency.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class AgentPatientInfo(BaseModel):
    name: Optional[str] = None
    dob: Optional[str] = None
    policy_id: Optional[str] = None
    account_number: Optional[str] = None
    address: Optional[str] = None


class AgentProviderInfo(BaseModel):
    name: Optional[str] = None
    npi: Optional[str] = None
    tax_id: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None


class AgentLineItem(BaseModel):
    line_number: int
    cpt_code: Optional[str] = None
    description: str
    units: int = 1
    billed_amount: float
    date_of_service: Optional[str] = None
    raw_text: Optional[str] = None
    # Enriched fields
    standard_description: Optional[str] = None
    medicare_national_rate: Optional[float] = None
    price_disparity_ratio: Optional[float] = None
    unbundling_group: Optional[str] = None
    is_covered: Optional[bool] = None
    requires_preauth: Optional[bool] = None
    coinsurance_rate: Optional[float] = None
    policy_notes: Optional[str] = None


class AgentInputBill(BaseModel):
    """Enriched bill payload handed to the MedAudit agent."""

    document_id: str
    patient: AgentPatientInfo
    provider: AgentProviderInfo
    statement_date: Optional[str] = None
    total_billed: float
    line_items: List[AgentLineItem]
    insurance_plan_id: str = Field(default="AETNA_CHOICE_POS")
