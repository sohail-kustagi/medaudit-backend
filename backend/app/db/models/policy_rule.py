from typing import Optional
from sqlalchemy import String, Text, Boolean, Float, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.db.base import Base


class PolicyRule(Base):
    __tablename__ = "policy_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    cpt_code: Mapped[str] = mapped_column(String(10), ForeignKey("cpt_codes.code", ondelete="CASCADE"), index=True, nullable=False)
    is_covered: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    requires_preauth: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    coinsurance_rate: Mapped[float] = mapped_column(Float, default=0.20, nullable=False)
    policy_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
