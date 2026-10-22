"""Candidate profile: schema, seed loading and the database-backed editable copy."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from logidx.models import Document, SettingKV
from logidx.settings import get_settings

PROFILE_KEY = "candidate_profile"


class Evidence(BaseModel):
    id: str
    claim: str
    source: str


class Remuneration(BaseModel):
    discovery_threshold_base_aud: float = 160_000
    preferred_min_aud: float = 200_000
    preferred_max_aud: float = 300_000
    include_undisclosed: bool = True
    notes: str = ""


class CandidateProfile(BaseModel):
    name: str = ""
    home_base: str = "Ormond, Melbourne, Victoria"
    experience_years: int | None = None
    headline: str = ""
    geography: dict[str, list[str]] = Field(default_factory=dict)
    remuneration: Remuneration = Field(default_factory=Remuneration)
    preferences: dict[str, object] = Field(default_factory=dict)
    evidence: list[Evidence] = Field(default_factory=list)
    credentials: list[str] = Field(default_factory=list)


def seed_profile(path: Path | None = None) -> CandidateProfile:
    path = path or get_settings().config_dir / "profile.yaml"
    with path.open(encoding="utf-8") as fh:
        return CandidateProfile.model_validate(yaml.safe_load(fh) or {})


def get_profile(session: Session) -> CandidateProfile:
    row = session.get(SettingKV, PROFILE_KEY)
    if row is None:
        return seed_profile()
    return CandidateProfile.model_validate(row.value)


def save_profile(session: Session, profile: CandidateProfile) -> None:
    row = session.get(SettingKV, PROFILE_KEY)
    if row is None:
        session.add(SettingKV(key=PROFILE_KEY, value=profile.model_dump()))
    else:
        row.value = profile.model_dump()


def master_cv_text(session: Session) -> str | None:
    doc = session.query(Document).filter(Document.kind == "master_cv").order_by(Document.version.desc()).first()
    return doc.extracted_text if doc else None
