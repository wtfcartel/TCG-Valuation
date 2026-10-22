"""ORM models. Every timestamp is stored in UTC; display code converts to Australia/Melbourne.

Nothing here is ever hard-deleted by the pipeline: expired vacancies keep their history,
assessments, application events and documents.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from logidx.enums import ApplicationStatus, FitClass, Geography, Lifecycle, Verification, WorkMode


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware UTC datetimes on every backend (SQLite drops tzinfo otherwise)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime passed to UTCDateTime")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class Base(DeclarativeBase):
    type_annotation_map = {datetime: UTCDateTime, dict[str, Any]: JSON, list[Any]: JSON}


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_login_at: Mapped[datetime | None]


class SettingKV(Base):
    """Editable non-secret settings (schedule, profile, thresholds). Secrets never live here."""

    __tablename__ = "settings_kv"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class Agency(Base):
    __tablename__ = "agencies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    website: Mapped[str | None] = mapped_column(String(500))
    specialty: Mapped[str | None] = mapped_column(Text)
    careers_source: Mapped[str | None] = mapped_column(String(100))  # e.g. "bullhorn:<board key>"
    notes: Mapped[str | None] = mapped_column(Text)
    last_verified_at: Mapped[datetime | None]
    recruiters: Mapped[list[Recruiter]] = relationship(back_populates="agency")


class Recruiter(Base):
    __tablename__ = "recruiters"
    id: Mapped[int] = mapped_column(primary_key=True)
    agency_id: Mapped[int | None] = mapped_column(ForeignKey("agencies.id"))
    name: Mapped[str] = mapped_column(String(200))
    title: Mapped[str | None] = mapped_column(String(200))
    specialty: Mapped[str | None] = mapped_column(Text)
    public_email: Mapped[str | None] = mapped_column(String(320))
    public_phone: Mapped[str | None] = mapped_column(String(50))
    profile_url: Mapped[str | None] = mapped_column(String(500))
    contact_source: Mapped[str | None] = mapped_column(String(500))  # where public info was found
    previously_contacted: Mapped[bool] = mapped_column(default=False)
    last_verified_at: Mapped[datetime | None]
    notes: Mapped[str | None] = mapped_column(Text)
    agency: Mapped[Agency | None] = relationship(back_populates="recruiters")


class Vacancy(Base):
    __tablename__ = "vacancies"
    id: Mapped[int] = mapped_column(primary_key=True)

    employer: Mapped[str | None] = mapped_column(String(300))
    is_confidential: Mapped[bool] = mapped_column(default=False)
    agency_id: Mapped[int | None] = mapped_column(ForeignKey("agencies.id"))
    recruiting_agency: Mapped[str | None] = mapped_column(String(300))
    title: Mapped[str] = mapped_column(String(500))
    original_title: Mapped[str] = mapped_column(String(500))
    normalized_title: Mapped[str] = mapped_column(String(500), index=True)
    norm_employer: Mapped[str] = mapped_column(String(300), index=True, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    description_is_snippet: Mapped[bool] = mapped_column(default=False)
    description_hash: Mapped[str] = mapped_column(String(64), index=True, default="")
    reference: Mapped[str | None] = mapped_column(String(100), index=True)

    industry: Mapped[str | None] = mapped_column(String(200))
    primary_category: Mapped[str | None] = mapped_column(String(50), index=True)
    categories: Mapped[list[Any]] = mapped_column(JSON, default=list)
    families: Mapped[list[Any]] = mapped_column(JSON, default=list)
    seniority_signal: Mapped[str | None] = mapped_column(String(100))
    relevance_flags: Mapped[list[Any]] = mapped_column(JSON, default=list)
    prescore: Mapped[float] = mapped_column(Float, default=0.0)
    is_relevant: Mapped[bool] = mapped_column(default=False, index=True)
    employment_type: Mapped[str | None] = mapped_column(String(100))

    location_text: Mapped[str | None] = mapped_column(String(500))
    work_base: Mapped[str | None] = mapped_column(String(300))
    work_mode: Mapped[str] = mapped_column(String(20), default=WorkMode.UNKNOWN)
    geography: Mapped[str] = mapped_column(String(80), default=Geography.UNKNOWN, index=True)
    geography_reason: Mapped[str | None] = mapped_column(Text)
    travel_requirements: Mapped[str | None] = mapped_column(Text)

    salary_text: Mapped[str | None] = mapped_column(String(500))
    salary_min: Mapped[float | None] = mapped_column(Float)
    salary_max: Mapped[float | None] = mapped_column(Float)
    salary_currency: Mapped[str | None] = mapped_column(String(3))
    salary_period: Mapped[str | None] = mapped_column(String(20))
    salary_includes_super: Mapped[bool | None] = mapped_column(Boolean)
    salary_base_estimate_max: Mapped[float | None] = mapped_column(Float)
    salary_below_threshold: Mapped[bool] = mapped_column(default=False)
    benefits: Mapped[list[Any]] = mapped_column(JSON, default=list)

    posted_at: Mapped[datetime | None]
    first_discovered_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    closing_date: Mapped[date | None] = mapped_column(Date)
    advert_url: Mapped[str | None] = mapped_column(String(1000))
    application_url: Mapped[str | None] = mapped_column(String(1000))
    lifecycle: Mapped[str] = mapped_column(String(20), default=Lifecycle.ACTIVE, index=True)

    verification_status: Mapped[str] = mapped_column(String(40), default=Verification.UNVERIFIED_STALE, index=True)
    verified_at: Mapped[datetime | None]
    verification_evidence: Mapped[list[Any]] = mapped_column(JSON, default=list)

    fit_class: Mapped[str] = mapped_column(String(20), default=FitClass.UNASSESSED, index=True)
    overall_fit: Mapped[float | None] = mapped_column(Float)
    capability_fit: Mapped[float | None] = mapped_column(Float)
    evidence_fit: Mapped[float | None] = mapped_column(Float)
    archetype_fit: Mapped[float | None] = mapped_column(Float)
    ats_lexical_fit: Mapped[float | None] = mapped_column(Float)
    recruiter_read_fit: Mapped[float | None] = mapped_column(Float)
    conversion_assessment: Mapped[str | None] = mapped_column(String(40))
    knockouts: Mapped[list[Any]] = mapped_column(JSON, default=list)
    knockout_blocked: Mapped[bool] = mapped_column(default=False)
    fit_override_reason: Mapped[str | None] = mapped_column(Text)
    ai_summary: Mapped[str | None] = mapped_column(Text)
    assessed_at: Mapped[datetime | None]
    assessed_description_hash: Mapped[str | None] = mapped_column(String(64))

    application_status: Mapped[str] = mapped_column(String(20), default=ApplicationStatus.DISCOVERED, index=True)
    applied_at: Mapped[datetime | None]
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    sources: Mapped[list[VacancySource]] = relationship(back_populates="vacancy", cascade="all, delete-orphan")
    events: Mapped[list[VacancyEvent]] = relationship(
        back_populates="vacancy", order_by="VacancyEvent.at", cascade="all, delete-orphan"
    )
    assessments: Mapped[list[Assessment]] = relationship(
        back_populates="vacancy", order_by="Assessment.created_at", cascade="all, delete-orphan"
    )
    documents: Mapped[list[Document]] = relationship(back_populates="vacancy")
    agency: Mapped[Agency | None] = relationship()


class VacancySource(Base):
    """One sighting channel of a vacancy: (source, source-specific id). Cross-posts share a vacancy."""

    __tablename__ = "vacancy_sources"
    __table_args__ = (UniqueConstraint("source", "source_job_id", name="uq_source_job"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    vacancy_id: Mapped[int] = mapped_column(ForeignKey("vacancies.id"), index=True)
    source: Mapped[str] = mapped_column(String(100))
    board: Mapped[str | None] = mapped_column(String(200))
    source_job_id: Mapped[str] = mapped_column(String(300))
    access_method: Mapped[str] = mapped_column(String(30))
    is_employer_requisition: Mapped[bool] = mapped_column(default=False)
    is_agency_listing: Mapped[bool] = mapped_column(default=False)
    url: Mapped[str | None] = mapped_column(String(1000))
    apply_url: Mapped[str | None] = mapped_column(String(1000))
    first_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_seen_run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id"))
    present: Mapped[bool] = mapped_column(default=True)
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    vacancy: Mapped[Vacancy] = relationship(back_populates="sources")


class VacancyEvent(Base):
    """Append-only audit trail for a vacancy: discovery, merges, verification, status, AI, documents."""

    __tablename__ = "vacancy_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    vacancy_id: Mapped[int] = mapped_column(ForeignKey("vacancies.id"), index=True)
    at: Mapped[datetime] = mapped_column(default=utcnow)
    kind: Mapped[str] = mapped_column(String(50))
    actor: Mapped[str] = mapped_column(String(50), default="system")
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    vacancy: Mapped[Vacancy] = relationship(back_populates="events")


class Assessment(Base):
    """Every AI call, valid or not, with token counts and cost. Scores are only copied to the
    vacancy when the output passed schema validation."""

    __tablename__ = "assessments"
    id: Mapped[int] = mapped_column(primary_key=True)
    vacancy_id: Mapped[int] = mapped_column(ForeignKey("vacancies.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(20))
    description_hash: Mapped[str] = mapped_column(String(64))
    valid: Mapped[bool] = mapped_column(default=False)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    derived: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    tokens_in: Mapped[int] = mapped_column(default=0)
    tokens_out: Mapped[int] = mapped_column(default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    vacancy: Mapped[Vacancy] = relationship(back_populates="assessments")


class Document(Base):
    """Master CV and generated application documents (Phase 4 generation; import available now)."""

    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    vacancy_id: Mapped[int | None] = mapped_column(ForeignKey("vacancies.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))  # master_cv | tailored_cv | cover_letter | ksc | report
    version: Mapped[int] = mapped_column(default=1)
    filename: Mapped[str] = mapped_column(String(300))
    path: Mapped[str] = mapped_column(String(1000))
    sha256: Mapped[str] = mapped_column(String(64))
    extracted_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    vacancy: Mapped[Vacancy | None] = relationship(back_populates="documents")


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True)
    trigger: Mapped[str] = mapped_column(String(20))  # scheduled | manual | cli
    slot: Mapped[str | None] = mapped_column(String(10))  # "06:00" etc. for scheduled runs
    scheduled_for: Mapped[datetime | None]
    started_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    finished_at: Mapped[datetime | None]
    status: Mapped[str] = mapped_column(String(20))
    error: Mapped[str | None] = mapped_column(Text)
    counts: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    searches: Mapped[list[SourceSearch]] = relationship(back_populates="run", cascade="all, delete-orphan")
    category_audits: Mapped[list[CategoryAudit]] = relationship(back_populates="run", cascade="all, delete-orphan")


class SourceSearch(Base):
    """One independently logged search: a (source, board/query, category) attempt within a run."""

    __tablename__ = "source_searches"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), index=True)
    source: Mapped[str] = mapped_column(String(100), index=True)
    source_label: Mapped[str] = mapped_column(String(200))
    board: Mapped[str | None] = mapped_column(String(200))
    query: Mapped[str | None] = mapped_column(String(500))
    category: Mapped[str | None] = mapped_column(String(50), index=True)
    access_method: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), index=True)
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    duration_ms: Mapped[int] = mapped_column(default=0)
    results_retrieved: Mapped[int] = mapped_column(default=0)
    unique_vacancies: Mapped[int] = mapped_column(default=0)
    new_vacancies: Mapped[int] = mapped_column(default=0)
    relevant_vacancies: Mapped[int] = mapped_column(default=0)
    verified_open: Mapped[int] = mapped_column(default=0)
    truncated: Mapped[bool] = mapped_column(default=False)
    error: Mapped[str | None] = mapped_column(Text)
    limitation: Mapped[str | None] = mapped_column(Text)
    run: Mapped[Run] = relationship(back_populates="searches")


class CategoryAudit(Base):
    __tablename__ = "category_audits"
    __table_args__ = (UniqueConstraint("run_id", "category", name="uq_run_category"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), index=True)
    category: Mapped[str] = mapped_column(String(50))
    complete: Mapped[bool] = mapped_column(default=False)
    queries: Mapped[list[Any]] = mapped_column(JSON, default=list)
    sources_succeeded: Mapped[list[Any]] = mapped_column(JSON, default=list)
    sources_failed: Mapped[list[Any]] = mapped_column(JSON, default=list)
    sources_not_searched: Mapped[list[Any]] = mapped_column(JSON, default=list)
    results_retrieved: Mapped[int] = mapped_column(default=0)
    relevant_vacancies: Mapped[int] = mapped_column(default=0)
    note: Mapped[str | None] = mapped_column(Text)
    run: Mapped[Run] = relationship(back_populates="category_audits")


class RunLock(Base):
    __tablename__ = "run_locks"
    name: Mapped[str] = mapped_column(String(50), primary_key=True)
    holder: Mapped[str] = mapped_column(String(100))
    acquired_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime]


class RecallCase(Base):
    __tablename__ = "recall_cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True)
    label: Mapped[str] = mapped_column(String(300))
    spec: Mapped[dict[str, Any]] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(default=True)
    results: Mapped[list[RecallResult]] = relationship(
        back_populates="case", order_by="RecallResult.at", cascade="all, delete-orphan"
    )


class RecallResult(Base):
    __tablename__ = "recall_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("recall_cases.id"), index=True)
    at: Mapped[datetime] = mapped_column(default=utcnow)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id"))
    outcome: Mapped[str] = mapped_column(String(20))
    cause: Mapped[str | None] = mapped_column(String(40))
    vacancy_id: Mapped[int | None] = mapped_column(ForeignKey("vacancies.id"))
    latency_hours: Mapped[float | None] = mapped_column(Float)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    case: Mapped[RecallCase] = relationship(back_populates="results")


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("kind", "dedupe_key", name="uq_notification_dedupe"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))
    dedupe_key: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    recipient: Mapped[str | None] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(500))
    body_html: Mapped[str] = mapped_column(Text)
    body_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))  # PENDING | SENT | FAILED | DISABLED
    attempts: Mapped[int] = mapped_column(default=0)
    sent_at: Mapped[datetime | None]
    provider_response: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)


class AuditLog(Base):
    """Security-relevant and user actions (logins, settings changes, status changes, runs)."""

    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(320))
    action: Mapped[str] = mapped_column(String(100))
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
