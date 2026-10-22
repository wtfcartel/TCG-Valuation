"""Dashboard (server-rendered) and JSON API."""

from __future__ import annotations

import hashlib
import logging
import secrets
import threading
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Any

import yaml
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from logidx import coverage, recall, report
from logidx.ai.evaluate import assess_vacancy
from logidx.ai.provider import get_provider
from logidx.db import get_sessionmaker
from logidx.documents import import_master_cv
from logidx.enums import AccessMethod, ApplicationStatus, FitClass, Geography, Lifecycle, RunStatus, Verification
from logidx.locks import holder_of
from logidx.models import Agency, AuditLog, Document, RecallCase, Recruiter, Run, User, Vacancy, VacancyEvent
from logidx.pipeline.ingest import ingest
from logidx.pipeline.runner import LOCK_NAME
from logidx.profile import CandidateProfile, get_profile, save_profile
from logidx.schedule_config import ScheduleConfig, get_schedule, save_schedule
from logidx.security import LoginRateLimiter, csrf_matches, new_csrf_token, verify_password
from logidx.settings import PACKAGE_ROOT, get_settings
from logidx.sources.base import RawVacancy
from logidx.sources.http import HttpClient
from logidx.sources.registry import RESTRICTED, load_watchlist
from logidx.taxonomy import default_taxonomy
from logidx.verification import verify_now

log = logging.getLogger(__name__)
templates = Jinja2Templates(directory=str(PACKAGE_ROOT / "web" / "templates"))
limiter = LoginRateLimiter()
PIPELINE = [
    ApplicationStatus.SAVED,
    ApplicationStatus.REVIEWING,
    ApplicationStatus.APPLIED,
    ApplicationStatus.INTERVIEWING,
    ApplicationStatus.OFFER,
    ApplicationStatus.REJECTED,
    ApplicationStatus.WITHDRAWN,
]


class NotAuthenticated(Exception):
    pass


def _local(dt: datetime | None, fmt: str = "%a %d %b %Y %H:%M") -> str:
    if dt is None:
        return "—"
    return dt.astimezone(get_settings().tz).strftime(fmt)


def _money(v: float | None) -> str:
    return "—" if v is None else f"${v / 1000:,.0f}k"


def _slug(v: object) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in str(v).lower()).strip("-")


templates.env.filters.update(local=_local, money=_money, slug=_slug)
templates.env.globals.update(Verification=Verification, FitClass=FitClass, ApplicationStatus=ApplicationStatus)


def get_db() -> Iterator[Session]:
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    uid = request.session.get("uid")
    user = db.get(User, uid) if uid else None
    if user is None:
        raise NotAuthenticated()
    return user


async def check_csrf(request: Request) -> None:
    if request.method == "POST":
        form = await request.form()
        supplied = form.get("csrf") or request.headers.get("X-CSRF-Token")
        if not csrf_matches(request.session.get("csrf"), str(supplied) if supplied else None):
            raise HTTPException(status_code=403, detail="invalid or missing CSRF token")


def render(request: Request, name: str, **ctx: Any) -> HTMLResponse:
    if "csrf" not in request.session:
        request.session["csrf"] = new_csrf_token()
    with get_sessionmaker()() as db:
        lock = holder_of(db, LOCK_NAME)
    ctx.setdefault("flash", request.session.pop("flash", None))
    return templates.TemplateResponse(
        request, name, {"csrf": request.session["csrf"], "running": lock is not None, "nav": request.url.path, **ctx}
    )


def flash(request: Request, message: str) -> None:
    request.session["flash"] = message


def audit(db: Session, user: User, action: str, **detail: Any) -> None:
    db.add(AuditLog(actor=user.email, action=action, detail=detail))


def create_app(start_scheduler: bool | None = None) -> FastAPI:
    settings = get_settings()
    scheduler_holder: dict[str, Any] = {}
    run_scheduler = settings.enable_scheduler if start_scheduler is None else start_scheduler

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if run_scheduler:
            from logidx.scheduler import Scheduler

            sched = Scheduler()
            sched.start()
            scheduler_holder["s"] = sched
        yield
        if "s" in scheduler_holder:
            scheduler_holder["s"].shutdown()

    app = FastAPI(title="LogiDx Executive Search", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    secret = settings.secret_key.get_secret_value()
    if not secret and settings.serverless:
        # Each serverless instance would invent its own key and sign users out at random.
        raise RuntimeError("LOGIDX_SECRET_KEY must be set when running serverless")
    if not secret:
        secret = secrets.token_urlsafe(48)
        log.warning("LOGIDX_SECRET_KEY not set: using a random key; sessions end when the server restarts")
    app.add_middleware(
        SessionMiddleware,
        secret_key=secret,
        session_cookie="logidx_session",
        https_only=settings.cookie_secure,
        same_site="strict",
        max_age=12 * 3600,
    )
    app.mount("/static", StaticFiles(directory=str(PACKAGE_ROOT / "web" / "static")), name="static")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        resp: Response = await call_next(request)
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; frame-ancestors 'none'; form-action 'self'"
        )
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["X-Frame-Options"] = "DENY"
        return resp

    @app.exception_handler(NotAuthenticated)
    async def _not_auth(request: Request, exc: NotAuthenticated) -> Response:
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "authentication required"}, status_code=401)
        return RedirectResponse("/login", status_code=303)

    # ------------------------------------------------------------------ auth
    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
        has_users = db.scalar(select(func.count(User.id))) > 0
        return render(request, "login.html", has_users=has_users)

    @app.post("/login", dependencies=[Depends(check_csrf)])
    def login(
        request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)
    ) -> Response:
        key = f"{request.client.host if request.client else '?'}:{email.lower()}"
        if not limiter.allowed(key):
            return render(request, "login.html", has_users=True, error="Too many attempts. Try again later.")
        user = db.scalar(select(User).where(User.email == email.lower().strip()))
        if user is None or not verify_password(password, user.password_hash):
            limiter.record_failure(key)
            db.add(AuditLog(actor=email[:320], action="login_failed", detail={}))
            db.commit()
            return render(request, "login.html", has_users=True, error="Email or password is incorrect.")
        limiter.reset(key)
        request.session.clear()
        request.session.update(uid=user.id, csrf=new_csrf_token())
        user.last_login_at = datetime.now(UTC)
        db.add(AuditLog(actor=user.email, action="login", detail={}))
        db.commit()
        return RedirectResponse("/", status_code=303)

    @app.post("/logout", dependencies=[Depends(check_csrf)])
    def logout(request: Request) -> Response:
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    # ------------------------------------------------------------------ overview
    @app.get("/", response_class=HTMLResponse)
    def overview(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> HTMLResponse:
        day = coverage.today_local()
        start, _ = coverage.day_bounds(day)
        active = Vacancy.lifecycle != Lifecycle.EXPIRED
        new_today = (
            db.scalar(
                select(func.count(Vacancy.id)).where(
                    Vacancy.first_discovered_at >= start, Vacancy.is_relevant.is_(True)
                )
            )
            or 0
        )
        priority = db.scalars(
            select(Vacancy)
            .where(active, Vacancy.fit_class == FitClass.PRIORITY, Vacancy.verification_status != Verification.CLOSED)
            .order_by(Vacancy.overall_fit.desc())
            .limit(8)
        ).all()
        top_unassessed = db.scalars(
            select(Vacancy)
            .where(active, Vacancy.is_relevant.is_(True), Vacancy.fit_class == FitClass.UNASSESSED)
            .order_by(Vacancy.prescore.desc(), Vacancy.first_discovered_at.desc())
            .limit(8)
        ).all()
        pipeline = {
            s: db.scalar(select(func.count(Vacancy.id)).where(Vacancy.application_status == s)) or 0 for s in PIPELINE
        }
        last_run = db.scalars(select(Run).order_by(Run.started_at.desc()).limit(1)).first()
        return render(
            request,
            "overview.html",
            user=user,
            new_today=new_today,
            priority=priority,
            top_unassessed=top_unassessed,
            pipeline=pipeline,
            last_run=last_run,
            sources=coverage.source_matrix(db, day),
            categories=coverage.category_matrix(db, day),
            relevant_total=db.scalar(select(func.count(Vacancy.id)).where(active, Vacancy.is_relevant.is_(True))),
        )

    # ------------------------------------------------------------------ vacancies
    def _filtered(db: Session, params: dict[str, str]) -> Any:
        stmt = select(Vacancy)
        if params.get("q"):
            like = f"%{params['q'].lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(Vacancy.title).like(like),
                    func.lower(Vacancy.employer).like(like),
                    func.lower(Vacancy.recruiting_agency).like(like),
                    func.lower(Vacancy.description).like(like),
                )
            )
        if params.get("category"):  # JSON list stored as text on SQLite, json on Postgres: compare as text
            stmt = stmt.where(cast(Vacancy.categories, String).like(f'%"{params["category"]}"%'))
        for field in ("fit_class", "verification_status", "geography", "application_status", "lifecycle"):
            if params.get(field):
                stmt = stmt.where(getattr(Vacancy, field) == params[field])
        if params.get("relevant", "1") == "1":
            stmt = stmt.where(Vacancy.is_relevant.is_(True))
        if not params.get("lifecycle") and params.get("include_expired") != "1":
            stmt = stmt.where(Vacancy.lifecycle != Lifecycle.EXPIRED)
        if params.get("workable") == "1":
            stmt = stmt.where(Vacancy.geography.in_([g.value for g in Geography if g.melbourne_workable]))
        order = params.get("sort", "fit")
        if order == "new":
            stmt = stmt.order_by(Vacancy.first_discovered_at.desc())
        elif order == "posted":
            stmt = stmt.order_by(Vacancy.posted_at.desc().nullslast())
        else:
            stmt = stmt.order_by(
                Vacancy.overall_fit.desc().nullslast(), Vacancy.prescore.desc(), Vacancy.first_discovered_at.desc()
            )
        return stmt

    @app.get("/jobs", response_class=HTMLResponse)
    def jobs(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> HTMLResponse:
        params = dict(request.query_params)
        page = max(1, int(params.get("page", "1") or 1))
        rows = db.scalars(_filtered(db, params).offset((page - 1) * 50).limit(51)).all()
        return render(
            request,
            "jobs.html",
            user=user,
            rows=rows[:50],
            has_more=len(rows) > 50,
            page=page,
            params=params,
            taxonomy=default_taxonomy(),
            geographies=list(Geography),
            title=params.get("title") or "Job discovery",
        )

    @app.get("/priority", response_class=HTMLResponse)
    def priority(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> HTMLResponse:
        rows = db.scalars(
            select(Vacancy).where(
                Vacancy.lifecycle != Lifecycle.EXPIRED,
                Vacancy.verification_status != Verification.CLOSED,
                or_(
                    Vacancy.fit_class.in_([FitClass.PRIORITY, FitClass.ADJACENT]),
                    (Vacancy.fit_class == FitClass.UNASSESSED)
                    & (Vacancy.is_relevant.is_(True))
                    & (Vacancy.prescore >= 6),
                ),
            )
        ).all()
        now = datetime.now(UTC)

        def urgency(v: Vacancy) -> tuple[float, ...]:
            fit = v.overall_fit if v.overall_fit is not None else v.prescore * 0.8
            conv = {"STRONG": 1.0, "COMPETITIVE": 0.6, "STRETCH": 0.2, "LONG_SHOT": 0.0}.get(
                v.conversion_assessment or "", 0.3
            )
            verified = {Verification.VERIFIED_OPEN: 1.0, Verification.LIKELY_OPEN: 0.6}.get(
                Verification(v.verification_status), 0.2
            )
            fresh = max(0.0, 1 - ((now - (v.posted_at or v.first_discovered_at)).days / 30))
            closing = 1.0 if v.closing_date and (v.closing_date - now.date()).days <= 7 else 0.0
            workable = 1.0 if Geography(v.geography).melbourne_workable else 0.0
            return (workable, fit + conv + verified + fresh + closing)

        rows = sorted(rows, key=urgency, reverse=True)
        return render(request, "priority.html", user=user, rows=rows)

    @app.get("/disciplines", response_class=HTMLResponse)
    def disciplines(
        request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)
    ) -> HTMLResponse:
        tax = default_taxonomy()
        active = db.scalars(
            select(Vacancy).where(Vacancy.lifecycle != Lifecycle.EXPIRED, Vacancy.is_relevant.is_(True))
        ).all()
        cards = []
        for key in tax.category_keys:
            in_cat = [v for v in active if key in (v.categories or [])]
            cards.append(
                {
                    "key": key,
                    "label": tax.category_label(key),
                    "count": len(in_cat),
                    "priority": sum(1 for v in in_cat if v.fit_class == FitClass.PRIORITY),
                    "verified": sum(1 for v in in_cat if v.verification_status == Verification.VERIFIED_OPEN),
                    "top": sorted(in_cat, key=lambda v: (v.overall_fit or 0, v.prescore), reverse=True)[:4],
                }
            )
        return render(
            request,
            "disciplines.html",
            user=user,
            cards=cards,
            categories=coverage.category_matrix(db, coverage.today_local()),
        )

    @app.get("/jobs/{vid}", response_class=HTMLResponse)
    def job_detail(
        vid: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)
    ) -> HTMLResponse:
        v = db.get(Vacancy, vid)
        if v is None:
            raise HTTPException(404)
        assessment = next((a for a in reversed(v.assessments) if a.valid), None)
        return render(
            request,
            "job.html",
            user=user,
            v=v,
            assessment=assessment,
            statuses=list(ApplicationStatus),
            taxonomy=default_taxonomy(),
            ai_available=get_provider() is not None,
        )

    @app.post("/jobs/{vid}/status", dependencies=[Depends(check_csrf)])
    def set_status(
        vid: int,
        request: Request,
        status: str = Form(...),
        note: str = Form(""),
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> Response:
        v = db.get(Vacancy, vid)
        if v is None or status not in {s.value for s in ApplicationStatus}:
            raise HTTPException(400)
        previous = v.application_status
        v.application_status = status
        if status == ApplicationStatus.APPLIED and not v.applied_at:
            v.applied_at = datetime.now(UTC)
        db.add(
            VacancyEvent(
                vacancy=v,
                kind="status_changed",
                actor=user.email,
                detail={"from": previous, "to": status, "note": note[:1000]},
            )
        )
        audit(db, user, "status_changed", vacancy_id=vid, to=status)
        db.commit()
        return RedirectResponse(f"/jobs/{vid}", status_code=303)

    @app.post("/jobs/{vid}/notes", dependencies=[Depends(check_csrf)])
    def set_notes(
        vid: int, notes: str = Form(""), user: User = Depends(current_user), db: Session = Depends(get_db)
    ) -> Response:
        v = db.get(Vacancy, vid)
        if v is None:
            raise HTTPException(404)
        v.notes = notes[:10000]
        db.add(VacancyEvent(vacancy=v, kind="notes_updated", actor=user.email, detail={}))
        db.commit()
        return RedirectResponse(f"/jobs/{vid}", status_code=303)

    @app.post("/jobs/{vid}/verify", dependencies=[Depends(check_csrf)])
    def reverify(
        vid: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)
    ) -> Response:
        v = db.get(Vacancy, vid)
        if v is None:
            raise HTTPException(404)
        http = HttpClient()
        try:
            status = verify_now(db, v, http, actor=user.email)
        finally:
            http.close()
        db.commit()
        flash(request, f"Verification: {status}")
        return RedirectResponse(f"/jobs/{vid}", status_code=303)

    @app.post("/jobs/{vid}/assess", dependencies=[Depends(check_csrf)])
    def assess(
        vid: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)
    ) -> Response:
        v = db.get(Vacancy, vid)
        provider = get_provider()
        if v is None:
            raise HTTPException(404)
        if provider is None:
            flash(request, "No AI provider configured (set XAI_API_KEY).")
        else:
            rec = assess_vacancy(db, v, provider)
            db.commit()
            flash(request, "Assessment complete." if rec.valid else f"Assessment failed: {rec.error}")
        return RedirectResponse(f"/jobs/{vid}", status_code=303)

    # ------------------------------------------------------------------ applications
    @app.get("/applications", response_class=HTMLResponse)
    def applications(
        request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)
    ) -> HTMLResponse:
        columns = {
            s: db.scalars(
                select(Vacancy).where(Vacancy.application_status == s).order_by(Vacancy.updated_at.desc())
            ).all()
            for s in PIPELINE
        }
        return render(request, "applications.html", user=user, columns=columns)

    # ------------------------------------------------------------------ recruiters
    @app.get("/recruiters", response_class=HTMLResponse)
    def recruiters(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> HTMLResponse:
        watch = {b.name: b for b in load_watchlist().boards if b.agency}
        for name in watch:
            if db.scalar(select(Agency).where(Agency.name == name)) is None:
                db.add(Agency(name=name, careers_source=f"{watch[name].ats}:{watch[name].key}"))
        db.commit()
        agencies = db.scalars(select(Agency).order_by(Agency.name)).all()
        counts = {
            a.id: db.scalar(
                select(func.count(Vacancy.id)).where(
                    Vacancy.recruiting_agency == a.name, Vacancy.lifecycle != Lifecycle.EXPIRED
                )
            )
            for a in agencies
        }
        return render(request, "recruiters.html", user=user, agencies=agencies, counts=counts, watch=watch)

    @app.post("/recruiters", dependencies=[Depends(check_csrf)])
    def add_recruiter(
        request: Request,
        agency_id: int = Form(...),
        name: str = Form(...),
        title: str = Form(""),
        specialty: str = Form(""),
        public_email: str = Form(""),
        public_phone: str = Form(""),
        profile_url: str = Form(""),
        contact_source: str = Form(...),
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> Response:
        if not contact_source.strip():
            raise HTTPException(400, "record where the public contact information was found")
        db.add(
            Recruiter(
                agency_id=agency_id,
                name=name[:200],
                title=title[:200] or None,
                specialty=specialty or None,
                public_email=public_email or None,
                public_phone=public_phone or None,
                profile_url=profile_url or None,
                contact_source=contact_source[:500],
                last_verified_at=datetime.now(UTC),
            )
        )
        audit(db, user, "recruiter_added", name=name)
        db.commit()
        return RedirectResponse("/recruiters", status_code=303)

    # ------------------------------------------------------------------ coverage, runs, recall
    @app.get("/coverage", response_class=HTMLResponse)
    def coverage_page(
        request: Request, day: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)
    ) -> HTMLResponse:
        d = date.fromisoformat(day) if day else coverage.today_local()
        return render(
            request,
            "coverage.html",
            user=user,
            day=d,
            prev=d - timedelta(days=1),
            next=d + timedelta(days=1),
            sources=coverage.source_matrix(db, d),
            categories=coverage.category_matrix(db, d),
            restricted=RESTRICTED,
        )

    @app.get("/runs", response_class=HTMLResponse)
    def runs(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> HTMLResponse:
        rows = db.scalars(select(Run).order_by(Run.started_at.desc()).limit(60)).all()
        from logidx.scheduler import next_fire_times

        upcoming = next_fire_times(get_schedule(db), datetime.now(UTC))
        return render(request, "runs.html", user=user, rows=rows, upcoming=upcoming)

    @app.get("/runs/{rid}", response_class=HTMLResponse)
    def run_detail(
        rid: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)
    ) -> HTMLResponse:
        run = db.get(Run, rid)
        if run is None:
            raise HTTPException(404)
        return render(request, "run.html", user=user, run=run, taxonomy=default_taxonomy())

    @app.post("/runs", dependencies=[Depends(check_csrf)])
    def run_now(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
        if holder_of(db, LOCK_NAME) is not None:
            flash(request, "A discovery run is already in progress.")
            return RedirectResponse("/runs", status_code=303)
        from logidx.service import execute

        email = user.email
        if settings.serverless:  # background threads do not outlive the request on serverless hosts
            run = execute(trigger="manual", actor=email)
            if run is None:
                flash(request, "Run not started (duplicate).")
                return RedirectResponse("/runs", status_code=303)
            flash(request, f"Run finished: {run.status}.")
            return RedirectResponse(f"/runs/{run.id}", status_code=303)
        threading.Thread(target=lambda: execute(trigger="manual", actor=email), daemon=True).start()
        flash(request, "Discovery run started. Refresh this page to follow progress.")
        return RedirectResponse("/runs", status_code=303)

    @app.get("/cron/run")
    def cron_run(request: Request, slot: str) -> Any:
        """Scheduled run for hosts without an in-process scheduler (Vercel Cron sends `Bearer CRON_SECRET`)."""
        expected = settings.cron_secret.get_secret_value()
        if not expected:
            raise HTTPException(503, "CRON_SECRET is not configured")
        if not csrf_matches(f"Bearer {expected}", request.headers.get("authorization")):
            raise HTTPException(401, "invalid cron credentials")
        try:
            ScheduleConfig(slots=[slot])
        except ValidationError as exc:
            raise HTTPException(400, "slot must be HH:MM") from exc
        from logidx.service import run_scheduled_slot

        run = run_scheduled_slot(slot)
        if run is None:
            return {"status": "duplicate", "detail": f"slot {slot} already ran today"}
        return {"status": run.status, "run_id": run.id, "error": run.error}

    @app.get("/recall", response_class=HTMLResponse)
    def recall_page(
        request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)
    ) -> HTMLResponse:
        recall.sync_cases(db)
        db.commit()
        cases = db.scalars(select(RecallCase).order_by(RecallCase.key)).all()
        return render(
            request,
            "recall.html",
            user=user,
            cases=cases,
            fixtures=recall.taxonomy_fixtures(),
            metrics=recall.metrics(db, datetime.now(UTC) - timedelta(days=2)),
        )

    @app.get("/report", response_class=HTMLResponse)
    def report_page(
        request: Request, day: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)
    ) -> HTMLResponse:
        daily = report.build(db, date.fromisoformat(day) if day else None)
        return render(request, "report.html", user=user, report=daily)

    # ------------------------------------------------------------------ import (browser-assisted discovery)
    @app.get("/import", response_class=HTMLResponse)
    def import_page(request: Request, user: User = Depends(current_user)) -> HTMLResponse:
        return render(request, "import.html", user=user)

    @app.post("/import", dependencies=[Depends(check_csrf)])
    def import_vacancy(
        request: Request,
        url: str = Form(...),
        title: str = Form(...),
        employer: str = Form(""),
        agency: str = Form(""),
        location: str = Form(""),
        description: str = Form(""),
        salary_text: str = Form(""),
        origin: str = Form("other"),
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> Response:
        if not url.startswith(("http://", "https://")):
            raise HTTPException(400, "URL must start with http(s)://")
        raw = RawVacancy(
            source="manual",
            source_job_id=hashlib.sha256(url.strip().encode()).hexdigest()[:24],
            title=title.strip()[:500],
            url=url.strip(),
            employer=employer or None,
            agency=agency or None,
            location=location or None,
            description=description[:50000],
            salary_text=salary_text or None,
            is_agency_listing=bool(agency) and not employer,
            raw={"origin": origin, "imported_by": user.email},
        )
        outcome = ingest(
            db, raw, run=None, access_method=AccessMethod.MANUAL, taxonomy=default_taxonomy(), profile=get_profile(db)
        )
        db.flush()
        from logidx.verification import update_verification

        update_verification(db, outcome.vacancy)
        audit(db, user, "vacancy_imported", vacancy_id=outcome.vacancy.id, origin=origin)
        db.commit()
        flash(
            request,
            "Imported." if outcome.is_new else f"Already known — merged ({outcome.merged_reason or 'same URL'}).",
        )
        return RedirectResponse(f"/jobs/{outcome.vacancy.id}", status_code=303)

    # ------------------------------------------------------------------ documents
    @app.get("/documents", response_class=HTMLResponse)
    def documents(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> HTMLResponse:
        docs = db.scalars(select(Document).order_by(Document.created_at.desc())).all()
        return render(request, "documents.html", user=user, docs=docs)

    @app.post("/documents/master-cv", dependencies=[Depends(check_csrf)])
    async def upload_cv(
        request: Request,
        file: UploadFile = File(...),
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> Response:
        data = await file.read(5 * 1024 * 1024 + 1)
        try:
            doc = import_master_cv(db, file.filename or "cv", data)
        except ValueError as exc:
            flash(request, f"Upload rejected: {exc}")
            return RedirectResponse("/documents", status_code=303)
        audit(db, user, "master_cv_imported", version=doc.version, sha256=doc.sha256)
        db.commit()
        flash(request, f"Master CV v{doc.version} imported — review the extracted text below.")
        return RedirectResponse("/documents", status_code=303)

    # ------------------------------------------------------------------ settings
    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(
        request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)
    ) -> HTMLResponse:
        s = get_settings()
        integrations = [
            ("xAI Grok", bool(s.xai_api_key.get_secret_value()), f"model {s.xai_model}"),
            ("Adzuna API", bool(s.adzuna_app_id.get_secret_value() and s.adzuna_app_key.get_secret_value()), ""),
            (
                "Google Programmable Search (indexed fallback)",
                bool(s.google_cse_key.get_secret_value() and s.google_cse_cx),
                "",
            ),
            ("SMTP email", bool(s.smtp_host and s.smtp_from and s.report_recipient), s.smtp_host or ""),
            ("Gmail (read-only OAuth)", False, "planned — Phase 4"),
        ]
        watch = load_watchlist()
        return render(
            request,
            "settings.html",
            user=user,
            profile_yaml=yaml.safe_dump(get_profile(db).model_dump(), sort_keys=False, allow_unicode=True, width=110),
            schedule=get_schedule(db),
            integrations=integrations,
            watch=watch,
            tz=s.timezone,
            config_dir=str(s.config_dir),
        )

    @app.post("/settings/profile", dependencies=[Depends(check_csrf)])
    def save_profile_route(
        request: Request,
        profile_yaml: str = Form(...),
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> Response:
        try:
            profile = CandidateProfile.model_validate(yaml.safe_load(profile_yaml) or {})
        except (yaml.YAMLError, ValidationError) as exc:
            flash(request, f"Profile not saved: {str(exc)[:400]}")
            return RedirectResponse("/settings", status_code=303)
        save_profile(db, profile)
        audit(db, user, "profile_updated")
        db.commit()
        flash(request, "Candidate profile saved. It applies from the next run.")
        return RedirectResponse("/settings", status_code=303)

    @app.post("/settings/schedule", dependencies=[Depends(check_csrf)])
    def save_schedule_route(
        request: Request,
        slots: str = Form(...),
        report_slot: str = Form(...),
        enabled: str = Form(""),
        ai_enabled: str = Form(""),
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> Response:
        try:
            cfg = ScheduleConfig(
                slots=[x.strip() for x in slots.split(",") if x.strip()],
                report_slot=report_slot,
                enabled=enabled == "on",
                ai_enabled=ai_enabled == "on",
            )
        except ValidationError as exc:
            flash(request, f"Schedule not saved: {exc.errors()[0]['msg']}")
            return RedirectResponse("/settings", status_code=303)
        save_schedule(db, cfg)
        audit(db, user, "schedule_updated", **cfg.model_dump())
        db.commit()
        if "s" in scheduler_holder:
            scheduler_holder["s"].reload()
        flash(request, "Schedule saved.")
        return RedirectResponse("/settings", status_code=303)

    # ------------------------------------------------------------------ JSON API
    def _vacancy_json(v: Vacancy, full: bool = False) -> dict[str, Any]:
        data = {
            k: getattr(v, k)
            for k in (
                "id",
                "title",
                "employer",
                "recruiting_agency",
                "is_confidential",
                "location_text",
                "geography",
                "work_mode",
                "salary_text",
                "salary_min",
                "salary_max",
                "primary_category",
                "categories",
                "verification_status",
                "fit_class",
                "overall_fit",
                "prescore",
                "application_status",
                "lifecycle",
                "advert_url",
                "application_url",
                "closing_date",
                "posted_at",
                "first_discovered_at",
                "last_seen_at",
            )
        }
        if full:
            data.update(
                description=v.description,
                verification_evidence=v.verification_evidence,
                knockouts=v.knockouts,
                ai_summary=v.ai_summary,
                fit_override_reason=v.fit_override_reason,
                sources=[
                    {
                        "source": s.source,
                        "board": s.board,
                        "id": s.source_job_id,
                        "url": s.url,
                        "present": s.present,
                        "last_seen_at": s.last_seen_at,
                    }
                    for s in v.sources
                ],
            )
        return data

    @app.get("/api/vacancies")
    def api_vacancies(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Any:
        params = dict(request.query_params)
        limit = min(500, int(params.get("limit", "100")))
        return [_vacancy_json(v) for v in db.scalars(_filtered(db, params).limit(limit)).all()]

    @app.get("/api/vacancies/{vid}")
    def api_vacancy(vid: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Any:
        v = db.get(Vacancy, vid)
        if v is None:
            raise HTTPException(404)
        return _vacancy_json(v, full=True)

    @app.get("/api/runs")
    def api_runs(user: User = Depends(current_user), db: Session = Depends(get_db)) -> Any:
        return [
            {
                "id": r.id,
                "trigger": r.trigger,
                "slot": r.slot,
                "status": r.status,
                "started_at": r.started_at,
                "finished_at": r.finished_at,
                "counts": r.counts,
                "error": r.error,
            }
            for r in db.scalars(select(Run).order_by(Run.started_at.desc()).limit(50)).all()
        ]

    @app.get("/api/coverage")
    def api_coverage(day: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Any:
        d = date.fromisoformat(day) if day else coverage.today_local()
        return {
            "day": d,
            "sources": [vars(r) | {"access_methods": sorted(r.access_methods)} for r in coverage.source_matrix(db, d)],
            "categories": [vars(c) for c in coverage.category_matrix(db, d)],
        }

    @app.get("/healthz")
    def healthz(db: Session = Depends(get_db)) -> Any:
        last = db.scalars(
            select(Run).where(Run.status != RunStatus.SKIPPED).order_by(Run.started_at.desc()).limit(1)
        ).first()
        return {"ok": True, "last_run": last.started_at if last else None, "last_status": last.status if last else None}

    return app
