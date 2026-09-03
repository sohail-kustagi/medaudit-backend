import json
from pathlib import Path
import pytest

from backend.app.pipelines.structuring import structure_bill, parse_money_value

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "mock_textract_response.json"


def test_parse_money_value():
    assert parse_money_value("$485.00") == 485.0
    assert parse_money_value("$1,450.50") == 1450.50
    assert parse_money_value("250") == 250.0
    assert parse_money_value("  $ 99.99 ") == 99.99
    assert parse_money_value("invalid") is None
    assert parse_money_value("") is None


def test_structure_bill_from_textract_blocks():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        raw_textract = json.load(f)

    structured = structure_bill(raw_textract)

    # 1. Patient verification
    assert structured.patient.name == "John Doe"
    assert structured.patient.policy_id == "AET-9920148"

    # 2. Provider verification
    assert "Metro Urgent Care" in structured.provider.name
    assert structured.provider.npi == "1234567890"

    # 3. Financial verification
    assert structured.total_billed == 745.00

    # 4. Line items verification
    assert len(structured.line_items) == 3

    item_1 = structured.line_items[0]
    assert item_1.cpt_code == "99215"
    assert "Office Visit High Complexity" in item_1.description
    assert item_1.billed_amount == 485.00
    assert item_1.units == 1

    item_2 = structured.line_items[1]
    assert item_2.cpt_code == "84132"
    assert "Potassium Serum" in item_2.description
    assert item_2.billed_amount == 80.00

    item_3 = structured.line_items[2]
    assert item_3.cpt_code == "71045"
    assert "Chest X-Ray" in item_3.description
    assert item_3.billed_amount == 180.00
