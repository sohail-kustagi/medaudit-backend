"""
MedAudit Agent Package
======================
Cognitive core of the MedAudit system. Implements the Strands Agents SDK
orchestrator, dual-provider Bedrock gateway, tool definitions, and appeal
letter generation.
"""

from agent.orchestrator import run_medaudit_agent

__all__ = ["run_medaudit_agent"]
