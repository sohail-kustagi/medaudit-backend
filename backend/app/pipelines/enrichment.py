from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.cpt_code import CptCode
from backend.app.db.models.policy_rule import PolicyRule
from backend.app.schemas.bill import (
    BillingLineItem,
    EnrichedBill,
    EnrichedLineItem,
    StructuredBill,
)


async def enrich_bill(
    structured_bill: StructuredBill,
    document_id: str,
    session: AsyncSession,
    insurance_plan_id: str = "AETNA_CHOICE_POS",
) -> EnrichedBill:
    """
    Enriches a StructuredBill with official CMS Medicare Physician Fee Schedule (PFS)
    baselines, unbundling groups, price disparity ratios, and insurance policy coverage rules.
    """
    enriched_items = []

    for item in structured_bill.line_items:
        standard_desc: Optional[str] = None
        medicare_rate: Optional[float] = None
        disparity_ratio: Optional[float] = None
        unbundling_group: Optional[str] = None
        is_covered: Optional[bool] = None
        requires_preauth: Optional[bool] = None
        coinsurance_rate: Optional[float] = None
        policy_notes: Optional[str] = None

        if item.cpt_code:
            # 1. Lookup CPT baseline data
            cpt = await session.get(CptCode, item.cpt_code)
            if cpt:
                standard_desc = cpt.long_description
                medicare_rate = cpt.medicare_national_rate
                unbundling_group = cpt.unbundling_group
                if medicare_rate and medicare_rate > 0:
                    disparity_ratio = round(item.billed_amount / medicare_rate, 2)
            else:
                standard_desc = "Unlisted / Non-CMS standard code"

            # 2. Lookup Insurance Policy Rule
            stmt = select(PolicyRule).where(
                PolicyRule.plan_id == insurance_plan_id,
                PolicyRule.cpt_code == item.cpt_code,
            )
            res = await session.execute(stmt)
            rule = res.scalar_one_or_none()
            if rule:
                is_covered = rule.is_covered
                requires_preauth = rule.requires_preauth
                coinsurance_rate = rule.coinsurance_rate
                policy_notes = rule.policy_notes
            else:
                # Default insurance policy assumption
                is_covered = True
                requires_preauth = False
                coinsurance_rate = 0.20

        enriched_item = EnrichedLineItem(
            line_number=item.line_number,
            cpt_code=item.cpt_code,
            description=item.description,
            units=item.units,
            billed_amount=item.billed_amount,
            date_of_service=item.date_of_service,
            raw_text=item.raw_text,
            standard_description=standard_desc,
            medicare_national_rate=medicare_rate,
            price_disparity_ratio=disparity_ratio,
            unbundling_group=unbundling_group,
            is_covered=is_covered,
            requires_preauth=requires_preauth,
            coinsurance_rate=coinsurance_rate,
            policy_notes=policy_notes,
        )
        enriched_items.append(enriched_item)

    return EnrichedBill(
        document_id=document_id,
        patient=structured_bill.patient,
        provider=structured_bill.provider,
        statement_date=structured_bill.statement_date,
        total_billed=structured_bill.total_billed,
        line_items=enriched_items,
        insurance_plan_id=insurance_plan_id,
    )
