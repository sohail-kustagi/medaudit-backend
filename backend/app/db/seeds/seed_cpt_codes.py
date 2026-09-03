import asyncio
import csv
import os
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.db.session import async_session_factory, engine
from backend.app.db.base import Base
from backend.app.db.models.cpt_code import CptCode
from backend.app.db.models.policy_rule import PolicyRule

CSV_PATH = Path(__file__).parent / "cms_pfs_sample.csv"


async def seed_cpt_codes(session: AsyncSession) -> int:
    """Reads CMS PFS CSV and populates cpt_codes table."""
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"CMS PFS CSV file not found at {CSV_PATH}")

    count = 0
    with open(CSV_PATH, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row["code"].strip()
            existing = await session.get(CptCode, code)
            if not existing:
                cpt_entry = CptCode(
                    code=code,
                    short_description=row["short_description"].strip(),
                    long_description=row["long_description"].strip(),
                    category=row["category"].strip() if row["category"] else None,
                    medicare_national_rate=float(row["medicare_national_rate"]),
                    unbundling_group=row["unbundling_group"].strip() if row.get("unbundling_group") else None,
                )
                session.add(cpt_entry)
                count += 1
            else:
                # Update baseline rates
                existing.medicare_national_rate = float(row["medicare_national_rate"])
                existing.short_description = row["short_description"].strip()
                existing.long_description = row["long_description"].strip()
                existing.category = row["category"].strip() if row["category"] else None
                existing.unbundling_group = row["unbundling_group"].strip() if row.get("unbundling_group") else None

    await session.flush()
    return count


async def seed_default_policy_rules(session: AsyncSession) -> int:
    """Seeds baseline insurance plan policy rules for common test scenarios."""
    plans = ["AETNA_CHOICE_POS", "BCBS_STANDARD", "UNITED_HEALTH_GOLD", "CIGNA_OPEN_ACCESS"]
    
    # Representative sample of rules
    rules_to_seed = [
        # (plan_id, cpt_code, is_covered, requires_preauth, coinsurance_rate, notes)
        ("AETNA_CHOICE_POS", "99213", True, False, 0.20, "Standard office visit copay applied"),
        ("AETNA_CHOICE_POS", "99215", True, False, 0.20, "Requires clinical documentation of high complexity"),
        ("AETNA_CHOICE_POS", "70450", True, True, 0.30, "CT Scan requires prior authorization unless emergency"),
        ("AETNA_CHOICE_POS", "80053", True, False, 0.10, "Preventive lab covered at 90%"),
        ("BCBS_STANDARD", "99213", True, False, 0.15, "Standard in-network rate"),
        ("BCBS_STANDARD", "99215", True, False, 0.20, "Level 5 visit subject to post-service audit"),
        ("BCBS_STANDARD", "80053", True, False, 0.00, "100% covered under annual preventive health"),
        ("BCBS_STANDARD", "93000", True, False, 0.20, "Routine ECG in-office covered"),
    ]

    count = 0
    for plan_id, cpt_code, is_covered, requires_preauth, coinsurance, notes in rules_to_seed:
        # Check if CPT exists
        cpt = await session.get(CptCode, cpt_code)
        if not cpt:
            continue

        stmt = select(PolicyRule).where(
            PolicyRule.plan_id == plan_id,
            PolicyRule.cpt_code == cpt_code
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if not existing:
            rule = PolicyRule(
                plan_id=plan_id,
                cpt_code=cpt_code,
                is_covered=is_covered,
                requires_preauth=requires_preauth,
                coinsurance_rate=coinsurance,
                policy_notes=notes
            )
            session.add(rule)
            count += 1

    await session.flush()
    return count


async def seed_all():
    """Initializes schema and runs all seeds."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        cpt_count = await seed_cpt_codes(session)
        rule_count = await seed_default_policy_rules(session)
        await session.commit()
        print(f"Seeded {cpt_count} CPT codes and {rule_count} policy rules successfully.")


if __name__ == "__main__":
    asyncio.run(seed_all())
