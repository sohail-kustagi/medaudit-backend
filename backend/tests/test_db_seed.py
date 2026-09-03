import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.db.models.cpt_code import CptCode
from backend.app.db.models.policy_rule import PolicyRule
from backend.app.db.seeds.seed_cpt_codes import seed_cpt_codes, seed_default_policy_rules


@pytest.mark.asyncio
async def test_cpt_seeding_and_integrity(db_session: AsyncSession):
    # Execute seeding
    count = await seed_cpt_codes(db_session)
    await db_session.commit()

    # Validation criteria 1: >= 50 CPT codes seeded
    assert count >= 50, f"Expected at least 50 CPT codes seeded, got {count}"

    # Validation criteria 2: Total count in DB matches
    result = await db_session.execute(select(func.count(CptCode.code)))
    total_in_db = result.scalar()
    assert total_in_db >= 50

    # Validation criteria 3: Verify specific critical CPT codes
    # Check E/M Level 5
    cpt_99215 = await db_session.get(CptCode, "99215")
    assert cpt_99215 is not None
    assert "Office o/p est hi" in cpt_99215.short_description
    assert cpt_99215.medicare_national_rate > 150.0  # Approx $183.15

    # Check unbundling group (CMP panel)
    cpt_80053 = await db_session.get(CptCode, "80053")
    assert cpt_80053 is not None
    assert cpt_80053.unbundling_group == "CMP_PANEL"
    assert cpt_80053.medicare_national_rate > 10.0

    # Check unbundled electrolyte component
    cpt_84132 = await db_session.get(CptCode, "84132")
    assert cpt_84132 is not None
    assert cpt_84132.unbundling_group == "CMP_PANEL"


@pytest.mark.asyncio
async def test_policy_rules_seeding(db_session: AsyncSession):
    # Seed CPT first
    await seed_cpt_codes(db_session)
    
    # Seed policy rules
    rule_count = await seed_default_policy_rules(db_session)
    await db_session.commit()

    assert rule_count > 0

    # Verify lookup for AETNA plan on 99215
    stmt = select(PolicyRule).where(
        PolicyRule.plan_id == "AETNA_CHOICE_POS",
        PolicyRule.cpt_code == "99215"
    )
    res = await db_session.execute(stmt)
    rule = res.scalar_one_or_none()
    assert rule is not None
    assert rule.is_covered is True
    assert rule.coinsurance_rate == 0.20
