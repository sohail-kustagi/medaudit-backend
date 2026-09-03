"""
Bedrock Service
===============
Provides `run_bedrock_audit`, the primary LLM audit entrypoint called by
`agent_dispatcher.py`.

Integration order:
  1. Delegates to `run_medaudit_agent` (Strands SDK orchestrator).
     - Mode A: Bedrock Mantle OpenAI-compatible proxy.
     - Mode B: Native Boto3 Bedrock Runtime.
  2. If the Strands agent raises (Mode C / no credentials / network error),
     the caller (`agent_dispatcher._execute_pipeline`) catches the exception
     and falls back to `default_audit_heuristic`.
"""

import logging
from typing import Dict, Any

from agent.orchestrator import run_medaudit_agent

logger = logging.getLogger(__name__)


async def run_bedrock_audit(enriched_bill_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a full LLM-powered audit using the MedAudit Strands agent.

    Invokes the Strands Agent SDK orchestrator which:
      - Uses the dual-provider gateway (Bedrock Mantle proxy or native Bedrock)
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
        RuntimeError: If no valid credentials are available (triggers heuristic
                      fallback in agent_dispatcher).
        Exception:    On model, network, or parsing failures (also triggers
                      heuristic fallback in agent_dispatcher).
    """
    logger.info(
        "run_bedrock_audit: delegating to Strands agent for document_id=%s",
        enriched_bill_dict.get("document_id", "unknown"),
    )
    return await run_medaudit_agent(enriched_bill_dict)
