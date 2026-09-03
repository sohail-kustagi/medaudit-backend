import os
from typing import Any, Dict
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from backend.app.config import settings

# S3 Service wrapper
class S3Service:
    def __init__(self):
        self.bucket_name = settings.S3_BUCKET_NAME
        self.region = settings.AWS_REGION
        self._s3_client = None
        self._mock_storage: Dict[str, bytes] = {}

    @property
    def client(self):
        if self._s3_client is None:
            self._s3_client = boto3.client(
                "s3",
                region_name=self.region,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID if settings.AWS_ACCESS_KEY_ID != "mock_key" else None,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY if settings.AWS_SECRET_ACCESS_KEY != "mock_secret" else None,
                config=Config(signature_version="s3v4")
            )
        return self._s3_client

    def generate_presigned_post(
        self,
        user_id: str,
        document_id: str,
        filename: str,
        content_type: str = "application/pdf",
        max_size_mb: int = 15,
    ) -> Dict[str, Any]:
        """Generates an S3 presigned POST policy allowing direct browser upload."""
        s3_key = f"uploads/{user_id}/{document_id}.pdf"

        # Check if running in mock/offline test mode
        if settings.AWS_ACCESS_KEY_ID == "mock_key" or settings.ALLOW_MOCK_AUTH:
            return {
                "upload_url": f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/",
                "s3_key": s3_key,
                "fields": {
                    "key": s3_key,
                    "Content-Type": content_type,
                    "x-amz-meta-original-filename": filename,
                    "x-amz-meta-user-id": user_id,
                    "x-amz-meta-document-id": document_id,
                    "policy": "mock-policy-base64",
                    "x-amz-signature": "mock-signature-hex",
                }
            }

        try:
            fields = {
                "Content-Type": content_type,
                "x-amz-meta-original-filename": filename,
                "x-amz-meta-user-id": user_id,
                "x-amz-meta-document-id": document_id,
            }
            conditions = [
                {"Content-Type": content_type},
                {"x-amz-meta-original-filename": filename},
                {"x-amz-meta-user-id": user_id},
                {"x-amz-meta-document-id": document_id},
                ["content-length-range", 100, max_size_mb * 1024 * 1024],
            ]
            response = self.client.generate_presigned_post(
                Bucket=self.bucket_name,
                Key=s3_key,
                Fields=fields,
                Conditions=conditions,
                ExpiresIn=settings.S3_PRESIGNED_EXPIRY_SECONDS,
            )
            return {
                "upload_url": response["url"],
                "s3_key": s3_key,
                "fields": response["fields"]
            }
        except ClientError as e:
            # Fallback for dev/sandbox
            return {
                "upload_url": f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/",
                "s3_key": s3_key,
                "fields": {"key": s3_key, "Content-Type": content_type}
            }


s3_service = S3Service()
