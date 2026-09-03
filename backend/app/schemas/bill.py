from datetime import date
from typing import List, Optional
from pydantic import BaseModel, Field


class BillingLineItem(BaseModel):
    line_number: int
    cpt_code: Optional[str] = Field(None, description="Extracted 5-char CPT or HCPCS code")
    description: str = Field(..., description="Description of the service or item")
    units: int = Field(default=1, description="Quantity/units billed")
    billed_amount: float = Field(..., description="Billed charge amount in USD")
    date_of_service: Optional[str] = Field(None, description="Date service rendered")
    raw_text: Optional[str] = Field(None, description="Original unparsed text snippet")


class PatientInfo(BaseModel):
    name: Optional[str] = None
    dob: Optional[str] = None
    policy_id: Optional[str] = None
    account_number: Optional[str] = None
    address: Optional[str] = None


class ProviderInfo(BaseModel):
    name: Optional[str] = None
    npi: Optional[str] = None
    tax_id: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None


class StructuredBill(BaseModel):
    patient: PatientInfo
    provider: ProviderInfo
    statement_date: Optional[str] = None
    due_date: Optional[str] = None
    total_billed: float
    line_items: List[BillingLineItem]


class EnrichedLineItem(BillingLineItem):
    standard_description: Optional[str] = None
    medicare_national_rate: Optional[float] = None
    price_disparity_ratio: Optional[float] = None  # billed_amount / medicare_rate
    unbundling_group: Optional[str] = None
    is_covered: Optional[bool] = None
    requires_preauth: Optional[bool] = None
    coinsurance_rate: Optional[float] = None
    policy_notes: Optional[str] = None


class EnrichedBill(BaseModel):
    document_id: str
    patient: PatientInfo
    provider: ProviderInfo
    statement_date: Optional[str] = None
    total_billed: float
    line_items: List[EnrichedLineItem]
    insurance_plan_id: str
