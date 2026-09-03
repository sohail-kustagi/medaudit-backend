"""
Agent Output Decision Schema
============================
Strictly typed output schemas for agent decisions, matching the JSON
payload format required by agent_dispatcher.py and the system prompt.
"""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class DisputedCode(BaseModel):
    cpt_code: str
    billed_description: str
    standard_description: str
    billed_amount: float
    medicare_baseline: float
    issue: Literal["UPCODING", "UNBUNDLING", "PRICE_DISPARITY"]


class AgentDecision(BaseModel):
    """Top-level output from run_medaudit_agent()."""

    status: Literal["cleared", "disputed"]
    disputed_codes: List[DisputedCode] = Field(default_factory=list)
    reasoning: Optional[str] = None
    dispute_letter_markdown: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialise to the dict format consumed by agent_dispatcher."""
        result: dict = {"status": self.status}
        if self.status == "disputed":
            result["disputed_codes"] = [c.model_dump() for c in self.disputed_codes]
            result["reasoning"] = self.reasoning or ""
            result["dispute_letter_markdown"] = self.dispute_letter_markdown or ""
        return result
