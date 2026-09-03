"""
Bedrock Service
===============
Provides `run_bedrock_audit`, the primary LLM audit entrypoint called by
`agent_dispatcher.py`.

Integration order:
  1. Makes an HTTP POST request to the standalone LLM microservice.
  2. If the microservice fails (network error / 500 status),
     the caller (`agent_dispatcher._execute_pipeline`) catches the exception
     and falls back to `default_audit_heuristic`.
"""

import logging
import httpx
from typing import Dict, Any

from backend.app.config import settings

logger = logging.getLogger(__name__)


async def run_bedrock_audit(enriched_bill_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a full LLM-powered audit using the remote MedAudit Strands microservice.

    Sends a POST request to the LLM microservice which:
      - Runs a structured Think → Verify (tools) → Decide reasoning loop
      - Returns a strictly typed JSON decision payload

    Args:
        enriched_bill_dict: Dict representation of an EnrichedBill (output
                            of the enrichment pipeline, serialised via
                            model_dump()).

    Returns:
        dict: {"status": "cleared"} or
              {"status": "disputed", "disputed_codes": [...],
               "reasoning": "...", "dispute_letter_markdown": "..."}

    Raises:
        Exception: On network failures or non-200 responses (triggers
                   heuristic fallback in agent_dispatcher).
    """
    document_id = enriched_bill_dict.get("document_id", "unknown")
    logger.info(
        "run_bedrock_audit: delegating to LLM Microservice at %s for document_id=%s",
        settings.LLM_MICROSERVICE_URL,
        document_id,
    )
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            settings.LLM_MICROSERVICE_URL,
            json=enriched_bill_dict
        )
        response.raise_for_status()
        return response.json()
