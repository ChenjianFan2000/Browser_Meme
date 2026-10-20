from __future__ import annotations
from pydoc import describe
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator

class ImplementationSpec(BaseModel):
    """String-only, uniform across ByteSized32 / CWMB / Text2World."""
    goal_and_evaluation: str = Field(..., description="(1) Success / failure / scoring.")
    objects_and_class_model: str = Field(..., description="(2) Core objects/classes + hierarchy/containment.")
    key_numbers: str = Field(..., description="(3) Units / ranges / thresholds / device params / step limit.")
    dynamics_transition: str = Field(..., description="(4) Per-tick/turn update rules, clamps, RNG & seed policy.")
    actions_and_preconditions: str = Field(..., description="(5) Action set, guards/preconditions, errors, distractors.")
    interface_contract: str = Field(..., description="(6) Class/method signatures, step() return order, observation, determinism.")

    @field_validator("*")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("field must be a non-empty string")
        return v.strip()

class TestPlanSimple(BaseModel):
    """Testing blueprint as plain strings."""
    happy_path: str = Field(..., description="Steps that should succeed end-to-end")
    edge_cases: str = Field(..., description="Negative/boundary scenarios that must fail or be guarded")
    assertions: str = Field(..., description="Contract checks: return order/types, determinism, invariants")

    @field_validator("*")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("field must be a non-empty string")
        return v.strip()

class WorldModelReport(BaseModel):
    """Minimal uniform report (no adapters, no benchmark profile)."""
    implementation_spec: str = Field(..., description="Points 1–6 for Code Agent.")
    test_plan: str  = Field(..., description="Point 7 for test/eval agents.")

    
    
class CodeReport(BaseModel):
    code_file_path: str = Field(..., description='Saved entrypoint file path')
    entrypoint_code: str = Field(..., description='Complete code content of the entrypoint')

class PlayReport(BaseModel):
    success: bool = Field(
        ...,
        description=(
            'True only if the evaluator (play_env) completed without exceptions '
            'AND met the acceptance criteria from the test plan (e.g., full traversal, '
            'no invariant violations, no time/step limit breaches).'
        ),
    )
    pass_rate: float = Field(
        default=0.0,
        description=(
            'Pass rate metric (0.0-1.0): percentage of successful test cases, episodes, '
            'or evaluation criteria met. Higher values indicate better performance. '
            'Used for ranking and selecting the best code implementation.'
        ),
    )
    analysis: str = Field(
        default=None,
        description=(
            'Concise triage (≈3–6 sentences): summarize what happened, why success/failure '
            'occurred, and point to the most probable root cause (e.g., precondition guard, '
            'state transition error, termination condition). Avoid pasting raw logs.'
        ),
    )
    suggest_fix: str = Field(
        default=None,
        description=(
            'Actionable, minimal fixes to reach acceptance: list concrete code changes or checks '
            '(bullet list allowed). Reference function/method names and, if available, file:line. '
            'Prefer smallest viable patch; avoid vague advice.'
        ),
    )


class PytestReport(BaseModel):
    success: bool = Field(
        ...,
        description=(
            'True iff pytest exit_code == 0 (all tests collected and passed with no hard errors).'
        ),
    )
    analysis: str = Field(
        default=None,
        description=(
            'Short human-readable diagnosis (≈3–6 sentences): group failures by cause, '
            'highlight the first failing assertion for each group, and summarize the likely fix. '
            'Include the most relevant nodeid(s); avoid dumping full tracebacks.'
        ),
    )
    suggest_fix: str = Field(
        default=None,
        description=(
            'Concrete, minimal corrective steps to make tests pass. Use small bullets referencing '
            'specific functions/branches/conditions; include rationale and any contract/invariant '
            'that the change restores.'
        ),
    )
