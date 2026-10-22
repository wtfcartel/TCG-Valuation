"""Scheduling (DST, idempotency), daily report, email delivery, document import and migrations."""

import io
import smtplib
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from logidx import report, service
from logidx.enums import RunStatus, SearchStatus
from logidx.models import Notification, Run, SourceSearch
from logidx.notify import send_report
from logidx.pipeline.runner import RunPlan
from logidx.schedule_config import ScheduleConfig
from logidx.scheduler import next_fire_times, trigger_for
from logidx.settings import Settings
from logidx.sources.registry import RESTRICTED, Watchlist

MEL = ZoneInfo("Australia/Melbourne")


# ------------------------------------------------------------------ scheduling and DST
def test_six_am_is_local_across_dst_start():
    # DST starts 2026-10-04 02:00 AEST → 03:00 AEDT.
    trig = trigger_for("06:00", "Australia/Melbourne")
    before = trig.get_next_fire_time(None, datetime(2026, 10, 2, 7, tzinfo=MEL))  # fires 3 Oct
    after = trig.get_next_fire_time(None, datetime(2026, 10, 4, 7, tzinfo=MEL))
    assert before.astimezone(UTC).hour == 20  # 06:00 AEST (+10) = 20:00 UTC previous day
    assert after.astimezone(UTC).hour == 19  # 06:00 AEDT (+11) = 19:00 UTC previous day
    assert before.astimezone(MEL).hour == after.astimezone(MEL).hour == 6


def test_slots_across_dst_end():
    # DST ends 2027-04-04 03:00 AEDT → 02:00 AEST.
    times = next_fire_times(
        ScheduleConfig(), datetime(2027, 4, 3, 12, tzinfo=MEL), count=6, tz_name="Australia/Melbourne"
    )
    local = [t.astimezone(MEL).strftime("%d %H:%M %z") for t in times]
    assert local == [
        "03 14:00 +1100",
        "03 20:00 +1100",
        "04 06:00 +1000",
        "04 14:00 +1000",
        "04 20:00 +1000",
        "05 06:00 +1000",
    ]


def test_schedule_validation():
    with pytest.raises(ValidationError):
        ScheduleConfig(slots=["25:00"])
    with pytest.raises(ValidationError):
        ScheduleConfig(slots=[])
    assert ScheduleConfig(slots=["20:00", "06:00", "06:00"]).slots == ["06:00", "20:00"]


def test_scheduled_slot_cannot_run_twice(monkeypatch):
    empty = RunPlan([], {}, Watchlist([]), RESTRICTED)
    key = service.scheduled_key("2026-10-21", "06:00")
    first = service.execute(trigger="scheduled", slot="06:00", idempotency_key=key, plan=empty, send_daily_report=False)
    second = service.execute(
        trigger="scheduled", slot="06:00", idempotency_key=key, plan=empty, send_daily_report=False
    )
    assert first is not None and second is None


# ------------------------------------------------------------------ report
def test_report_distinguishes_failed_from_zero(session):
    run = Run(idempotency_key="r1", trigger="test", status=RunStatus.PARTIAL)
    session.add(run)
    session.add(
        SourceSearch(
            run=run,
            source="adzuna",
            source_label="Adzuna Australia",
            query="general manager",
            category="egm_group",
            access_method="API",
            status=SearchStatus.FAILED,
            error="HTTP 503 from api.adzuna.com",
        )
    )
    session.commit()
    daily = report.build(session)
    assert "HTTP 503" in daily.html and "FAILED" in daily.text
    assert "SEEK Australia" in daily.text  # restricted rows always shown
    assert "Gmail correspondence reconciliation is not implemented" in daily.text
    assert daily.subject.startswith("LogiDx")


# ------------------------------------------------------------------ email
class FakeSMTP:
    instances: list["FakeSMTP"] = []

    def __init__(self, host, port, fail=None, refused=None):
        self.fail, self.refused, self.sent = fail, refused or {}, []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        if self.fail:
            raise self.fail

    def login(self, u, p):
        pass

    def send_message(self, msg):
        self.sent.append(msg)
        return self.refused


SMTP_SETTINGS = Settings(
    SMTP_HOST="smtp.example.com",
    SMTP_FROM="logidx@example.com",
    LOGIDX_REPORT_RECIPIENT="me@example.com",
    SMTP_PASSWORD="hunter2-secret",
)


def test_email_disabled_without_config(session):
    note = send_report(
        session, kind="daily_report", dedupe_key="d1", subject="s", html="<p>h</p>", text="t", settings=Settings()
    )
    assert note.status == "DISABLED" and "dashboard" in note.error


def test_email_sent_only_when_accepted_and_idempotent(session):
    note = send_report(
        session,
        kind="daily_report",
        dedupe_key="d2",
        subject="s",
        html="h",
        text="t",
        settings=SMTP_SETTINGS,
        smtp_factory=lambda h, p: FakeSMTP(h, p),
    )
    assert note.status == "SENT" and "accepted by smtp.example.com" in note.provider_response
    count = len(FakeSMTP.instances)
    again = send_report(
        session,
        kind="daily_report",
        dedupe_key="d2",
        subject="s",
        html="h",
        text="t",
        settings=SMTP_SETTINGS,
        smtp_factory=lambda h, p: FakeSMTP(h, p),
    )
    assert again.id == note.id and len(FakeSMTP.instances) == count  # not re-sent


def test_email_failure_retries_and_redacts(session):
    note = send_report(
        session,
        kind="daily_report",
        dedupe_key="d3",
        subject="s",
        html="h",
        text="t",
        settings=SMTP_SETTINGS,
        sleep=lambda _s: None,
        smtp_factory=lambda h, p: FakeSMTP(h, p, fail=smtplib.SMTPAuthenticationError(535, b"bad hunter2-secret")),
    )
    assert note.status == "FAILED" and note.attempts == 3 and "hunter2-secret" not in note.error


def test_refused_recipient_is_failure(session):
    note = send_report(
        session,
        kind="daily_report",
        dedupe_key="d4",
        subject="s",
        html="h",
        text="t",
        settings=SMTP_SETTINGS,
        sleep=lambda _s: None,
        smtp_factory=lambda h, p: FakeSMTP(h, p, refused={"me@example.com": (550, b"no")}),
    )
    assert note.status == "FAILED"
    assert session.scalar(select(Notification).where(Notification.dedupe_key == "d4")).sent_at is None


# ------------------------------------------------------------------ documents
def test_master_cv_docx_import(session):
    from docx import Document as Docx

    from logidx.documents import import_master_cv

    buf = io.BytesIO()
    d = Docx()
    d.add_paragraph("Chief Operating Officer — Example Logistics (fixture)")
    d.save(buf)
    doc = import_master_cv(session, "cv.docx", buf.getvalue())
    assert doc.version == 1 and "Chief Operating Officer" in doc.extracted_text
    assert import_master_cv(session, "cv2.docx", buf.getvalue()).version == 2


def test_master_cv_rejects_bad_files(session):
    from logidx.documents import import_master_cv

    with pytest.raises(ValueError):
        import_master_cv(session, "cv.exe", b"MZ")
    with pytest.raises(ValueError):
        import_master_cv(session, "cv.pdf", b"not a pdf")


# ------------------------------------------------------------------ migrations
def test_migrations_match_models():
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from logidx.db import get_engine
    from logidx.models import Base

    with get_engine().connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []
