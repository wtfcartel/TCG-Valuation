"""High-level operations shared by the scheduler, the dashboard's Run Now button and the CLI."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from logidx import recall, report
from logidx.ai.evaluate import assess_pending
from logidx.ai.provider import get_provider
from logidx.db import session_scope
from logidx.enums import RunStatus
from logidx.models import AuditLog, Run
from logidx.notify import send_report
from logidx.pipeline.runner import RunPlan, run_discovery, start_run
from logidx.schedule_config import get_schedule
from logidx.settings import get_settings
from logidx.sources.http import HttpClient

log = logging.getLogger(__name__)


def scheduled_key(local_day: str, slot: str) -> str:
    return f"scheduled:{local_day}:{slot}"


def post_run(session: Session, run: Run, *, send_daily_report: bool = False) -> None:
    """AI assessment, recall evaluation and (for the report slot) the daily report. Each step isolated."""
    counts = dict(run.counts or {})
    schedule = get_schedule(session)
    provider = get_provider() if schedule.ai_enabled else None
    if provider is None:
        counts["ai"] = "skipped: no AI provider configured (XAI_API_KEY)" if schedule.ai_enabled else "disabled"
    else:
        try:
            counts["ai"] = assess_pending(session, provider)
        except Exception as exc:
            log.exception("AI assessment step failed")
            counts["ai"] = f"failed: {type(exc).__name__}"
    try:
        results = recall.evaluate_all(session, run)
        counts["recall"] = {r.case.key: r.outcome for r in results}
    except Exception as exc:
        log.exception("recall evaluation failed")
        counts["recall"] = f"failed: {type(exc).__name__}"
    run.counts = counts
    session.commit()
    if send_daily_report:
        daily = report.build(session)
        note = send_report(
            session,
            kind="daily_report",
            dedupe_key=daily.day.isoformat(),
            subject=daily.subject,
            html=daily.html,
            text=daily.text,
        )
        run.counts = {**run.counts, "report": note.status}
        session.commit()


def execute(
    *,
    trigger: str,
    slot: str | None = None,
    scheduled_for: datetime | None = None,
    idempotency_key: str | None = None,
    send_daily_report: bool | None = None,
    plan: RunPlan | None = None,
    http: HttpClient | None = None,
    actor: str = "system",
) -> Run | None:
    with session_scope() as session:
        run = start_run(
            session, trigger=trigger, idempotency_key=idempotency_key, slot=slot, scheduled_for=scheduled_for
        )
        if run is None:
            log.info("duplicate trigger ignored", extra={"idempotency_key": idempotency_key})
            return None
        session.add(
            AuditLog(actor=actor, action="run_started", detail={"run_id": run.id, "trigger": trigger, "slot": slot})
        )
        session.commit()
        if send_daily_report is None:
            send_daily_report = slot is not None and slot == get_schedule(session).report_slot
        run = run_discovery(
            session,
            run,
            http=http,
            plan=plan,
            post_run=lambda s, r: post_run(s, r, send_daily_report=bool(send_daily_report)),
        )
        return run


def run_scheduled_slot(slot: str) -> Run | None:
    tz = get_settings().tz
    now_local = datetime.now(tz)
    hour, minute = map(int, slot.split(":"))
    scheduled = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return execute(
        trigger="scheduled",
        slot=slot,
        scheduled_for=scheduled.astimezone(UTC),
        idempotency_key=scheduled_key(now_local.date().isoformat(), slot),
    )


def last_run_summary(session: Session) -> Run | None:
    return session.query(Run).filter(Run.status != RunStatus.SKIPPED).order_by(Run.started_at.desc()).first()
