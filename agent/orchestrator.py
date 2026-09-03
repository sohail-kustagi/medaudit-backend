"""
MedAudit Agent Orchestrator
============================
Primary Strands agent loop and execution entrypoint.

This module builds and invokes a `strands.Agent` configured with:
  - The MedAudit auditor system prompt
  - The `think` tool (extended reasoning)
  - Three custom @tool functions: query_policy_rules, check_unbundling,
    draft_appeal_letter

Public API:
    run_medaudit_agent(enriched_bill_dict: dict) -> dict
        Async entrypoint called by bedrock_service.py.
        Returns a dict with {"status": "cleared"} or the full disputed payload.

Fallback:
    If no valid credentials are available (Mode C / HEURISTIC), raises
    RuntimeError so that agent_dispatcher.py can catch it and invoke
    `default_audit_heuristic` instead.
"""

import asyncio
import json
import logging
import re
from typing import Any, Dict

from agent.config import AgentConfig, ProviderMode, resolve_agent_config
from agent.prompts import MEDAUDIT_SYSTEM_PROMPT
from agent.schemas.output_decision import AgentDecision

logger = logging.getLogger(__name__)


def _build_agent_prompt(enriched_bill_dict: Dict[str, Any]) -> str:
    """Construct the user-facing prompt string with the enriched bill JSON."""
    bill_json = json.dumps(enriched_bill_dict, indent=2, default=str)
    return (
        "Please audit the following enriched medical bill. "
        "Follow your STRICT OPERATIONAL RULES exactly:\n\n"
        f"```json\n{bill_json}\n```\n\n"
        "Begin with STEP 1 (THINK), then proceed through STEP 2 (VERIFY) "
        "and STEP 3 (DECIDE). Return ONLY the final JSON decision payload."
    )


def _extract_json_from_response(raw_text: str) -> Dict[str, Any]:
    """
    Extract and parse the first valid JSON object from agent output.

    Handles:
      - Bare JSON
      - ```json ... ``` fenced blocks
      - ```  ... ``` fenced blocks
    """
    # Try to find a fenced JSON block first
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
    if fenced:
        candidate = fenced.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # Try to find a raw JSON object (first { ... })
    brace_match = re.search(r"(\{.*\})", raw_text, re.DOTALL)
    if brace_match:
        candidate = brace_match.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    raise ValueError(
        f"Could not extract valid JSON from agent response. "
        f"Raw output (first 500 chars): {raw_text[:500]}"
    )


def _sanitise_decision(raw_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and sanitise the raw JSON dict from the agent using the
    AgentDecision Pydantic schema, then convert back to a plain dict
    compatible with agent_dispatcher.py expectations.
    """
    try:
        decision = AgentDecision(**raw_dict)
        return decision.to_dict()
    except Exception as e:
        logger.warning(
            "AgentDecision validation failed: %s — raw dict: %s",
            e,
            raw_dict,
        )
        # Minimal safe fallback: if we got a status, return it
        status = raw_dict.get("status", "cleared")
        if status not in ("cleared", "disputed"):
            status = "cleared"
        if status == "cleared":
            return {"status": "cleared"}
        # Return as-is for disputed (dispatcher handles any missing fields)
        return raw_dict


TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "query_policy_rules",
            "description": (
                "Query patient insurance policy coverage, pre-authorization "
                "requirements, and coinsurance percentage for a given CPT code."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "string",
                        "description": "Patient or policy ID",
                    },
                    "cpt_code": {
                        "type": "string",
                        "description": "5-digit CPT procedure code",
                    },
                    "plan_id": {
                        "type": "string",
                        "description": "Insurance plan identifier (e.g. AETNA_CHOICE_POS)",
                    },
                },
                "required": ["patient_id", "cpt_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_unbundling",
            "description": (
                "Check a list of CPT codes against CMS NCCI bundling edits to detect "
                "unbundled laboratory or procedural panels."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cpt_code_list": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of billed CPT codes to analyze",
                    }
                },
                "required": ["cpt_code_list"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draft_appeal_letter",
            "description": (
                "Draft a formal medical billing dispute appeal letter citing "
                "the No Surprises Act, CMS CCI guidelines, and AMA CPT rules."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_info": {
                        "type": "object",
                        "description": "Patient demographic and policy details",
                    },
                    "provider_info": {
                        "type": "object",
                        "description": "Billing provider details including name and NPI",
                    },
                    "disputed_codes": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "List of line items with billing discrepancies",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Clinical and financial justification for the dispute",
                    },
                },
                "required": [
                    "patient_info",
                    "provider_info",
                    "disputed_codes",
                    "reasoning",
                ],
            },
        },
    },
]


def _dispatch_tool(name: str, args: dict) -> str:
    from agent.tools import query_policy_rules, check_unbundling, draft_appeal_letter
    try:
        if name == "query_policy_rules":
            return json.dumps(query_policy_rules(**args))
        elif name == "check_unbundling":
            return json.dumps(check_unbundling(**args))
        elif name == "draft_appeal_letter":
            return json.dumps(draft_appeal_letter(**args))
        return json.dumps({"error": f"Unknown tool: {name}"})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


async def run_mantle_direct_audit(
    enriched_bill_dict: Dict[str, Any],
    cfg: AgentConfig,
) -> Dict[str, Any]:
    """
    Direct OpenAI client execution against Bedrock Mantle /chat/completions endpoint.
    Uses model="openai.gpt-oss-120b" and header {"OpenAI-Project": "default"}.
    Supports autonomous tool execution loop conforming to Bedrock Mantle API docs.
    """
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        base_url=cfg.mantle_base_url,
        api_key=cfg.mantle_api_key or "mock_key",
        default_headers={"OpenAI-Project": cfg.mantle_workspace_id or "default"},
    )
    user_prompt = _build_agent_prompt(enriched_bill_dict)
    messages: list[Any] = [
        {"role": "system", "content": MEDAUDIT_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    for _ in range(5):
        response = await client.chat.completions.create(
            model=cfg.model_id or "openai.gpt-oss-120b",
            messages=messages,
            tools=TOOLS_SCHEMA,
            tool_choice="auto",
            max_tokens=cfg.max_tokens,
            temperature=cfg.temperature,
        )
        msg = response.choices[0].message
        messages.append(msg)

        if not msg.tool_calls:
            raw_text = msg.content or ""
            raw_dict = _extract_json_from_response(raw_text)
            return _sanitise_decision(raw_dict)

        for tool_call in msg.tool_calls:
            fn_name = tool_call.function.name
            try:
                fn_args = json.loads(tool_call.function.arguments)
            except Exception:
                fn_args = {}
            tool_result = _dispatch_tool(fn_name, fn_args)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result,
            })

    last_content = getattr(messages[-1], "content", None) or ""
    return _sanitise_decision(_extract_json_from_response(last_content))


async def run_medaudit_agent(enriched_bill_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute the MedAudit Strands agent on an enriched bill payload.

    Args:
        enriched_bill_dict: Dict representation of an EnrichedBill, as
                            produced by the enrichment pipeline and
                            serialised via model_dump().

    Returns:
        A dict matching the AgentDecision schema:
          {"status": "cleared"}
          or
          {"status": "disputed", "disputed_codes": [...], "reasoning": "...",
           "dispute_letter_markdown": "..."}

    Raises:
        RuntimeError: If mode is HEURISTIC (no credentials) — caller should
                      catch and invoke default_audit_heuristic instead.
        Exception:    On unexpected model or network failures.
    """
    cfg = resolve_agent_config()

    if cfg.mode == ProviderMode.HEURISTIC:
        raise RuntimeError(
            "No LLM credentials configured. Triggering heuristic fallback."
        )

    try:
        from strands import Agent  # type: ignore[import]
        from strands_tools import think  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "strands-agents / strands-agents-tools not installed. "
            "Run: pip install strands-agents strands-agents-tools"
        ) from exc

    from agent.adapter import get_strands_model
    from agent.tools import (
        check_unbundling,
        draft_appeal_letter,
        query_policy_rules,
    )

    model = get_strands_model(cfg)

    agent = Agent(
        model=model,
        system_prompt=MEDAUDIT_SYSTEM_PROMPT,
        tools=[think, query_policy_rules, check_unbundling, draft_appeal_letter],
    )

    user_prompt = _build_agent_prompt(enriched_bill_dict)

    logger.info(
        "MedAudit agent invoked: model=%s mode=%s document_id=%s",
        cfg.model_id,
        cfg.mode,
        enriched_bill_dict.get("document_id", "unknown"),
    )

    # Strands Agent.__call__ is synchronous; run in executor to stay async-safe
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: agent(user_prompt))

        # Extract the text content from the agent response
        raw_text: str
        if hasattr(response, "message"):
            content = response.message.get("content", [])
            text_parts = [
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            raw_text = "\n".join(text_parts)
        else:
            raw_text = str(response)

        logger.debug("Agent raw response (first 800 chars): %s", raw_text[:800])

        raw_dict = _extract_json_from_response(raw_text)
        decision = _sanitise_decision(raw_dict)

        logger.info(
            "MedAudit agent decision: status=%s disputed_codes=%d",
            decision.get("status"),
            len(decision.get("disputed_codes", [])),
        )

        return decision

    except Exception as exc:
        if cfg.mode == ProviderMode.BEDROCK_MANTLE:
            logger.warning(
                "Strands agent invocation failed (%s). Attempting direct Bedrock Mantle OpenAI completion...",
                exc,
            )
            return await run_mantle_direct_audit(enriched_bill_dict, cfg)
        raise exc
