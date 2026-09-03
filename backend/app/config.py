from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # API Settings
    PROJECT_NAME: str = "MedAudit Backend API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = Field(default="development")
    DEBUG: bool = Field(default=True)

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
    ]

    # Database
    # Default to sqlite+aiosqlite for local testing if Postgres not explicitly supplied
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./medaudit.db"
    )

    # AWS Configuration
    AWS_REGION: str = Field(default="us-east-1")
    AWS_ACCESS_KEY_ID: str = Field(default="mock_key")
    AWS_SECRET_ACCESS_KEY: str = Field(default="mock_secret")
    S3_BUCKET_NAME: str = Field(default="medaudit-bills-bucket")
    S3_PRESIGNED_EXPIRY_SECONDS: int = Field(default=900)

    # AWS Cognito
    COGNITO_USER_POOL_ID: str = Field(default="us-east-1_mock")
    COGNITO_CLIENT_ID: str = Field(default="mock_client_id")
    COGNITO_REGION: str = Field(default="us-east-1")

    # Flag to allow mock / dev auth tokens when developing locally
    ALLOW_MOCK_AUTH: bool = Field(default=True)

    # Agent / Bedrock Settings
    BEDROCK_MODEL_ID: str = Field(default="openai.gpt-oss-120b")
    LLM_MICROSERVICE_URL: str = Field(default="http://localhost:8001/api/v1/audit")


settings = Settings()
