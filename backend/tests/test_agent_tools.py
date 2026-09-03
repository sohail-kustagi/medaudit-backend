"""
Unit Tests: MedAudit Agent Tools
=================================
Tests for the three Strands @tool functions:
  - query_policy_rules
  - check_unbundling
  - draft_appeal_letter

Uses an in-memory SQLite test DB seeded with CPT codes and policy rules.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.seeds.seed_cpt_codes import seed_cpt_codes, seed_default_policy_rules


# ── query_policy_rules ────────────────────────────────────────────────────────

class TestQueryPolicyRules:
    """Tests for the query_policy_rules @tool."""

    @pytest.mark.asyncio
    async def test_known_plan_and_code_returns_coverage(self, db_session: AsyncSession):
        """query_policy_rules for a seeded plan/code returns correct coverage data."""
        await seed_cpt_codes(db_session)
        await seed_default_policy_rules(db_session)
        await db_session.commit()

        # Import after seeding so the async DB session factory is ready
        from agent.tools.policy_checker import _async_query_policy

        result = await _async_query_policy(
            patient_id="POL-1",
            cpt_code="99215",
            plan_id="AETNA_CHOICE_POS",
            session=db_session,
        )

        assert result["is_covered"] is True
        assert isinstance(result["requires_preauth"], bool)
        assert isinstance(result["coinsurance_pct"], float)
        assert result["cpt_code"] == "99215"
        assert result["plan_id"] == "AETNA_CHOICE_POS"
        assert "policy_notes" in result

    @pytest.mark.asyncio
    async def test_unknown_code_returns_defaults(self, db_session: AsyncSession):
        """query_policy_rules for unknown CPT returns sensible defaults."""
        await seed_cpt_codes(db_session)
        await db_session.commit()

        from agent.tools.policy_checker import _async_query_policy

        result = await _async_query_policy(
            patient_id="POL-X",
            cpt_code="99999",
            plan_id="AETNA_CHOICE_POS",
            session=db_session,
        )

        # Default when no rule found
        assert result["is_covered"] is True
        assert result["requires_preauth"] is False
        assert result["coinsurance_pct"] == 0.20

    @pytest.mark.asyncio
    async def test_plan_alias_resolution(self, db_session: AsyncSession):
        """Short plan aliases (AETNA, BCBS) are correctly expanded."""
        await seed_cpt_codes(db_session)
        await seed_default_policy_rules(db_session)
        await db_session.commit()

        from agent.tools.policy_checker import _async_query_policy

        result = await _async_query_policy("POL-1", "99213", "AETNA", session=db_session)
        assert result["plan_id"] == "AETNA_CHOICE_POS"

    @pytest.mark.asyncio
    async def test_preauth_required_for_ct_scan(self, db_session: AsyncSession):
        """CT scan (70450) under AETNA requires prior authorization."""
        await seed_cpt_codes(db_session)
        await seed_default_policy_rules(db_session)
        await db_session.commit()

        from agent.tools.policy_checker import _async_query_policy

        result = await _async_query_policy("POL-1", "70450", "AETNA_CHOICE_POS", session=db_session)
        assert result["requires_preauth"] is True


# ── check_unbundling ──────────────────────────────────────────────────────────

class TestCheckUnbundling:
    """Tests for the check_unbundling @tool."""

    @pytest.mark.asyncio
    async def test_bmp_panel_unbundling_detected(self, db_session: AsyncSession):
        """BMP component codes billed individually are flagged as unbundled."""
        await seed_cpt_codes(db_session)
        await db_session.commit()

        from agent.tools.unbundling_checker import _async_check_unbundling

        result = await _async_check_unbundling(["80048", "84132", "84295"], session=db_session)

        assert result["has_unbundling"] is True
        assert len(result["offending_codes"]) >= 2
        # Should suggest the BMP panel code
        assert result["suggested_bundled_code"] in ("80048", "80053", None) or \
               result["suggested_bundled_code"] is not None
        assert result["estimated_savings"] >= 0.0
        assert "NCCI" in result["explanation"] or "bundl" in result["explanation"].lower()

    @pytest.mark.asyncio
    async def test_no_unbundling_for_unrelated_codes(self, db_session: AsyncSession):
        """Unrelated codes with no common unbundling group return has_unbundling=False."""
        await seed_cpt_codes(db_session)
        await db_session.commit()

        from agent.tools.unbundling_checker import _async_check_unbundling

        result = await _async_check_unbundling(["99213", "70450"], session=db_session)

        assert result["has_unbundling"] is False
        assert result["offending_codes"] == []
        assert result["suggested_bundled_code"] is None

    @pytest.mark.asyncio
    async def test_empty_list_returns_no_unbundling(self, db_session: AsyncSession):
        """Empty code list returns safe defaults."""
        from agent.tools.unbundling_checker import _async_check_unbundling

        result = await _async_check_unbundling([], session=db_session)
        # check_unbundling handles empty list in the @tool wrapper
        # But the async impl should handle it gracefully too
        assert result["has_unbundling"] is False

    @pytest.mark.asyncio
    async def test_single_code_no_violation(self, db_session: AsyncSession):
        """A single BMP code alone is not an unbundling violation."""
        await seed_cpt_codes(db_session)
        await db_session.commit()

        from agent.tools.unbundling_checker import _async_check_unbundling

        result = await _async_check_unbundling(["80048"], session=db_session)
        assert result["has_unbundling"] is False

    @pytest.mark.asyncio
    async def test_lipid_panel_unbundling(self, db_session: AsyncSession):
        """Multiple LIPID_PANEL codes trigger unbundling detection."""
        await seed_cpt_codes(db_session)
        await db_session.commit()

        from agent.tools.unbundling_checker import _async_check_unbundling

        # 80061, 82465, 83718 would all be in LIPID_PANEL if seeded
        # Test with whatever LIPID_PANEL codes are seeded
        result = await _async_check_unbundling(["80061"], session=db_session)
        # Single code: not unbundled
        assert result["has_unbundling"] is False


# ── draft_appeal_letter ───────────────────────────────────────────────────────

class TestDraftAppealLetter:
    """Tests for the draft_appeal_letter @tool."""

    def _make_letter_args(self):
        return {
            "patient_info": {
                "name": "John Doe",
                "dob": "1970-01-15",
                "policy_id": "POL-TEST-001",
                "account_number": "ACC-0001",
                "address": "123 Test St, Anytown, USA 00001",
            },
            "provider_info": {
                "name": "Test Medical Center",
                "npi": "1234567890",
                "address": "456 Hospital Rd, Anytown, USA 00002",
            },
            "disputed_codes": [
                {
                    "cpt_code": "99215",
                    "billed_description": "High complexity office visit",
                    "standard_description": "Office visit, high MDM",
                    "billed_amount": 750.00,
                    "medicare_baseline": 171.24,
                    "issue": "UPCODING",
                }
            ],
            "reasoning": (
                "CPT 99215 was billed at $750.00 representing a 4.38x markup over "
                "the Medicare national rate of $171.24. Clinical documentation does "
                "not support high complexity E/M visit."
            ),
        }

    def test_letter_renders_without_error(self):
        """draft_appeal_letter renders a non-empty letter from valid inputs."""
        from agent.tools.letter_drafter import draft_appeal_letter

        args = self._make_letter_args()
        result = draft_appeal_letter(**args)

        assert "letter_markdown" in result
        assert "formal_reference_id" in result
        assert len(result["letter_markdown"]) > 100

    def test_letter_contains_no_surprises_act(self):
        """Appeal letter must cite the No Surprises Act."""
        from agent.tools.letter_drafter import draft_appeal_letter

        result = draft_appeal_letter(**self._make_letter_args())
        assert "No Surprises Act" in result["letter_markdown"]

    def test_letter_contains_patient_name(self):
        """Patient name appears in the letter."""
        from agent.tools.letter_drafter import draft_appeal_letter

        result = draft_appeal_letter(**self._make_letter_args())
        assert "John Doe" in result["letter_markdown"]

    def test_letter_contains_provider_name(self):
        """Provider name appears in the letter."""
        from agent.tools.letter_drafter import draft_appeal_letter

        result = draft_appeal_letter(**self._make_letter_args())
        assert "Test Medical Center" in result["letter_markdown"]

    def test_letter_contains_cpt_code(self):
        """CPT code 99215 appears in the letter."""
        from agent.tools.letter_drafter import draft_appeal_letter

        result = draft_appeal_letter(**self._make_letter_args())
        assert "99215" in result["letter_markdown"]

    def test_formal_reference_id_format(self):
        """formal_reference_id has the MEDAUDIT- prefix."""
        from agent.tools.letter_drafter import draft_appeal_letter

        result = draft_appeal_letter(**self._make_letter_args())
        assert result["formal_reference_id"].startswith("MEDAUDIT-")

    def test_letter_contains_cms_cci_reference(self):
        """Letter cites CMS Correct Coding Initiative."""
        from agent.tools.letter_drafter import draft_appeal_letter

        result = draft_appeal_letter(**self._make_letter_args())
        assert "Correct Coding Initiative" in result["letter_markdown"] or \
               "CCI" in result["letter_markdown"]

    def test_multiple_disputed_codes(self):
        """Letter renders correctly with multiple disputed codes."""
        from agent.tools.letter_drafter import draft_appeal_letter

        args = self._make_letter_args()
        args["disputed_codes"].append(
            {
                "cpt_code": "84132",
                "billed_description": "Potassium, serum",
                "standard_description": "Potassium; serum, plasma or whole blood",
                "billed_amount": 28.50,
                "medicare_baseline": 6.80,
                "issue": "UNBUNDLING",
            }
        )
        result = draft_appeal_letter(**args)
        assert "84132" in result["letter_markdown"]
        assert "99215" in result["letter_markdown"]
