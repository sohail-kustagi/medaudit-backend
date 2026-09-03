import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.seeds.seed_cpt_codes import seed_cpt_codes, seed_default_policy_rules
from backend.app.pipelines.enrichment import enrich_bill
from backend.app.schemas.bill import (
    BillingLineItem,
    PatientInfo,
    ProviderInfo,
    StructuredBill,
)


@pytest.mark.asyncio
async def test_bill_enrichment_with_cpt_and_policy(db_session: AsyncSession):
    # Seed baseline CMS reference data
    await seed_cpt_codes(db_session)
    await seed_default_policy_rules(db_session)
    await db_session.commit()

    structured = StructuredBill(
        patient=PatientInfo(name="Alice Smith", policy_id="AET-12345"),
        provider=ProviderInfo(name="Downtown Health Clinic", npi="1234567890"),
        statement_date="2024-11-01",
        total_billed=835.0,
        line_items=[
            BillingLineItem(
                line_number=1,
                cpt_code="99215",
                description="Office visit level 5",
                units=1,
                billed_amount=485.00,
            ),
            BillingLineItem(
                line_number=2,
                cpt_code="84132",
                description="Potassium Serum",
                units=1,
                billed_amount=50.00,
            ),
            BillingLineItem(
                line_number=3,
                cpt_code="99999",  # Non-existent code
                description="Custom experimental test",
                units=1,
                billed_amount=300.00,
            ),
        ],
    )

    enriched = await enrich_bill(
        structured_bill=structured,
        document_id="doc-test-123",
        session=db_session,
        insurance_plan_id="AETNA_CHOICE_POS",
    )

    assert enriched.document_id == "doc-test-123"
    assert len(enriched.line_items) == 3

    # Check Item 1: CPT 99215
    item_1 = enriched.line_items[0]
    assert item_1.cpt_code == "99215"
    assert item_1.medicare_national_rate is not None
    assert item_1.medicare_national_rate > 150.0
    assert item_1.price_disparity_ratio is not None
    assert item_1.price_disparity_ratio > 2.0  # 485 / 183.15 is ~2.65
    assert "Office or other outpatient visit" in item_1.standard_description
    assert item_1.is_covered is True
    assert item_1.coinsurance_rate == 0.20

    # Check Item 2: CPT 84132 (Unbundling candidate)
    item_2 = enriched.line_items[1]
    assert item_2.cpt_code == "84132"
    assert item_2.unbundling_group == "CMP_PANEL"
    assert item_2.medicare_national_rate == 5.15
    assert item_2.price_disparity_ratio == 9.71  # 50 / 5.15

    # Check Item 3: Unknown CPT 99999
    item_3 = enriched.line_items[2]
    assert item_3.cpt_code == "99999"
    assert item_3.medicare_national_rate is None
    assert item_3.price_disparity_ratio is None
    assert "Unlisted" in item_3.standard_description
