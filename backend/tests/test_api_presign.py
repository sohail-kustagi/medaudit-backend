import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.db.models.document import Document, DocumentStatus


@pytest.mark.asyncio
async def test_presign_rejects_non_pdf(client: AsyncClient):
    headers = {"Authorization": "Bearer mock-user-presign-1"}
    response = await client.post(
        "/api/v1/presign",
        json={"filename": "bill_photo.jpg", "content_type": "image/jpeg"},
        headers=headers,
    )
    assert response.status_code == 400
    assert "Only PDF documents are supported" in response.json()["detail"]


@pytest.mark.asyncio
async def test_presign_success_and_db_pending(client: AsyncClient, db_session: AsyncSession):
    headers = {"Authorization": "Bearer mock-user-presign-2"}
    response = await client.post(
        "/api/v1/presign",
        json={"filename": "hospital_bill_nov2024.pdf", "content_type": "application/pdf"},
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert "upload_url" in data
    assert "document_id" in data
    assert "fields" in data
    assert data["fields"]["Content-Type"] == "application/pdf"

    # Verify Document is in DB with status PENDING
    stmt = select(Document).where(Document.id == data["document_id"])
    result = await db_session.execute(stmt)
    doc = result.scalar_one_or_none()
    assert doc is not None
    assert doc.filename == "hospital_bill_nov2024.pdf"
    assert doc.status == DocumentStatus.PENDING
