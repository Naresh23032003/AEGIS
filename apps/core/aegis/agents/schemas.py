"""Structured-output shapes for the LLM nodes' "submit" tool.

These are not packages/contracts entries: they are internal tool-call
argument schemas for aegis.llm, never serialized to the console directly
and never shared with the TypeScript side (the console only ever sees the
resulting event payloads, which plan/02-contracts.md already types as
free-form JSON per event type). Where a node's answer IS a shared shape
(ActionProposal, VerifyResult), the code builds that contract object itself
from the tool's answer plus server-assigned fields (action_id, catalog
tier, deterministic probe evidence) rather than trusting the model to
produce the whole contract unsupervised. Noted here per CLAUDE.md, flagged
in the phase report.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TriageResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    severity: Literal["sev1", "sev2", "sev3"]
    affected_services: list[str]
    summary: str = Field(max_length=300)


class DiagnoseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hypothesis: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_refs: list[str] = Field(default_factory=list)


class ProposedActionInput(BaseModel):
    """What the model provides for one action. tier is deliberately absent:
    the catalog is the source of truth for tier (aegis.actions.catalog),
    not the model's guess. action_id is server-assigned."""

    model_config = ConfigDict(extra="forbid")
    catalog_key: str
    params: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(max_length=600)
    rollback_key: str | None = None


class PlanRemediationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actions: list[ProposedActionInput] = Field(min_length=1, max_length=2)


class VerifySubmit(BaseModel):
    """passed is logged for observability but never authoritative; the
    verify node always derives the real pass/fail from
    run_verification_probes' all_healthy (plan/phases/phase-2.md, Gotchas:
    verify uses the phase 1 detection probes, not new logic)."""

    model_config = ConfigDict(extra="forbid")
    passed: bool
    summary: str = Field(max_length=400)
