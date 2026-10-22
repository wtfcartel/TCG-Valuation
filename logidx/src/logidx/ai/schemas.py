"""Structured AI output. The model's JSON is validated against these schemas before anything is stored;
overall score and fit class are computed deterministically from the validated parts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PROMPT_VERSION = "2026-10-21.1"


class Score(BaseModel):
    score: float = Field(ge=0, le=10)
    rationale: str = Field(min_length=10, max_length=900)


class RequirementEvidence(BaseModel):
    requirement: str = Field(max_length=300)
    importance: Literal["ESSENTIAL", "DESIRABLE"]
    support: Literal["STRONG", "PARTIAL", "NONE"]
    evidence_ids: list[str] = Field(default_factory=list, max_length=6)
    note: str = Field(default="", max_length=400)


class Knockout(BaseModel):
    requirement: str = Field(max_length=300)
    category: Literal[
        "professional_registration",
        "engineering_qualification",
        "clinical_credential",
        "security_clearance",
        "industry_licence",
        "accounting_qualification",
        "legal_practice",
        "citizenship_or_visa",
        "other",
    ]
    importance: Literal["ESSENTIAL", "DESIRABLE"]
    candidate_meets: Literal["YES", "NO", "UNKNOWN"]
    quote: str = Field(max_length=400, description="verbatim text from the advertisement")


class Conversion(BaseModel):
    assessment: Literal["STRONG", "COMPETITIVE", "STRETCH", "LONG_SHOT"]
    rationale: str = Field(min_length=10, max_length=900)
    screening_risks: list[str] = Field(default_factory=list, max_length=8)


class SeniorityCheck(BaseModel):
    is_executive_scope: bool
    rationale: str = Field(min_length=5, max_length=600)


class AssessmentOutput(BaseModel):
    capability_fit: Score
    evidence_fit: Score
    archetype_fit: Score
    ats_lexical_fit: Score
    recruiter_read_fit: Score
    requirements: list[RequirementEvidence] = Field(default_factory=list, max_length=15)
    missing_keywords: list[str] = Field(default_factory=list, max_length=20)
    knockouts: list[Knockout] = Field(default_factory=list, max_length=10)
    conversion: Conversion
    seniority: SeniorityCheck
    specialist_role: bool = Field(description="role is dominated by specialist technical requirements")
    summary: str = Field(min_length=10, max_length=900)


def json_schema() -> dict:  # type: ignore[type-arg]
    """JSON Schema sent to the provider for structured output.

    Strict structured-output modes accept a limited keyword set, so length/size constraints, titles and
    defaults are stripped here; Pydantic still enforces the full schema when the response is validated.
    """
    allowed = {
        "type",
        "properties",
        "required",
        "items",
        "enum",
        "$defs",
        "$ref",
        "description",
        "anyOf",
        "additionalProperties",
    }

    def harden(node: object) -> object:
        if isinstance(node, list):
            return [harden(v) for v in node]
        if not isinstance(node, dict):
            return node
        out = {}
        for key, value in node.items():
            if key in ("properties", "$defs"):  # maps of name -> schema: keep every name
                out[key] = {name: harden(sub) for name, sub in value.items()}
            elif key in allowed:
                out[key] = harden(value)
        if out.get("type") == "object" and "properties" in out:
            out["additionalProperties"] = False
            out["required"] = list(out["properties"])
        return out

    return harden(AssessmentOutput.model_json_schema())  # type: ignore[return-value]
