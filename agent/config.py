"""
Agent Configuration
===================
Resolves the active model provider, credentials, and runtime parameters for
the MedAudit Strands agent.

Priority order:
  1. Bedrock Mantle proxy  (AWS_BEARER_TOKEN_BEDROCK or ANTHROPIC_API_KEY)
  2. Native Boto3 Bedrock Runtime          (IAM/static AWS credentials)
  3. Fallback heuristic in agent_dispatcher — triggered by caller on exception

Model: `openai.gpt-oss-120b`  (the exclusively authorized Bedrock Mantle model)
Proxy: https://bedrock-mantle.us-east-1.api.aws/v1
"""

import os
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

try:
    from backend.app.config import settings
    _DEFAULT_MODEL_ID = getattr(settings, "BEDROCK_MODEL_ID", "openai.gpt-oss-120b")
    _DEFAULT_REGION = getattr(settings, "AWS_REGION", "us-east-1")
    _DEFAULT_KEY = getattr(settings, "AWS_ACCESS_KEY_ID", "mock_key")
    _DEFAULT_SECRET = getattr(settings, "AWS_SECRET_ACCESS_KEY", "mock_secret")
except ImportError:
    _DEFAULT_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "openai.gpt-oss-120b")
    _DEFAULT_REGION = os.getenv("AWS_REGION", "us-east-1")
    _DEFAULT_KEY = os.getenv("AWS_ACCESS_KEY_ID", "mock_key")
    _DEFAULT_SECRET = os.getenv("AWS_SECRET_ACCESS_KEY", "mock_secret")

logger = logging.getLogger(__name__)


class ProviderMode(str, Enum):
    BEDROCK_MANTLE = "bedrock_mantle"      # OpenAI-compatible proxy
    NATIVE_BEDROCK = "native_bedrock"      # boto3 bedrock-runtime
    HEURISTIC = "heuristic"               # deterministic fallback (no LLM)


@dataclass
class AgentConfig:
    """Resolved runtime configuration for the MedAudit agent."""

    mode: ProviderMode

    # ── Bedrock Mantle (OpenAI proxy) ──────────────────────────────────────
    model_id: str = field(default_factory=lambda: _DEFAULT_MODEL_ID)
    mantle_base_url: str = "https://bedrock-mantle.us-east-1.api.aws/v1"
    mantle_api_key: Optional[str] = None
    mantle_workspace_id: str = "default"

    # ── Native Bedrock ─────────────────────────────────────────────────────
    aws_region: str = field(default_factory=lambda: _DEFAULT_REGION)
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None

    # ── Inference params ───────────────────────────────────────────────────
    temperature: float = 0.1
    max_tokens: int = 4096


def resolve_agent_config() -> AgentConfig:
    """
    Inspect available environment variables and return the best AgentConfig.

    Credential resolution chain:
      1. AWS_BEARER_TOKEN_BEDROCK  -> Mantle proxy (preferred)
      2. ANTHROPIC_API_KEY         -> Mantle proxy (alternate key name)
      3. AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY with real values
                                   -> Native Bedrock runtime
      4. Nothing valid             -> returns HEURISTIC mode (no config secret)
    """
    bearer_token = os.getenv("AWS_BEARER_TOKEN_BEDROCK")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    workspace_id = os.getenv("ANTHROPIC_WORKSPACE_ID", "default")

    # ── Mode A: Bedrock Mantle proxy ──────────────────────────────────────
    mantle_key = bearer_token or anthropic_key
    if mantle_key and mantle_key not in ("mock_key", ""):
        logger.info("AgentConfig: using Bedrock Mantle proxy (Mode A)")
        return AgentConfig(
            mode=ProviderMode.BEDROCK_MANTLE,
            mantle_api_key=mantle_key,
            mantle_workspace_id=workspace_id,
        )

    # ── Mode B: Native Boto3 Bedrock Runtime ──────────────────────────────
    aws_key = os.getenv("AWS_ACCESS_KEY_ID", _DEFAULT_KEY)
    aws_secret = os.getenv("AWS_SECRET_ACCESS_KEY", _DEFAULT_SECRET)
    aws_region = os.getenv("AWS_REGION", _DEFAULT_REGION)

    if aws_key and aws_secret and aws_key not in ("mock_key", ""):
        logger.info("AgentConfig: using Native Bedrock Runtime (Mode B)")
        return AgentConfig(
            mode=ProviderMode.NATIVE_BEDROCK,
            aws_access_key_id=aws_key,
            aws_secret_access_key=aws_secret,
            aws_region=aws_region,
        )

    # ── Mode C: Heuristic fallback ────────────────────────────────────────
    logger.warning(
        "AgentConfig: no valid credentials found — agent will raise to "
        "trigger heuristic fallback in agent_dispatcher."
    )
    return AgentConfig(mode=ProviderMode.HEURISTIC)
