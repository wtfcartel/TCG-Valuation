"""Candidate–vacancy assessment.

Division of labour:
- Deterministic (never from the model): location/geography, salary, dates, verification status,
  hard-knockout pattern detection, overall score, fit class and overrides.
- Model: capability / evidence / archetype / ATS / recruiter-read judgements with rationales,
  requirement-by-requirement evidence mapping, knockout reading, conversion assessment.

Model output must validate against `AssessmentOutput`. Evidence ids must exist in the candidate
profile, and knockout quotes must appear in the advertisement; otherwise the output is rejected or
the offending item is dropped. Rejected outputs are stored (for audit) but never change scores.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, time

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from logidx.ai.provider import LLMProvider, ProviderError
from logidx.ai.schemas import PROMPT_VERSION, AssessmentOutput, json_schema
from logidx.enums import FitClass, Lifecycle, Verification
from logidx.models import Assessment, Vacancy, VacancyEvent
from logidx.pipeline.normalize import fold
from logidx.profile import CandidateProfile, get_profile, master_cv_text
from logidx.settings import Settings, get_settings
from logidx.taxonomy import Taxonomy, default_taxonomy

WEIGHTS = {
    "capability_fit": 0.30,
    "evidence_fit": 0.25,
    "archetype_fit": 0.15,
    "ats_lexical_fit": 0.10,
    "recruiter_read_fit": 0.20,
}

SYSTEM_PROMPT = """You are an experienced Australian executive-search consultant assessing whether one specific \
candidate should apply for one specific vacancy. Be candid and calibrated: your job is to save the candidate time, \
not to encourage every application.

Rules:
1. Use ONLY the candidate evidence provided (items with ids, and the master CV text if present). Never invent \
achievements, employers, qualifications, credentials, board roles or numbers. Cite evidence by id ("E3") or "CV".
2. The "deterministic_facts" block (location classification, salary, dates, verification) was computed by code. Do \
not restate, recompute or contradict it; you may mention it in rationales.
3. Separate ESSENTIAL requirements from DESIRABLE ones. A knockout is a genuinely mandatory credential, registration, \
licence, clearance or qualification. Quote the advertisement verbatim in `quote`. If the candidate's credentials are \
not listed, use candidate_meets = "UNKNOWN" unless the evidence clearly shows they lack it ("NO").
4. Do not inflate specialist engineering, clinical, manufacturing-process, financial-accounting or IT roles because \
they contain generic leadership language; set specialist_role = true when specialist expertise dominates.
5. A title containing "Lead" is not executive by itself: judge decision authority, P&L, team size, reporting line \
and remuneration in seniority.is_executive_scope.
6. Scores are 0-10 judgements, not probabilities. conversion.assessment is a reasoned view of interview \
competitiveness (STRONG, COMPETITIVE, STRETCH, LONG_SHOT), not a forecast.
7. capability_fit: match of demonstrated experience to responsibilities. evidence_fit: can each key competency be \
supported with the cited evidence. archetype_fit: resemblance to the person a recruiter would realistically \
shortlist. ats_lexical_fit: whether the ad's important concepts are supported by the CV/evidence; list \
missing_keywords. recruiter_read_fit: credibility and relevance in a 15-second CV scan.
8. Keep every rationale short, specific and evidence-based. Australian English."""


@dataclass
class Derived:
    overall: float
    fit_class: FitClass
    knockout_blocked: bool
    override_reasons: list[str]
    knockouts: list[dict[str, object]]


def fit_class_for(score: float) -> FitClass:
    if score >= 8.5:
        return FitClass.PRIORITY
    if score >= 7.0:
        return FitClass.ADJACENT
    if score >= 6.0:
        return FitClass.EXPLORATORY
    return FitClass.LOW


_ORDER = [FitClass.LOW, FitClass.EXPLORATORY, FitClass.ADJACENT, FitClass.PRIORITY]


def _cap(current: FitClass, ceiling: FitClass) -> FitClass:
    return current if _ORDER.index(current) <= _ORDER.index(ceiling) else ceiling


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", fold(text).lower()).strip()


def validate_against_sources(
    out: AssessmentOutput, profile: CandidateProfile, job_text: str, has_cv: bool
) -> list[str]:
    """Reject invented evidence ids; drop knockouts whose quote is not in the ad. Returns notes."""
    notes: list[str] = []
    allowed = {e.id for e in profile.evidence} | ({"CV"} if has_cv else set())
    for req in out.requirements:
        unknown = [i for i in req.evidence_ids if i not in allowed]
        if unknown:
            raise ValueError(f"model cited evidence ids not in the profile: {unknown}")
    norm_job = _norm(job_text)
    kept = []
    for k in out.knockouts:
        quote = _norm(k.quote)
        if quote and (quote in norm_job or _norm(k.requirement) in norm_job):
            kept.append(k)
        else:
            notes.append(f"dropped knockout not found verbatim in the advertisement: {k.requirement!r}")
    out.knockouts = kept
    return notes


def derive(out: AssessmentOutput, vacancy: Vacancy, taxonomy: Taxonomy, profile: CandidateProfile) -> Derived:
    overall = round(sum(getattr(out, k).score * w for k, w in WEIGHTS.items()), 2)
    cls = fit_class_for(overall)
    reasons: list[str] = []
    knockouts: list[dict[str, object]] = [k.model_dump() | {"origin": "ai"} for k in out.knockouts]
    held = {c.lower() for c in profile.credentials}
    for d in taxonomy.deterministic_knockouts(vacancy.description):
        already = any(d["term"] in str(k.get("quote", "")).lower() for k in knockouts)
        if d["type"] == "ESSENTIAL" and not already and not any(d["term"] in h for h in held):
            knockouts.append(
                {
                    "requirement": d["term"],
                    "category": d["category"],
                    "importance": "ESSENTIAL",
                    "candidate_meets": "UNKNOWN",
                    "quote": d["evidence"],
                    "origin": "pattern",
                }
            )
    unmet = [k for k in knockouts if k["importance"] == "ESSENTIAL" and k["candidate_meets"] == "NO"]
    blocked = bool(unmet)
    if blocked:
        overall = min(overall, 5.9)
        cls = FitClass.LOW
        reasons.append("essential requirement not met: " + "; ".join(str(k["requirement"]) for k in unmet))
    if out.specialist_role and cls in (FitClass.PRIORITY, FitClass.ADJACENT):
        cls = _cap(cls, FitClass.EXPLORATORY)
        reasons.append("specialist-dominated role: capped at Exploratory")
    if not out.seniority.is_executive_scope and cls in (FitClass.PRIORITY, FitClass.ADJACENT):
        cls = _cap(cls, FitClass.EXPLORATORY)
        reasons.append("executive scope not evidenced: capped at Exploratory")
    if out.conversion.assessment == "STRETCH" and cls == FitClass.PRIORITY:
        cls = FitClass.ADJACENT
        reasons.append("conversion override: recruiter-screening disadvantage (STRETCH)")
    if out.conversion.assessment == "LONG_SHOT" and cls in (FitClass.PRIORITY, FitClass.ADJACENT):
        cls = _cap(cls, FitClass.EXPLORATORY)
        reasons.append("conversion override: significant screening disadvantage (LONG_SHOT)")
    unknown_essential = [k for k in knockouts if k["importance"] == "ESSENTIAL" and k["candidate_meets"] == "UNKNOWN"]
    if unknown_essential:
        reasons.append("check essential requirement(s): " + "; ".join(str(k["requirement"]) for k in unknown_essential))
    return Derived(overall, cls, blocked, reasons, knockouts)


def build_user_prompt(vacancy: Vacancy, profile: CandidateProfile, cv_text: str | None) -> str:
    facts = {
        "geography": vacancy.geography,
        "geography_reason": vacancy.geography_reason,
        "work_mode": vacancy.work_mode,
        "travel": vacancy.travel_requirements,
        "salary_text": vacancy.salary_text,
        "salary_max_annual_aud": vacancy.salary_max,
        "salary_includes_super": vacancy.salary_includes_super,
        "posted_at": vacancy.posted_at.isoformat() if vacancy.posted_at else None,
        "closing_date": vacancy.closing_date.isoformat() if vacancy.closing_date else None,
        "verification_status": vacancy.verification_status,
        "description_is_snippet": vacancy.description_is_snippet,
    }
    candidate = {
        "headline": profile.headline,
        "home_base": profile.home_base,
        "experience_years": profile.experience_years,
        "evidence": [e.model_dump() for e in profile.evidence],
        "credentials_held": profile.credentials,
        "preferences": profile.preferences,
        "remuneration": profile.remuneration.model_dump(),
    }
    job = {
        "title": vacancy.title,
        "employer": vacancy.employer or "(confidential)",
        "recruiting_agency": vacancy.recruiting_agency,
        "location": vacancy.location_text,
        "employment_type": vacancy.employment_type,
        "description": vacancy.description[:12000],
    }
    parts = [
        "## candidate\n" + json.dumps(candidate, ensure_ascii=False),
        "## master_cv\n" + (cv_text[:15000] if cv_text else "(not imported — rely on evidence items only)"),
        "## vacancy\n" + json.dumps(job, ensure_ascii=False),
        "## deterministic_facts (computed by code — do not alter)\n" + json.dumps(facts, ensure_ascii=False),
    ]
    return "\n\n".join(parts)


def spent_today(session: Session, settings: Settings) -> float:
    tz = settings.tz
    local_midnight = datetime.combine(datetime.now(tz).date(), time.min, tzinfo=tz)
    total = session.scalar(
        select(func.coalesce(func.sum(Assessment.cost_usd), 0.0)).where(
            Assessment.created_at >= local_midnight.astimezone(UTC)
        )
    )
    return float(total or 0.0)


def assess_vacancy(
    session: Session,
    vacancy: Vacancy,
    provider: LLMProvider,
    *,
    profile: CandidateProfile | None = None,
    taxonomy: Taxonomy | None = None,
    settings: Settings | None = None,
) -> Assessment:
    settings = settings or get_settings()
    profile = profile or get_profile(session)
    taxonomy = taxonomy or default_taxonomy()
    cv_text = master_cv_text(session)
    record = Assessment(
        vacancy=vacancy,
        provider=provider.name,
        model=provider.model,
        prompt_version=PROMPT_VERSION,
        description_hash=vacancy.description_hash,
    )
    session.add(record)
    try:
        result = provider.complete_json(
            SYSTEM_PROMPT, build_user_prompt(vacancy, profile, cv_text), "executive_vacancy_assessment", json_schema()
        )
    except ProviderError as exc:
        record.error = str(exc)
        return record
    record.model = result.model
    record.tokens_in, record.tokens_out = result.tokens_in, result.tokens_out
    record.cost_usd = round(
        result.tokens_in / 1e6 * settings.ai_price_input_per_mtok
        + result.tokens_out / 1e6 * settings.ai_price_output_per_mtok,
        6,
    )
    try:
        raw = json.loads(result.text)
        record.output = raw
        out = AssessmentOutput.model_validate(raw)
        notes = validate_against_sources(out, profile, f"{vacancy.title}\n{vacancy.description}", bool(cv_text))
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        record.error = f"invalid model output: {str(exc)[:1500]}"
        return record

    d = derive(out, vacancy, taxonomy, profile)
    record.valid = True
    record.output = out.model_dump()
    record.derived = {
        "overall": d.overall,
        "fit_class": str(d.fit_class),
        "knockout_blocked": d.knockout_blocked,
        "override_reasons": d.override_reasons,
        "validation_notes": notes,
    }
    vacancy.capability_fit = out.capability_fit.score
    vacancy.evidence_fit = out.evidence_fit.score
    vacancy.archetype_fit = out.archetype_fit.score
    vacancy.ats_lexical_fit = out.ats_lexical_fit.score
    vacancy.recruiter_read_fit = out.recruiter_read_fit.score
    vacancy.overall_fit, vacancy.fit_class = d.overall, d.fit_class
    vacancy.conversion_assessment = out.conversion.assessment
    vacancy.knockouts, vacancy.knockout_blocked = d.knockouts, d.knockout_blocked
    vacancy.fit_override_reason = "; ".join(d.override_reasons) or None
    vacancy.ai_summary = out.summary
    vacancy.assessed_at = datetime.now(UTC)
    vacancy.assessed_description_hash = vacancy.description_hash
    session.add(
        VacancyEvent(
            vacancy=vacancy,
            kind="assessed",
            actor=f"ai:{provider.name}",
            detail={"overall": d.overall, "fit_class": str(d.fit_class), "model": result.model},
        )
    )
    return record


def pending_vacancies(session: Session, limit: int) -> list[Vacancy]:
    rows = session.scalars(
        select(Vacancy)
        .where(
            Vacancy.is_relevant.is_(True),
            Vacancy.lifecycle == Lifecycle.ACTIVE,
            Vacancy.verification_status != Verification.CLOSED,
        )
        .order_by(Vacancy.prescore.desc(), Vacancy.first_discovered_at.desc())
    ).all()
    out = [v for v in rows if v.assessed_description_hash != v.description_hash]
    return out[:limit]


def assess_pending(
    session: Session, provider: LLMProvider, *, settings: Settings | None = None, limit: int | None = None
) -> dict[str, int | float | str]:
    settings = settings or get_settings()
    limit = settings.ai_max_assessments_per_run if limit is None else limit
    done = invalid = 0
    stopped = ""
    for vacancy in pending_vacancies(session, limit):
        if spent_today(session, settings) >= settings.ai_daily_budget_usd:
            stopped = f"daily AI budget of US${settings.ai_daily_budget_usd:.2f} reached"
            break
        rec = assess_vacancy(session, vacancy, provider, settings=settings)
        session.commit()
        if rec.valid:
            done += 1
        else:
            invalid += 1
    return {
        "assessed": done,
        "invalid_or_failed": invalid,
        "stopped": stopped,
        "spent_today_usd": round(spent_today(session, settings), 4),
    }
