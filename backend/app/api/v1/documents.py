from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.api.deps import get_current_user
from backend.app.db.models.document import Document
from backend.app.db.models.user import User
from backend.app.db.session import get_db
from backend.app.schemas.document import DocumentResponse, DocumentDetailResponse, DisputedCodeItem

router = APIRouter(tags=["Documents"])


@router.get("/documents", response_model=List[DocumentResponse])
async def list_documents(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Lists all medical bills uploaded by the current authenticated user."""
    stmt = (
        select(Document)
        .where(Document.user_id == current_user.id)
        .order_by(Document.created_at.desc())
    )
    result = await session.execute(stmt)
    documents = result.scalars().all()
    return documents


@router.get("/documents/{document_id}", response_model=DocumentDetailResponse)
async def get_document_detail(
    document_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Retrieves full details of a specific document, including any generated dispute audit."""
    stmt = (
        select(Document)
        .options(selectinload(Document.dispute))
        .where(Document.id == document_id, Document.user_id == current_user.id)
    )
    result = await session.execute(stmt)
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    response_data = {
        "id": doc.id,
        "filename": doc.filename,
        "status": doc.status,
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
        "patient_info": None,
        "provider_info": None,
        "disputed_codes": None,
        "agent_reasoning": None,
        "dispute_letter_markdown": None,
    }

    if doc.dispute:
        dispute = doc.dispute
        response_data.update({
            "patient_info": dispute.patient_info,
            "provider_info": dispute.provider_info,
            "disputed_codes": dispute.disputed_codes,
            "agent_reasoning": dispute.agent_reasoning,
            "dispute_letter_markdown": dispute.dispute_letter_markdown,
        })

    return response_data


@router.post("/documents/{document_id}/process", status_code=status.HTTP_202_ACCEPTED)
async def trigger_document_process(
    document_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Triggers the autonomous OCR, structuring, enrichment, and LLM auditing pipeline.
    Invoked upon S3 upload completion or via webhook.
    """
    stmt = select(Document).where(Document.id == document_id, Document.user_id == current_user.id)
    result = await session.execute(stmt)
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    # Launch background processing pipeline
    from backend.app.services.agent_dispatcher import process_document_pipeline
    import asyncio

    # Spawn async background task
    asyncio.create_task(process_document_pipeline(document_id=doc.id))

    return {
        "message": "Document processing pipeline triggered",
        "document_id": doc.id,
        "status": "PROCESSING_QUEUED",
    }

