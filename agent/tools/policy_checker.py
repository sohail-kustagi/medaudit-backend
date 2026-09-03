"""
Tool: query_policy_rules
========================
Queries the patient's insurance plan coverage, deductible status,
pre-authorization criteria, and in-network co-insurance limits for a
given CPT code.

Database backing: `policy_rules` table (SQLAlchemy async session).

The tool uses a module-level synchronous session factory so it can be
called from within the Strands sync tool invocation context. A thread-safe
asyncio runner is used when no event loop is active.
"""

import asyncio
import logging
from typing import Optional, Any

from strands import tool  # type: ignore[import]

logger = logging.getLogger(__name__)

# ── Known plan aliases ────────────────────────────────────────────────────────
PLAN_ALIASES: dict[str, str] = {
    "AETNA": "AETNA_CHOICE_POS",
    "BCBS": "BCBS_STANDARD",
    "UNITED": "UNITED_HEALTH_GOLD",
    "CIGNA": "CIGNA_OPEN_ACCESS",
}


async def _async_query_policy(
    patient_id: str,
    cpt_code: str,
    plan_id: str,
    session: Optional[Any] = None,
) -> dict:
    resolved_plan = PLAN_ALIASES.get(plan_id.upper(), plan_id)
    rule = None
    try:
        from sqlalchemy import select
        from backend.app.db.session import async_session_factory
        from backend.app.db.models.policy_rule import PolicyRule

        async def _execute_query(s):
            stmt = select(PolicyRule).where(
                PolicyRule.plan_id == resolved_plan,
                PolicyRule.cpt_code == cpt_code,
            )
            result = await s.execute(stmt)
            return result.scalar_one_or_none()

        if session is not None:
            rule = await _execute_query(session)
        else:
            async with async_session_factory() as new_session:
                rule = await _execute_query(new_session)
    except (ImportError, Exception) as exc:
        logger.debug("Database lookup skipped or failed: %s", exc)
        rule = None

    if rule:
        return {
            "is_covered": rule.is_covered,
            "requires_preauth": rule.requires_preauth,
            "coinsurance_pct": rule.coinsurance_rate,
            "policy_notes": rule.policy_notes or "Standard coverage applies.",
            "plan_id": resolved_plan,
            "cpt_code": cpt_code,
        }

    # Default assumption when no explicit rule exists
    logger.info(
        "No policy rule found for plan=%s cpt=%s — applying defaults.",
        resolved_plan,
        cpt_code,
    )
    return {
        "is_covered": True,
        "requires_preauth": False,
        "coinsurance_pct": 0.20,
        "policy_notes": (
            "No explicit policy rule found. Standard 80/20 coinsurance applied."
        ),
        "plan_id": resolved_plan,
        "cpt_code": cpt_code,
    }


def _run_async(coro):
    """Run a coroutine safely regardless of current event loop state."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # In an already-running async context (e.g. FastAPI): use a new thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


@tool
def query_policy_rules(
    patient_id: str,
    cpt_code: str,
    plan_id: str = "AETNA_CHOICE_POS",
) -> dict:
    """
    Query patient insurance policy rules for a specific CPT procedure code.

    Args:
        patient_id: Patient or policy identification string.
        cpt_code: 5-character CPT/HCPCS code (e.g., '99215').
        plan_id: Insurance plan identifier. Supported plans include
                 AETNA_CHOICE_POS, BCBS_STANDARD, UNITED_HEALTH_GOLD,
                 CIGNA_OPEN_ACCESS. Aliases (AETNA, BCBS, etc.) are accepted.

    Returns:
        dict with keys:
            - is_covered (bool): Whether the procedure is covered by the plan.
            - requires_preauth (bool): Whether prior authorization is needed.
            - coinsurance_pct (float): Patient cost-sharing percentage (0.0–1.0).
            - policy_notes (str): Human-readable coverage notes.
            - plan_id (str): Resolved plan identifier used for the lookup.
            - cpt_code (str): The CPT code queried.
    """
    logger.info(
        "query_policy_rules called: patient_id=%s cpt_code=%s plan_id=%s",
        patient_id,
        cpt_code,
        plan_id,
    )
    return _run_async(_async_query_policy(patient_id, cpt_code, plan_id))
