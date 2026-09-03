import asyncio
import json
import logging
from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.document import Document, DocumentStatus
from backend.app.db.models.dispute import Dispute, DisputeStatus
from backend.app.db.session import async_session_factory
from backend.app.services.textract_service import textract_service
from backend.app.pipelines.structuring import structure_bill
from backend.app.pipelines.enrichment import enrich_bill
from backend.app.schemas.bill import EnrichedBill
from backend.app.services.bedrock_service import run_bedrock_audit

logger = logging.getLogger(__name__)


def default_audit_heuristic(enriched_bill: EnrichedBill) -> Dict[str, Any]:
    """
    Deterministic audit evaluation used as fallback or fast verification:
    Detects unbundling or high price disparity ratios.
    """
    disputed_codes = []
    reasoning_points = []

    # Check unbundling & high markup
    unbundled_groups = {}
    for item in enriched_bill.line_items:
        if item.unbundling_group:
            unbundled_groups.setdefault(item.unbundling_group, []).append(item)

        # Flag excessive markup vs Medicare baseline (> 2.5x)
        if item.price_disparity_ratio and item.price_disparity_ratio > 2.5:
            issue_type = "UPCODING" if item.cpt_code in ["99205", "99215"] else "PRICE_DISPARITY"
            disputed_codes.append({
                "cpt_code": item.cpt_code,
                "billed_description": item.description,
                "standard_description": item.standard_description or item.description,
                "billed_amount": item.billed_amount,
                "medicare_baseline": item.medicare_national_rate or 0.0,
                "issue": issue_type,
            })
            reasoning_points.append(
                f"CPT code {item.cpt_code} was billed at ${item.billed_amount:.2f}, representing a {item.price_disparity_ratio:.1f}x markup "
                f"over the standard Medicare baseline fee (${item.medicare_national_rate:.2f})."
            )

    # Check unbundled panel groups
    for group, items in unbundled_groups.items():
        if len(items) > 1:
            total_unbundled_cost = sum(i.billed_amount for i in items)
            codes_str = ", ".join(i.cpt_code for i in items)
            disputed_codes.append({
                "cpt_code": items[0].cpt_code,
                "billed_description": f"Unbundled {group} items: {codes_str}",
                "standard_description": f"Comprehensive {group} panel",
                "billed_amount": total_unbundled_cost,
                "medicare_baseline": 14.53,  # Baseline bundled CMP rate
                "issue": "UNBUNDLING",
            })
            reasoning_points.append(
                f"Procedures ({codes_str}) belong to common panel {group} and appear unbundled instead of comprehensive billing."
            )

    if disputed_codes:
        markdown_letter = f"""# FORMAL MEDICAL BILLING DISPUTE & AUDIT NOTICE

**To:** {enriched_bill.provider.name or 'Billing Department'}
**From:** {enriched_bill.patient.name or 'Patient'} (Policy ID: {enriched_bill.patient.policy_id or 'N/A'})
**Statement Date:** {enriched_bill.statement_date or 'N/A'}
**Total Disputed Charges:** ${sum(d['billed_amount'] for d in disputed_codes):.2f}

---

### Notice of Disputed Line Items
The following billed line items have been identified with compliance discrepancies:

| CPT Code | Description | Billed Amount | Medicare Baseline | Issue |
|---|---|---|---|---|
"""
        for d in disputed_codes:
            markdown_letter += f"| {d['cpt_code']} | {d['billed_description']} | ${d['billed_amount']:.2f} | ${d['medicare_baseline']:.2f} | {d['issue']} |\n"

        markdown_letter += f"""
### Auditor Reasoning & Grounds for Appeal
{' '.join(reasoning_points)}

Pursuant to the No Surprises Act and standard AMA CPT billing guidelines, we formally request an itemized review and re-adjudication of these charges.
"""
        return {
            "status": "disputed",
            "disputed_codes": disputed_codes,
            "reasoning": " ".join(reasoning_points),
            "dispute_letter_markdown": markdown_letter,
        }

    return {"status": "cleared"}


async def process_document_pipeline(
    document_id: str,
    mock_textract_json: Optional[Dict[str, Any]] = None,
    custom_agent_fn: Optional[Any] = None,
    session: Optional[AsyncSession] = None,
):
    """
    Executes the complete document processing pipeline:
    1. Sets document status to SCANNING.
    2. Runs Textract OCR (or uses provided raw JSON).
    3. Structures raw blocks into StructuredBill.
    4. Enriches StructuredBill with CMS CPT data.
    5. Dispatches to Agent auditor.
    6. Persists Dispute or marks Cleared.
    """
    if session is not None:
        await _execute_pipeline(document_id, session, mock_textract_json, custom_agent_fn)
    else:
        async with async_session_factory() as new_session:
            await _execute_pipeline(document_id, new_session, mock_textract_json, custom_agent_fn)


async def _execute_pipeline(
    document_id: str,
    session: AsyncSession,
    mock_textract_json: Optional[Dict[str, Any]] = None,
    custom_agent_fn: Optional[Any] = None,
):
    doc = await session.get(Document, document_id)
    if not doc:
        logger.error(f"Document {document_id} not found")
        return

    try:
        # 1. Update status to SCANNING
        doc.status = DocumentStatus.SCANNING
        await session.commit()

        # 2. Textract OCR
        if mock_textract_json:
            raw_textract = mock_textract_json
        else:
            job_id = await textract_service.start_document_analysis(doc.s3_key)
            doc.textract_job_id = job_id
            await session.commit()
            raw_textract = await textract_service.get_document_analysis(job_id)

        doc.raw_textract_json = raw_textract

        # 3. Structuring
        structured = structure_bill(raw_textract)
        doc.structured_data = structured.model_dump()

        # 4. Enrichment
        enriched = await enrich_bill(
            structured_bill=structured,
            document_id=doc.id,
            session=session,
        )

        # 5. Agent Audit Execution
        if custom_agent_fn:
            decision = await custom_agent_fn(enriched.model_dump())
        else:
            try:
                decision = await run_bedrock_audit(enriched.model_dump())
            except Exception as e:
                logger.error(f"Bedrock audit failed, falling back to heuristic: {e}")
                decision = default_audit_heuristic(enriched)

        # 6. Adjudicate Result
        if decision.get("status") == "disputed":
            dispute = Dispute(
                document_id=doc.id,
                patient_info=enriched.patient.model_dump(),
                provider_info=enriched.provider.model_dump(),
                disputed_codes=decision.get("disputed_codes", []),
                agent_reasoning=decision.get("reasoning", ""),
                dispute_letter_markdown=decision.get("dispute_letter_markdown", ""),
                status=DisputeStatus.PENDING_REVIEW,
            )
            session.add(dispute)
            doc.status = DocumentStatus.DISPUTED
        else:
            doc.status = DocumentStatus.CLEARED

        await session.commit()
        logger.info(f"Document {document_id} successfully processed with status {doc.status}")

    except Exception as e:
        logger.exception(f"Pipeline error for document {document_id}: {str(e)}")
        doc.status = DocumentStatus.ERROR
        doc.error_message = str(e)
        await session.commit()
