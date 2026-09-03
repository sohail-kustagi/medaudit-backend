import logging
from typing import Dict, Any, Optional
import boto3
from botocore.exceptions import ClientError
from backend.app.config import settings

logger = logging.getLogger(__name__)


class SESService:
    def __init__(self):
        self.region = settings.AWS_REGION
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = boto3.client(
                "ses",
                region_name=self.region,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID if settings.AWS_ACCESS_KEY_ID != "mock_key" else None,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY if settings.AWS_SECRET_ACCESS_KEY != "mock_secret" else None,
            )
        return self._client

    async def send_dispute_letter_email(
        self,
        to_email: str,
        subject: str,
        letter_markdown: str,
        from_email: str = "appeals@medaudit.app",
    ) -> Dict[str, Any]:
        """Transmits formal dispute appeal via AWS SES or simulated dispatcher."""
        if settings.AWS_ACCESS_KEY_ID == "mock_key" or settings.ALLOW_MOCK_AUTH:
            logger.info(f"[MOCK SES] Sending dispute letter to {to_email} with subject: {subject}")
            return {"MessageId": f"mock-ses-msg-{hash(to_email + subject)}", "status": "sent"}

        try:
            response = self.client.send_email(
                Source=from_email,
                Destination={"ToAddresses": [to_email]},
                Message={
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {
                        "Text": {"Data": letter_markdown, "Charset": "UTF-8"},
                    },
                },
            )
            return {"MessageId": response["MessageId"], "status": "sent"}
        except ClientError as e:
            logger.error(f"Failed to send email via AWS SES: {str(e)}")
            raise RuntimeError(f"AWS SES transmission failed: {str(e)}")


ses_service = SESService()
