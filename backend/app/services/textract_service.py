import asyncio
import os
import json
from typing import Any, Dict, List, Optional
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from backend.app.config import settings


class TextractService:
    def __init__(self):
        self.region = settings.AWS_REGION
        self.bucket = settings.S3_BUCKET_NAME
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = boto3.client(
                "textract",
                region_name=self.region,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID if settings.AWS_ACCESS_KEY_ID != "mock_key" else None,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY if settings.AWS_SECRET_ACCESS_KEY != "mock_secret" else None,
                config=Config(retries={"max_attempts": 5, "mode": "standard"}),
            )
        return self._client

    async def start_document_analysis(self, s3_key: str) -> str:
        """Starts asynchronous Textract document analysis with TABLES and FORMS features."""
        if settings.AWS_ACCESS_KEY_ID == "mock_key" or settings.ALLOW_MOCK_AUTH:
            # Dev / offline mock Job ID
            return f"mock-textract-job-{s3_key.replace('/', '-')}"

        try:
            response = self.client.start_document_analysis(
                DocumentLocation={
                    "S3Object": {
                        "Bucket": self.bucket,
                        "Name": s3_key,
                    }
                },
                FeatureTypes=["TABLES", "FORMS"],
            )
            return response["JobId"]
        except ClientError as e:
            raise RuntimeError(f"Failed to start Amazon Textract job: {str(e)}")

    async def get_document_analysis(self, job_id: str, max_wait_seconds: int = 60) -> Dict[str, Any]:
        """Polls async Textract job until SUCCEEDED or FAILED, collecting all paginated blocks."""
        if job_id.startswith("mock-textract-job"):
            return self._generate_mock_analysis_response()

        elapsed = 0
        poll_interval = 3
        while elapsed < max_wait_seconds:
            try:
                response = self.client.get_document_analysis(JobId=job_id)
                status = response.get("JobStatus")

                if status == "SUCCEEDED":
                    blocks = response.get("Blocks", [])
                    next_token = response.get("NextToken")

                    while next_token:
                        next_res = self.client.get_document_analysis(JobId=job_id, NextToken=next_token)
                        blocks.extend(next_res.get("Blocks", []))
                        next_token = next_res.get("NextToken")

                    return {"JobStatus": "SUCCEEDED", "Blocks": blocks}

                elif status == "FAILED":
                    raise RuntimeError(f"Textract analysis job failed: {response.get('StatusMessage')}")

                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

            except ClientError as e:
                raise RuntimeError(f"Error checking Textract job status: {str(e)}")

        raise TimeoutError(f"Textract job {job_id} timed out after {max_wait_seconds} seconds")

    def _generate_mock_analysis_response(self) -> Dict[str, Any]:
        """Fallback mock Textract blocks response used for local development and smoke tests."""
        return {
            "JobStatus": "SUCCEEDED",
            "Blocks": [
                {
                    "Id": "block-page-1",
                    "BlockType": "PAGE",
                    "Geometry": {},
                }
            ]
        }


textract_service = TextractService()
