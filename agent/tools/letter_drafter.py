"""
Tool: draft_appeal_letter
=========================
Compiles verified billing discrepancies, provider details, and statutory
citations into a formal dispute letter using a Jinja2 template.

The letter cites:
  - No Surprises Act (Public Health Service Act § 2799A-1)
  - CMS National Correct Coding Initiative (CCI) guidelines
  - AMA CPT Coding Guidelines
  - False Claims Act (31 U.S.C. §§ 3729–3733)
"""

import logging
import uuid
from datetime import date
from pathlib import Path

from strands import tool  # type: ignore[import]

logger = logging.getLogger(__name__)

TEMPLATE_PATH = (
    Path(__file__).parent.parent / "prompts" / "templates" / "appeal_letter.md.j2"
)


@tool
def draft_appeal_letter(
    patient_info: dict,
    provider_info: dict,
    disputed_codes: list[dict],
    reasoning: str,
) -> dict:
    """
    Drafts a formal, legally grounded medical bill dispute letter.

    Args:
        patient_info: Dict containing patient details:
                      - name (str): Patient full name.
                      - dob (str): Date of birth (YYYY-MM-DD or formatted).
                      - policy_id (str): Insurance policy/member ID.
                      - account_number (str): Medical account number.
                      - address (str): Patient mailing address.
        provider_info: Dict containing provider details:
                       - name (str): Facility or provider name.
                       - npi (str): National Provider Identifier.
                       - address (str): Provider billing address.
        disputed_codes: List of dicts, each containing:
                        - cpt_code (str): CPT procedure code.
                        - billed_description (str): Description as billed.
                        - standard_description (str): AMA/CMS standard description.
                        - billed_amount (float): Amount charged.
                        - medicare_baseline (float): CMS Medicare national rate.
                        - issue (str): One of UPCODING, UNBUNDLING, PRICE_DISPARITY.
        reasoning: Clinical and financial audit reasoning string explaining
                   the basis for the dispute (sourced from agent's analysis).

    Returns:
        dict with keys:
            - letter_markdown (str): Complete dispute letter formatted in Markdown.
            - formal_reference_id (str): Unique tracking reference ID.
    """
    try:
        from jinja2 import Environment, FileSystemLoader, StrictUndefined

        env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_PATH.parent)),
            undefined=StrictUndefined,
            autoescape=False,
        )
        template = env.get_template(TEMPLATE_PATH.name)
    except Exception as e:
        logger.error("Failed to load Jinja2 template: %s", e)
        raise RuntimeError(f"Appeal letter template load failed: {e}") from e

    formal_reference_id = f"MEDAUDIT-{uuid.uuid4().hex[:8].upper()}"
    today = date.today().strftime("%B %d, %Y")

    total_disputed = sum(c.get("billed_amount", 0.0) for c in disputed_codes)
    total_baseline = sum(c.get("medicare_baseline", 0.0) for c in disputed_codes)

    try:
        letter_markdown = template.render(
            formal_reference_id=formal_reference_id,
            date=today,
            patient_info=patient_info,
            provider_info=provider_info,
            disputed_codes=disputed_codes,
            reasoning=reasoning,
            total_disputed=total_disputed,
            total_baseline=total_baseline,
        )
    except Exception as e:
        logger.error("Jinja2 template rendering failed: %s", e)
        raise RuntimeError(f"Appeal letter rendering failed: {e}") from e

    logger.info(
        "draft_appeal_letter: generated letter %s for %d disputed codes",
        formal_reference_id,
        len(disputed_codes),
    )

    return {
        "letter_markdown": letter_markdown,
        "formal_reference_id": formal_reference_id,
    }
