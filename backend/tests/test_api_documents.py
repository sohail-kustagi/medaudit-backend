import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.db.models.document import Document, DocumentStatus
from backend.app.db.models.dispute import Dispute, DisputeStatus
from backend.app.db.models.user import User


@pytest.mark.asyncio
async def test_list_and_get_document_details(client: AsyncClient, db_session: AsyncSession):
    headers_user_a = {"Authorization": "Bearer mock-user-a"}
    headers_user_b = {"Authorization": "Bearer mock-user-b"}

    # Presign upload for User A
    res_a = await client.post(
        "/api/v1/presign",
        json={"filename": "bill_user_a.pdf"},
        headers=headers_user_a,
    )
    doc_id_a = res_a.json()["document_id"]

    # Presign upload for User B
    res_b = await client.post(
        "/api/v1/presign",
        json={"filename": "bill_user_b.pdf"},
        headers=headers_user_b,
    )
    doc_id_b = res_b.json()["document_id"]

    # List documents for User A
    list_a = await client.get("/api/v1/documents", headers=headers_user_a)
    assert list_a.status_code == 200
    docs_a = list_a.json()
    assert len(docs_a) == 1
    assert docs_a[0]["id"] == doc_id_a

    # User B should not see User A's document
    detail_forbidden = await client.get(f"/api/v1/documents/{doc_id_a}", headers=headers_user_b)
    assert detail_forbidden.status_code == 404


@pytest.mark.asyncio
async def test_dispute_approval_and_dismissal_workflow(client: AsyncClient, db_session: AsyncSession):
    headers = {"Authorization": "Bearer mock-user-dispute"}
    res = await client.post(
        "/api/v1/presign",
        json={"filename": "bill_with_error.pdf"},
        headers=headers,
    )
    doc_id = res.json()["document_id"]

    # Manually attach a Dispute to simulate completed agent execution
    doc = await db_session.get(Document, doc_id)
    doc.status = DocumentStatus.DISPUTED
    
    dispute = Dispute(
        document_id=doc_id,
        patient_info={"name": "Jane Doe", "policy_id": "POL-999"},
        provider_info={"name": "Metro General Hospital"},
        disputed_codes=[{
            "cpt_code": "99215",
            "billed_description": "Office visit high complexity",
            "standard_description": "Level 5 visit",
            "billed_amount": 450.0,
            "medicare_baseline": 183.15,
            "issue": "UPCODING"
        }],
        agent_reasoning="Clinical notes support simple follow-up, code 99215 is unbundled/upcoded.",
        dispute_letter_markdown="# Medical Billing Appeal\n...",
        status=DisputeStatus.PENDING_REVIEW,
    )
    db_session.add(dispute)
    await db_session.commit()
    await db_session.refresh(dispute)

    # Fetch document detail
    detail_res = await client.get(f"/api/v1/documents/{doc_id}", headers=headers)
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["status"] == "DISPUTED"
    assert detail["patient_info"]["name"] == "Jane Doe"
    assert len(detail["disputed_codes"]) == 1
    assert detail["disputed_codes"][0]["cpt_code"] == "99215"

    # Approve dispute
    approve_res = await client.post(f"/api/v1/disputes/{dispute.id}/approve", headers=headers)
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "APPROVED"

    # Cannot approve after dismissal test on another dispute
    # Test dismissal
    dismiss_doc = await client.post(
        "/api/v1/presign",
        json={"filename": "bill_dismiss.pdf"},
        headers=headers,
    )
    dismiss_doc_id = dismiss_doc.json()["document_id"]
    dismiss_dispute = Dispute(
        document_id=dismiss_doc_id,
        patient_info={},
        provider_info={},
        disputed_codes=[],
        agent_reasoning="test",
        dispute_letter_markdown="test",
    )
    db_session.add(dismiss_dispute)
    await db_session.commit()
    await db_session.refresh(dismiss_dispute)

    dismiss_res = await client.post(f"/api/v1/disputes/{dismiss_dispute.id}/dismiss", headers=headers)
    assert dismiss_res.status_code == 200
    assert dismiss_res.json()["status"] == "DISMISSED"

    # Attempting to approve dismissed dispute returns 400
    invalid_approve = await client.post(f"/api/v1/disputes/{dismiss_dispute.id}/approve", headers=headers)
    assert invalid_approve.status_code == 400
