from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from backend.app.db.models.dispute import DisputeStatus


class DisputeActionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    status: DisputeStatus
    message: str
    timestamp: datetime
