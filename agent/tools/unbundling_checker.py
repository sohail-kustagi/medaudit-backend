"""
Tool: check_unbundling
======================
Evaluates a group of billed CPT codes against the National Correct Coding
Initiative (NCCI) bundling rules stored in the `cpt_codes.unbundling_group`
column.

Logic:
  1. Query the `cpt_codes` table for each code in the list.
  2. Group codes by their `unbundling_group` value.
  3. If ≥ 2 codes in a list share the same non-null group, it is an
     unbundling violation — they should be billed under a single
     comprehensive panel code.
  4. Returns the suggested bundle code, estimated savings, and explanation.

NCCI Panel Reference (seeded in cms_pfs_sample.csv):
  - CMP_PANEL    → 80053  Comprehensive Metabolic Panel  ($14.53)
  - BMP_PANEL    → 80048  Basic Metabolic Panel          ($11.42)
  - LIPID_PANEL  → 80061  Lipid Panel                    ($18.02)
  - CBC_PANEL    → 85025  CBC with Differential          ($10.44)
"""

import asyncio
import logging
from typing import Optional, Any

from strands import tool  # type: ignore[import]

logger = logging.getLogger(__name__)

# Canonical bundle codes per unbundling group (derived from NCCI / CMS PFS)
PANEL_BUNDLE_CODE: dict[str, str] = {
    "CMP_PANEL": "80053",
    "BMP_PANEL": "80048",
    "LIPID_PANEL": "80061",
    "CBC_PANEL": "85025",
    # Wound repair bundles (simple/intermediate/complex by body area)
    "WOUND_REPAIR_SIMPLE": "12001",
    "WOUND_REPAIR_INTERMEDIATE": "12031",
    "WOUND_REPAIR_COMPLEX": "13100",
}

# Approximate Medicare national rates for bundle codes (cents precision)
BUNDLE_RATE: dict[str, float] = {
    "80053": 14.53,
    "80048": 11.42,
    "80061": 18.02,
    "85025": 10.44,
    "12001": 130.00,
    "12031": 160.00,
    "13100": 310.00,
}


async def _async_check_unbundling(
    cpt_code_list: list[str],
    session: Optional[Any] = None,
) -> dict:
    try:
        from sqlalchemy import select, and_
        from backend.app.db.session import async_session_factory
        from backend.app.db.models.cpt_code import CptCode

        async def _execute_query(s):
            stmt = select(CptCode).where(CptCode.code.in_(cpt_code_list))
            result = await s.execute(stmt)
            return {row.code: row for row in result.scalars().all()}

        if session is not None:
            cpt_rows = await _execute_query(session)
        else:
            async with async_session_factory() as new_session:
                cpt_rows = await _execute_query(new_session)
    except (ImportError, Exception) as exc:
        logger.debug("Database unbundling query skipped or failed: %s", exc)
        cpt_rows = {}

    # Group by unbundling_group
    groups: dict[str, list[str]] = {}
    for code in cpt_code_list:
        row = cpt_rows.get(code)
        if row and row.unbundling_group:
            groups.setdefault(row.unbundling_group, []).append(code)

    offending_codes: list[str] = []
    suggested_bundle: Optional[str] = None
    estimated_savings: float = 0.0
    explanation_parts: list[str] = []

    for group, codes in groups.items():
        if len(codes) >= 2:
            offending_codes.extend(codes)
            bundle_code = PANEL_BUNDLE_CODE.get(group)
            bundle_rate = BUNDLE_RATE.get(bundle_code, 0.0) if bundle_code else 0.0

            # Sum of individual Medicare rates billed separately
            individual_total = sum(
                cpt_rows[c].medicare_national_rate
                for c in codes
                if c in cpt_rows
            )
            savings = individual_total - bundle_rate

            if bundle_code and (suggested_bundle is None or savings > estimated_savings):
                suggested_bundle = bundle_code
                estimated_savings = max(savings, 0.0)

            codes_str = ", ".join(codes)
            explanation_parts.append(
                f"Codes {codes_str} belong to NCCI group '{group}'. "
                f"Under CMS CCI guidelines these should be billed as a single "
                f"{'code ' + bundle_code if bundle_code else 'comprehensive procedure'}. "
                f"Billing them individually constitutes unbundling."
            )

    has_unbundling = len(offending_codes) > 0
    return {
        "has_unbundling": has_unbundling,
        "offending_codes": offending_codes,
        "suggested_bundled_code": suggested_bundle,
        "estimated_savings": round(estimated_savings, 2),
        "explanation": " ".join(explanation_parts) if explanation_parts else (
            "No unbundling violations detected. All codes appear to be "
            "legitimately billed as separate procedures."
        ),
    }


def _run_async(coro):
    """Run a coroutine safely regardless of current event loop state."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


@tool
def check_unbundling(cpt_code_list: list[str]) -> dict:
    """
    Cross-reference a list of CPT codes against medical bundling rules.

    Checks whether any combination of codes in the provided list violates
    National Correct Coding Initiative (NCCI) bundling edits. If multiple
    codes share the same NCCI unbundling group, they should be billed as
    a single comprehensive procedure code.

    Args:
        cpt_code_list: List of CPT codes appearing on the patient's bill,
                       e.g. ['84132', '84295', '80048'].

    Returns:
        dict with keys:
            - has_unbundling (bool): True if at least one bundling violation found.
            - offending_codes (list[str]): The codes triggering the violation.
            - suggested_bundled_code (str | None): Recommended replacement code.
            - estimated_savings (float): Dollar amount patient is over-billed.
            - explanation (str): Human-readable NCCI citation and explanation.
    """
    logger.info("check_unbundling called with codes: %s", cpt_code_list)
    if not cpt_code_list:
        return {
            "has_unbundling": False,
            "offending_codes": [],
            "suggested_bundled_code": None,
            "estimated_savings": 0.0,
            "explanation": "No CPT codes provided.",
        }
    return _run_async(_async_check_unbundling(cpt_code_list))
