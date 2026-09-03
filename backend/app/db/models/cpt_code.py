from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Float, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.db.base import Base, utc_now


class CptCode(Base):
    __tablename__ = "cpt_codes"

    code: Mapped[str] = mapped_column(String(10), primary_key=True, index=True)
    short_description: Mapped[str] = mapped_column(String(255), nullable=False)
    long_description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    medicare_national_rate: Mapped[float] = mapped_column(Float, nullable=False)
    unbundling_group: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
