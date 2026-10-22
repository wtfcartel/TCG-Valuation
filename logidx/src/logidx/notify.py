"""Email delivery with retry. A message is recorded as SENT only when the SMTP server accepts it for every
recipient; that is acceptance by the mail server, not confirmation of inbox delivery."""

from __future__ import annotations

import smtplib
import ssl
import time
from collections.abc import Callable
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import make_msgid

from sqlalchemy import select
from sqlalchemy.orm import Session

from logidx.models import Notification
from logidx.security import redact
from logidx.settings import Settings, get_settings

SmtpFactory = Callable[[str, int], smtplib.SMTP]


def email_configured(settings: Settings) -> bool:
    return bool(settings.smtp_host and settings.smtp_from and settings.report_recipient)


def send_report(
    session: Session,
    *,
    kind: str,
    dedupe_key: str,
    subject: str,
    html: str,
    text: str,
    settings: Settings | None = None,
    smtp_factory: SmtpFactory | None = None,
    max_attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> Notification:
    settings = settings or get_settings()
    note = session.scalar(select(Notification).where(Notification.kind == kind, Notification.dedupe_key == dedupe_key))
    if note is not None and note.status == "SENT":
        return note  # idempotent: never send the same daily report twice
    if note is None:
        note = Notification(
            kind=kind,
            dedupe_key=dedupe_key,
            subject=subject,
            body_html=html,
            body_text=text,
            status="PENDING",
            attempts=0,
            recipient=settings.report_recipient or None,
        )
        session.add(note)
    else:
        note.subject, note.body_html, note.body_text = subject, html, text
    if not email_configured(settings):
        note.status = "DISABLED"
        note.error = "SMTP not configured — report available in the dashboard only"
        session.commit()
        return note

    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, settings.smtp_from, settings.report_recipient
    msg["Message-ID"] = make_msgid(domain=settings.smtp_from.split("@")[-1] or None)
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    factory = smtp_factory or (lambda host, port: smtplib.SMTP(host, port, timeout=30))
    for attempt in range(1, max_attempts + 1):
        note.attempts += 1
        try:
            with factory(settings.smtp_host, settings.smtp_port) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                if settings.smtp_username:
                    smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
                refused = smtp.send_message(msg)
            if refused:
                raise smtplib.SMTPRecipientsRefused(refused)
            note.status, note.sent_at, note.error = "SENT", datetime.now(UTC), None
            note.provider_response = f"accepted by {settings.smtp_host}; Message-ID {msg['Message-ID']}"
            break
        except (smtplib.SMTPException, OSError) as exc:
            note.status, note.error = (
                "FAILED",
                redact(f"attempt {attempt}: {type(exc).__name__}: {exc}", settings.secret_values())[:1000],
            )
            if attempt < max_attempts:
                sleep(2**attempt)
    session.commit()
    return note
