"""
Tests: Appeal Letter Rendering Quality & Legal Citations
=========================================================
Validates Jinja2 template rendering quality, structure, and compliance
with all required legal citation standards.
"""

import pytest
from pathlib import Path


TEMPLATE_PATH = (
    Path(__file__).parent.parent.parent / "agent" / "prompts" /
    "templates" / "appeal_letter.md.j2"
)


@pytest.fixture
def standard_letter_args():
    """Standard test fixture for appeal letter generation."""
    return {
        "patient_info": {
            "name": "Jane Smith",
            "dob": "1982-06-14",
            "policy_id": "POL-BCBS-7788",
            "account_number": "ACC-334455",
            "address": "99 Oak Street, Chicago, IL 60601",
        },
        "provider_info": {
            "name": "Chicago Regional Medical Center",
            "npi": "5566778899",
            "address": "1000 Healthcare Blvd, Chicago, IL 60602",
        },
        "disputed_codes": [
            {
                "cpt_code": "99215",
                "billed_description": "Comprehensive office visit, high complexity",
                "standard_description": "Office or other outpatient visit, high MDM",
                "billed_amount": 850.00,
                "medicare_baseline": 171.24,
                "issue": "UPCODING",
            },
            {
                "cpt_code": "84132",
                "billed_description": "Potassium serum",
                "standard_description": "Potassium; serum, plasma or whole blood",
                "billed_amount": 35.00,
                "medicare_baseline": 6.80,
                "issue": "UNBUNDLING",
            },
        ],
        "reasoning": (
            "Two billing issues identified: (1) CPT 99215 billed at $850 represents a "
            "4.96x markup over the Medicare rate of $171.24, which is excessive without "
            "documented clinical complexity justification. (2) CPT 84132 should have "
            "been bundled under the CMP panel code 80053 per NCCI guidelines."
        ),
    }


class TestTemplateExists:
    """Verify template file is present."""

    def test_template_file_exists(self):
        assert TEMPLATE_PATH.exists(), (
            f"Jinja2 template not found at: {TEMPLATE_PATH}"
        )


class TestLetterStructure:
    """Tests for letter markdown structure."""

    def test_renders_without_error(self, standard_letter_args):
        from agent.tools.letter_drafter import draft_appeal_letter
        result = draft_appeal_letter(**standard_letter_args)
        assert result["letter_markdown"]

    def test_has_formal_header(self, standard_letter_args):
        """Letter starts with FORMAL MEDICAL BILLING DISPUTE heading."""
        from agent.tools.letter_drafter import draft_appeal_letter
        result = draft_appeal_letter(**standard_letter_args)
        letter = result["letter_markdown"]
        assert "FORMAL MEDICAL BILLING DISPUTE" in letter or \
               "DISPUTE" in letter.upper()

    def test_contains_reference_id(self, standard_letter_args):
        """Unique MEDAUDIT- reference ID is present in letter."""
        from agent.tools.letter_drafter import draft_appeal_letter
        result = draft_appeal_letter(**standard_letter_args)
        assert "MEDAUDIT-" in result["letter_markdown"]
        assert result["formal_reference_id"] in result["letter_markdown"]

    def test_contains_patient_and_provider_info(self, standard_letter_args):
        """Letter includes both patient and provider information sections."""
        from agent.tools.letter_drafter import draft_appeal_letter
        result = draft_appeal_letter(**standard_letter_args)
        letter = result["letter_markdown"]
        assert "Jane Smith" in letter
        assert "Chicago Regional Medical Center" in letter
        assert "5566778899" in letter  # NPI

    def test_contains_disputed_table(self, standard_letter_args):
        """Letter contains a markdown table of disputed line items."""
        from agent.tools.letter_drafter import draft_appeal_letter
        result = draft_appeal_letter(**standard_letter_args)
        letter = result["letter_markdown"]
        # Markdown table indicators
        assert "|" in letter
        assert "99215" in letter
        assert "84132" in letter

    def test_contains_financial_totals(self, standard_letter_args):
        """Letter shows total disputed charges and baseline amounts."""
        from agent.tools.letter_drafter import draft_appeal_letter
        result = draft_appeal_letter(**standard_letter_args)
        letter = result["letter_markdown"]
        # Total disputed = 850 + 35 = 885.00
        assert "885.00" in letter or "$885" in letter

    def test_contains_reasoning(self, standard_letter_args):
        """Clinical reasoning appears in the letter body."""
        from agent.tools.letter_drafter import draft_appeal_letter
        result = draft_appeal_letter(**standard_letter_args)
        assert "4.96x" in result["letter_markdown"] or "markup" in result["letter_markdown"]


class TestLegalCitations:
    """Tests for required legal citations in the letter."""

    def test_cites_no_surprises_act(self, standard_letter_args):
        """No Surprises Act is cited with section reference."""
        from agent.tools.letter_drafter import draft_appeal_letter
        result = draft_appeal_letter(**standard_letter_args)
        assert "No Surprises Act" in result["letter_markdown"]
        assert "2799A" in result["letter_markdown"] or \
               "PHSA" in result["letter_markdown"] or \
               "Public Health Service Act" in result["letter_markdown"]

    def test_cites_ncci_cci(self, standard_letter_args):
        """CMS National Correct Coding Initiative is cited."""
        from agent.tools.letter_drafter import draft_appeal_letter
        result = draft_appeal_letter(**standard_letter_args)
        letter = result["letter_markdown"]
        assert "Correct Coding Initiative" in letter or "CCI" in letter or "NCCI" in letter

    def test_cites_ama_cpt_guidelines(self, standard_letter_args):
        """AMA CPT Coding Guidelines are cited."""
        from agent.tools.letter_drafter import draft_appeal_letter
        result = draft_appeal_letter(**standard_letter_args)
        letter = result["letter_markdown"]
        assert "AMA" in letter or "American Medical Association" in letter

    def test_cites_false_claims_act(self, standard_letter_args):
        """False Claims Act reference is included."""
        from agent.tools.letter_drafter import draft_appeal_letter
        result = draft_appeal_letter(**standard_letter_args)
        letter = result["letter_markdown"]
        assert "False Claims" in letter

    def test_mentions_cms_enforcement(self, standard_letter_args):
        """Letter references CMS / OIG enforcement options."""
        from agent.tools.letter_drafter import draft_appeal_letter
        result = draft_appeal_letter(**standard_letter_args)
        letter = result["letter_markdown"]
        assert "CMS" in letter or "Centers for Medicare" in letter

    def test_mentions_inspector_general(self, standard_letter_args):
        """Letter mentions OIG complaint pathway."""
        from agent.tools.letter_drafter import draft_appeal_letter
        result = draft_appeal_letter(**standard_letter_args)
        assert "Inspector General" in result["letter_markdown"] or "OIG" in result["letter_markdown"]


class TestLetterEdgeCases:
    """Edge case tests for letter rendering."""

    def test_missing_optional_patient_fields(self):
        """Letter renders cleanly when optional patient fields are absent."""
        from agent.tools.letter_drafter import draft_appeal_letter
        result = draft_appeal_letter(
            patient_info={"name": "Anonymous Patient"},
            provider_info={"name": "Unknown Provider"},
            disputed_codes=[
                {
                    "cpt_code": "99213",
                    "billed_description": "Office visit",
                    "standard_description": "Office visit moderate complexity",
                    "billed_amount": 200.00,
                    "medicare_baseline": 92.14,
                    "issue": "PRICE_DISPARITY",
                }
            ],
            reasoning="Charge is 2.17x Medicare baseline.",
        )
        assert result["letter_markdown"]
        assert "Anonymous Patient" in result["letter_markdown"]

    def test_unique_reference_ids_per_call(self, standard_letter_args):
        """Each call to draft_appeal_letter produces a unique reference ID."""
        from agent.tools.letter_drafter import draft_appeal_letter
        r1 = draft_appeal_letter(**standard_letter_args)
        r2 = draft_appeal_letter(**standard_letter_args)
        assert r1["formal_reference_id"] != r2["formal_reference_id"]
