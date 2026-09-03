import enum
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from sqlalchemy import String, Text, DateTime, ForeignKey, Enum, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.db.base import Base, utc_now

if TYPE_CHECKING:
    from backend.app.db.models.document import Document


class DisputeStatus(str, enum.Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    DISMISSED = "DISMISSED"


class Dispute(Base):
    __tablename__ = "disputes"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    patient_info: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    provider_info: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    disputed_codes: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    agent_reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    dispute_letter_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[DisputeStatus] = mapped_column(
        Enum(DisputeStatus, native_enum=False), default=DisputeStatus.PENDING_REVIEW, index=True, nullable=False
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    # Relationships
    document: Mapped["Document"] = relationship("Document", back_populates="dispute")
