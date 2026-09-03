"""
Strands Model Adapter
=====================
Builds and returns a Strands SDK `Model` instance wired to either:
  - Mode A: Bedrock Mantle OpenAI-compatible proxy (AsyncOpenAI client)
  - Mode B: Native AWS Bedrock Runtime (boto3)

The adapter is consumed exclusively by `orchestrator.py`.
"""

import logging
from typing import Optional

from agent.config import AgentConfig, ProviderMode

logger = logging.getLogger(__name__)


def get_strands_model(cfg: AgentConfig):
    """
    Return a Strands-compatible model object for the given AgentConfig.

    Raises:
        RuntimeError: If mode is HEURISTIC (no LLM available), signalling
                      the caller to invoke the heuristic fallback.
        ImportError:  If the `strands` SDK is not installed.
    """
    if cfg.mode == ProviderMode.HEURISTIC:
        raise RuntimeError(
            "No valid cloud credentials found. Raising to trigger "
            "deterministic heuristic fallback."
        )

    if cfg.mode == ProviderMode.BEDROCK_MANTLE:
        logger.info(
            "Adapter: initialising OpenAIModel with Bedrock Mantle proxy → %s (model=%s)",
            cfg.mantle_base_url,
            cfg.model_id,
        )
        from openai import AsyncOpenAI
        from strands.models.openai import OpenAIModel

        client = AsyncOpenAI(
            base_url=cfg.mantle_base_url,
            api_key=cfg.mantle_api_key or "mock_key",
            default_headers={"OpenAI-Project": cfg.mantle_workspace_id or "default"},
        )
        model = OpenAIModel(
            client=client,
            model_id=cfg.model_id or "openai.gpt-oss-120b",
            params={"max_tokens": cfg.max_tokens, "temperature": cfg.temperature},
        )
        return model

    try:
        from strands.models import BedrockModel  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "strands-agents package not found. "
            "Run: pip install strands-agents strands-agents-tools"
        ) from exc

    # Mode B: Native Bedrock Runtime
    logger.info(
        "Adapter: initialising BedrockModel with native Bedrock Runtime (region=%s)",
        cfg.aws_region,
    )
    import boto3

    session = boto3.Session(
        aws_access_key_id=cfg.aws_access_key_id,
        aws_secret_access_key=cfg.aws_secret_access_key,
        region_name=cfg.aws_region,
    )
    model = BedrockModel(
        model_id=cfg.model_id,
        boto_session=session,
        max_tokens=cfg.max_tokens,
        additional_request_fields={"temperature": cfg.temperature},
    )
    return model
