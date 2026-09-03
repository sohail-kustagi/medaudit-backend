from typing import Dict, Optional
from pydantic import BaseModel, Field


class PresignRequest(BaseModel):
    filename: str = Field(..., description="Original name of the uploaded medical bill PDF")
    content_type: str = Field(default="application/pdf", description="MIME type, must be application/pdf")


class PresignResponse(BaseModel):
    upload_url: str = Field(..., description="S3 direct POST URL")
    document_id: str = Field(..., description="Generated UUID for the document tracking")
    fields: Dict[str, str] = Field(..., description="S3 Presigned POST form fields including signature")
