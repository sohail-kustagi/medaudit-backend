import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_current_user
from backend.app.db.models.document import Document, DocumentStatus
from backend.app.db.models.user import User
from backend.app.db.session import get_db
from backend.app.schemas.presign import PresignRequest, PresignResponse
from backend.app.services.s3_service import s3_service

router = APIRouter(tags=["Ingestion"])


@router.post("/presign", response_model=PresignResponse, status_code=status.HTTP_201_CREATED)
async def create_presigned_upload(
    payload: PresignRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Generates a secure AWS S3 presigned POST URL for direct client-side upload.
    Initializes a Document record in PENDING status.
    """
    if not payload.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF documents are supported (.pdf)",
        )

    document_id = str(uuid.uuid4())
    presign_data = s3_service.generate_presigned_post(
        user_id=current_user.id,
        document_id=document_id,
        filename=payload.filename,
        content_type=payload.content_type,
    )

    # Persist pending document record
    doc = Document(
        id=document_id,
        user_id=current_user.id,
        filename=payload.filename,
        s3_key=presign_data["s3_key"],
        status=DocumentStatus.PENDING,
    )
    session.add(doc)
    await session.commit()

    return PresignResponse(
        upload_url=presign_data["upload_url"],
        document_id=document_id,
        fields=presign_data["fields"],
    )
