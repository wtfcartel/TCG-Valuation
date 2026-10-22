"""Command line: `logidx <command>`. Run `logidx --help` for the list."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from datetime import UTC, datetime

from sqlalchemy import select


def _initdb(_: argparse.Namespace) -> int:
    from logidx.bootstrap import ensure_ready

    ensure_ready()
    print("Database ready.")
    return 0


def _create_user(args: argparse.Namespace) -> int:
    from logidx.db import session_scope
    from logidx.models import AuditLog, User
    from logidx.security import hash_password

    password = getpass.getpass("Password (min 12 characters): ")
    if password != getpass.getpass("Repeat password: "):
        print("Passwords do not match.", file=sys.stderr)
        return 1
    with session_scope() as s:
        email = args.email.lower().strip()
        user = s.scalar(select(User).where(User.email == email))
        if user is None:
            s.add(User(email=email, password_hash=hash_password(password)))
            action = "user_created"
        else:
            user.password_hash = hash_password(password)
            action = "password_reset"
        s.add(AuditLog(actor="cli", action=action, detail={"email": email}))
    print(f"{action.replace('_', ' ')}: {email}")
    return 0


def _run(args: argparse.Namespace) -> int:
    from logidx.service import execute

    run = execute(trigger="cli", send_daily_report=args.report, actor="cli")
    if run is None:
        print("Run skipped (duplicate).")
        return 1
    print(
        json.dumps(
            {"run_id": run.id, "status": run.status, "error": run.error, "counts": run.counts}, indent=2, default=str
        )
    )
    return 0 if run.status in ("SUCCEEDED", "PARTIAL") else 2


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    from logidx.security import configure_logging
    from logidx.web.app import create_app

    configure_logging()
    uvicorn.run(create_app(), host=args.host, port=args.port, proxy_headers=True, log_config=None)
    return 0


def _assess(args: argparse.Namespace) -> int:
    from logidx.ai.evaluate import assess_pending
    from logidx.ai.provider import get_provider
    from logidx.db import session_scope

    provider = get_provider()
    if provider is None:
        print("No AI provider configured (set XAI_API_KEY).", file=sys.stderr)
        return 1
    with session_scope() as s:
        print(json.dumps(assess_pending(s, provider, limit=args.limit), indent=2))
    return 0


def _recall(_: argparse.Namespace) -> int:
    from logidx import recall
    from logidx.db import session_scope

    with session_scope() as s:
        results = recall.evaluate_all(s)
        for r in results:
            print(f"{r.case.key:45} {r.outcome:12} {r.cause or ''}")
        for f in recall.taxonomy_fixtures():
            print(f"{f.key:45} {'PASS' if f.passed else 'FAIL':12} {'; '.join(f.problems)}")
    return 0


def _report(args: argparse.Namespace) -> int:
    from logidx import report
    from logidx.db import session_scope
    from logidx.notify import send_report

    with session_scope() as s:
        daily = report.build(s)
        if args.send:
            note = send_report(
                s,
                kind="daily_report",
                dedupe_key=daily.day.isoformat(),
                subject=daily.subject,
                html=daily.html,
                text=daily.text,
            )
            print(f"Delivery: {note.status} {note.provider_response or note.error or ''}")
        else:
            print(daily.text)
    return 0


def _probe(_: argparse.Namespace) -> int:
    """One live request per configured source, so integrations can be checked where the network allows."""
    from logidx.settings import get_settings
    from logidx.sources.http import HttpClient, SourceError
    from logidx.sources.registry import board_sources, load_watchlist, query_sources

    http = HttpClient(max_attempts=1)
    failures = 0
    for qs in query_sources():
        ok, reason = qs.available
        if not ok:
            print(f"SKIP  {qs.label}: {reason}")
            continue
        try:
            res = qs.search(http, "general manager", max_age_days=7)
            print(f"OK    {qs.label}: {len(res.vacancies)} results for 'general manager'")
        except SourceError as exc:
            failures += 1
            print(f"FAIL  {qs.label}: {exc}")
    sources = board_sources()
    for board in load_watchlist().configured():
        try:
            res = sources[board.ats].fetch(http, board, title_filter=lambda _t: False)
            print(f"OK    {board.name} ({board.ats}): {len(res.vacancies)} postings listed")
        except SourceError as exc:
            failures += 1
            print(f"FAIL  {board.name} ({board.ats}): {exc}")
    s = get_settings()
    key = s.xai_api_key.get_secret_value()
    if key:
        try:
            resp = http.client.get(f"{s.xai_base_url}/models", headers={"Authorization": f"Bearer {key}"}, timeout=20)
            print(f"{'OK  ' if resp.status_code == 200 else 'FAIL'}  xAI API: HTTP {resp.status_code}")
            failures += resp.status_code != 200
        except Exception as exc:  # network errors are reported, never raised
            failures += 1
            print(f"FAIL  xAI API: {type(exc).__name__}")
    else:
        print("SKIP  xAI API: XAI_API_KEY not configured")
    http.close()
    print(f"\nProbe finished at {datetime.now(UTC).isoformat()} with {failures} failure(s).")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="logidx", description="LogiDx Executive Search")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("initdb", help="create/upgrade the database and seed profile + recall cases").set_defaults(
        fn=_initdb
    )
    p = sub.add_parser("create-user", help="create a dashboard user or reset a password")
    p.add_argument("email")
    p.set_defaults(fn=_create_user)
    p = sub.add_parser("run", help="run one discovery cycle now (same as the Run now button)")
    p.add_argument("--report", action="store_true", help="also build and send the daily report")
    p.set_defaults(fn=_run)
    p = sub.add_parser("serve", help="start the dashboard and the scheduler")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8780)
    p.set_defaults(fn=_serve)
    p = sub.add_parser("assess", help="AI-assess pending relevant vacancies")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(fn=_assess)
    sub.add_parser("recall", help="evaluate known-vacancy recall cases and taxonomy fixtures").set_defaults(fn=_recall)
    p = sub.add_parser("report", help="print today's report, or send it with --send")
    p.add_argument("--send", action="store_true")
    p.set_defaults(fn=_report)
    sub.add_parser("probe", help="live connectivity check of every configured source").set_defaults(fn=_probe)
    args = parser.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
