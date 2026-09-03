import json
from pathlib import Path
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.document import Document, DocumentStatus
from backend.app.db.models.dispute import Dispute, DisputeStatus
from backend.app.db.seeds.seed_cpt_codes import seed_cpt_codes, seed_default_policy_rules
from backend.app.services.agent_dispatcher import process_document_pipeline

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "mock_textract_response.json"


@pytest.mark.asyncio
async def test_end_to_end_dispute_pipeline(client: AsyncClient, db_session: AsyncSession):
    # 1. Seed CPT fee schedule & policies
    await seed_cpt_codes(db_session)
    await seed_default_policy_rules(db_session)
    await db_session.commit()

    headers = {"Authorization": "Bearer e2e-user"}

    # 2. Client calls /presign to initiate document upload
    presign_res = await client.post(
        "/api/v1/presign",
        json={"filename": "metro_urgent_care_bill.pdf"},
        headers=headers,
    )
    assert presign_res.status_code == 201
    doc_id = presign_res.json()["document_id"]

    # 3. Simulate S3 upload and trigger processing pipeline
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        mock_ocr = json.load(f)

    await process_document_pipeline(document_id=doc_id, mock_textract_json=mock_ocr, session=db_session)

    # 4. Refresh and verify document state
    doc = await db_session.get(Document, doc_id)
    assert doc is not None
    assert doc.status == DocumentStatus.DISPUTED
    assert doc.structured_data is not None
    assert doc.raw_textract_json is not None

    # 5. Verify Dispute record
    stmt = select(Dispute).where(Dispute.document_id == doc_id)
    res = await db_session.execute(stmt)
    dispute = res.scalar_one_or_none()
    assert dispute is not None
    assert dispute.status == DisputeStatus.PENDING_REVIEW
    assert dispute.patient_info["name"] == "John Doe"
    assert "Metro Urgent Care" in dispute.provider_info["name"]
    assert len(dispute.disputed_codes) > 0
    assert "No Surprises Act" in dispute.dispute_letter_markdown

    # 6. Verify via API endpoint /documents/{id}
    api_detail = await client.get(f"/api/v1/documents/{doc_id}", headers=headers)
    assert api_detail.status_code == 200
    data = api_detail.json()
    assert data["status"] == "DISPUTED"
    assert data["patient_info"]["name"] == "John Doe"
    assert len(data["disputed_codes"]) > 0

    # 7. User clicks 'Approve & Send' in Action Modal
    approve_res = await client.post(f"/api/v1/disputes/{dispute.id}/approve", headers=headers)
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "APPROVED"

    # Verify DB reflects approved
    await db_session.refresh(dispute)
    assert dispute.status == DisputeStatus.APPROVED
    assert dispute.approved_at is not None


@pytest.mark.asyncio
async def test_end_to_end_cleared_bill_pipeline(client: AsyncClient, db_session: AsyncSession):
    # Seed CPT codes
    await seed_cpt_codes(db_session)
    await db_session.commit()

    headers = {"Authorization": "Bearer e2e-clean-user"}

    # Presign upload
    presign_res = await client.post(
        "/api/v1/presign",
        json={"filename": "clean_bill.pdf"},
        headers=headers,
    )
    doc_id = presign_res.json()["document_id"]

    # Mock clean OCR: routine E/M code 99213 at standard $92.00
    clean_ocr = {
        "JobStatus": "SUCCEEDED",
        "Blocks": [
            {
                "Id": "k-pat", "BlockType": "KEY_VALUE_SET", "EntityTypes": ["KEY"],
                "Relationships": [{"Type": "CHILD", "Ids": ["w-k"]}, {"Type": "VALUE", "Ids": ["v-pat"]}]
            },
            {"Id": "w-k", "BlockType": "WORD", "Text": "Patient Name:"},
            {
                "Id": "v-pat", "BlockType": "KEY_VALUE_SET", "EntityTypes": ["VALUE"],
                "Relationships": [{"Type": "CHILD", "Ids": ["w-v"]}]
            },
            {"Id": "w-v", "BlockType": "WORD", "Text": "Bob Jones"},
            {
                "Id": "tbl", "BlockType": "TABLE",
                "Relationships": [{"Type": "CHILD", "Ids": ["c1", "c2", "c3", "c4"]}]
            },
            {"Id": "c1", "BlockType": "CELL", "RowIndex": 1, "ColumnIndex": 1, "Relationships": [{"Type": "CHILD", "Ids": ["w1"]}]},
            {"Id": "w1", "BlockType": "WORD", "Text": "Code"},
            {"Id": "c2", "BlockType": "CELL", "RowIndex": 1, "ColumnIndex": 2, "Relationships": [{"Type": "CHILD", "Ids": ["w2"]}]},
            {"Id": "w2", "BlockType": "WORD", "Text": "Charge"},
            {"Id": "c3", "BlockType": "CELL", "RowIndex": 2, "ColumnIndex": 1, "Relationships": [{"Type": "CHILD", "Ids": ["w3"]}]},
            {"Id": "w3", "BlockType": "WORD", "Text": "99213"},
            {"Id": "c4", "BlockType": "CELL", "RowIndex": 2, "ColumnIndex": 2, "Relationships": [{"Type": "CHILD", "Ids": ["w4"]}]},
            {"Id": "w4", "BlockType": "WORD", "Text": "$95.00"}
        ]
    }

    await process_document_pipeline(document_id=doc_id, mock_textract_json=clean_ocr, session=db_session)

    doc = await db_session.get(Document, doc_id)
    assert doc is not None
    # No upcoding or unbundling, within normal fee tolerance -> CLEARED
    assert doc.status == DocumentStatus.CLEARED

    # Verify no dispute was created
    stmt = select(Dispute).where(Dispute.document_id == doc_id)
    res = await db_session.execute(stmt)
    assert res.scalar_one_or_none() is None
