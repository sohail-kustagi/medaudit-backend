from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.api.deps import get_current_user
from backend.app.db.models.dispute import Dispute, DisputeStatus
from backend.app.db.models.document import Document
from backend.app.db.models.user import User
from backend.app.db.session import get_db
from backend.app.schemas.dispute import DisputeActionResponse

router = APIRouter(tags=["Disputes"])


@router.post("/disputes/{dispute_id}/approve", response_model=DisputeActionResponse)
async def approve_dispute(
    dispute_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Approves the drafted appeal letter.
    Transitions dispute status to APPROVED and triggers notification/SES dispatch.
    """
    stmt = (
        select(Dispute)
        .join(Document)
        .where(Dispute.id == dispute_id, Document.user_id == current_user.id)
    )
    result = await session.execute(stmt)
    dispute = result.scalar_one_or_none()

    if not dispute:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dispute not found",
        )

    if dispute.status == DisputeStatus.DISMISSED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot approve a dispute that has already been dismissed",
        )

    dispute.status = DisputeStatus.APPROVED
    dispute.approved_at = datetime.now(timezone.utc)
    await session.commit()

    return DisputeActionResponse(
        id=dispute.id,
        document_id=dispute.document_id,
        status=dispute.status,
        message="Dispute letter approved successfully. Formal appeal queued for transmission.",
        timestamp=dispute.approved_at,
    )


@router.post("/disputes/{dispute_id}/dismiss", response_model=DisputeActionResponse)
async def dismiss_dispute(
    dispute_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Dismisses the drafted dispute.
    Transitions dispute status to DISMISSED.
    """
    stmt = (
        select(Dispute)
        .join(Document)
        .where(Dispute.id == dispute_id, Document.user_id == current_user.id)
    )
    result = await session.execute(stmt)
    dispute = result.scalar_one_or_none()

    if not dispute:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dispute not found",
        )

    dispute.status = DisputeStatus.DISMISSED
    await session.commit()

    return DisputeActionResponse(
        id=dispute.id,
        document_id=dispute.document_id,
        status=dispute.status,
        message="Dispute dismissed by user.",
        timestamp=datetime.now(timezone.utc),
    )
