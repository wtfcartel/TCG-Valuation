"""Source registry: which adapters exist, which boards are configured, and the coverage-matrix targets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from logidx.settings import get_settings
from logidx.sources.adzuna import AdzunaSource
from logidx.sources.agencies import BullhornSource, GoogleIndexedSource, RssSource
from logidx.sources.ats import (
    GreenhouseSource,
    LeverSource,
    PageUpSource,
    SmartRecruitersSource,
    WorkdaySource,
)
from logidx.sources.base import BoardConfig, BoardSource, QuerySource, RestrictedSource

ALERT_EMAIL = "saved-search alert emails parsed from Gmail (read-only, Phase 4)"
MANUAL = "manual or browser-assisted import of a vacancy URL/text you are viewing (Import page)"

RESTRICTED: list[RestrictedSource] = [
    RestrictedSource(
        "seek",
        "SEEK Australia",
        "No public candidate search API; SEEK terms prohibit automated access to its site. Not contacted.",
        [ALERT_EMAIL, MANUAL],
    ),
    RestrictedSource(
        "linkedin",
        "LinkedIn Jobs",
        "No public job-search API for individuals; automated access prohibited by LinkedIn terms. "
        "Not contacted. Google-indexed results, if enabled, are reported separately.",
        [ALERT_EMAIL, MANUAL],
    ),
    RestrictedSource(
        "indeed",
        "Indeed Australia",
        "Indeed's Publisher job-search API is closed to new users; scraping is prohibited. Not contacted.",
        [ALERT_EMAIL, MANUAL],
    ),
    RestrictedSource(
        "google_jobs",
        "Google Jobs",
        "Google provides no public API for the Google Jobs search experience. Not contacted. "
        "Optional Programmable Search fallback is labelled INDEXED FALLBACK ONLY.",
        ["Google Programmable Search indexed fallback (GOOGLE_CSE_KEY)", MANUAL],
    ),
    RestrictedSource(
        "jora",
        "Jora Australia",
        "No public search API identified (Jora is SEEK-owned). Not contacted pending terms review.",
        [ALERT_EMAIL, MANUAL],
    ),
    RestrictedSource(
        "careerone",
        "CareerOne",
        "No public search API identified. Not contacted pending terms review.",
        [ALERT_EMAIL, MANUAL, "CareerOne listings are partly covered via Adzuna"],
    ),
    RestrictedSource(
        "workforce_australia",
        "Workforce Australia",
        "No documented public job-search API identified for individuals. Not contacted.",
        [MANUAL, "investigate data.gov.au / Department of Employment feeds"],
    ),
]

# Coverage-matrix rows required by the brief, in display order.
TARGET_GROUPS: list[tuple[str, str]] = [
    ("seek", "SEEK Australia"),
    ("google_jobs", "Google Jobs"),
    ("linkedin", "LinkedIn Jobs"),
    ("indeed", "Indeed Australia"),
    ("jora", "Jora Australia"),
    ("careerone", "CareerOne"),
    ("adzuna", "Adzuna Australia"),
    ("workforce_australia", "Workforce Australia"),
    ("ethicaljobs", "EthicalJobs"),
    ("probono", "Pro Bono Australia"),
    ("executive_search", "Executive search & recruitment sites"),
    ("employer_careers", "Employer careers / ATS"),
    ("google_indexed", "Google-indexed fallback"),
]


def query_sources() -> list[QuerySource]:
    return [AdzunaSource(), GoogleIndexedSource()]


def board_sources() -> dict[str, BoardSource]:
    sources: list[BoardSource] = [
        WorkdaySource(),
        SmartRecruitersSource(),
        GreenhouseSource(),
        LeverSource(),
        PageUpSource(),
        BullhornSource(),
        RssSource(),
    ]
    return {s.name: s for s in sources}


@dataclass
class Watchlist:
    boards: list[BoardConfig]

    def configured(self) -> list[BoardConfig]:
        return [b for b in self.boards if b.configured and b.ats in board_sources()]


def load_watchlist(path: Path | None = None) -> Watchlist:
    path = path or get_settings().config_dir / "watchlist.yaml"
    if not path.exists():
        return Watchlist([])
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return Watchlist([BoardConfig.model_validate(b) for b in data.get("boards", [])])
