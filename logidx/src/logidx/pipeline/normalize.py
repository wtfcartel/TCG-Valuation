"""Text normalisation shared by adapters, dedup and classification."""

from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from datetime import UTC, date, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

_COMPANY_SUFFIXES = re.compile(
    r"\b(pty\.?|ltd\.?|limited|proprietary|inc\.?|incorporated|llc|plc|group|holdings|australia|"
    r"aust\.?|anz|corporation|corp\.?|co\.?|the)\b",
    re.IGNORECASE,
)
_TITLE_NOISE = re.compile(
    r"\(([^)]*\b(ref|job|id|req)\b[^)]*)\)|\b(ref|reference|job\s*id|req(uisition)?\s*(id)?)\s*[:#]?\s*[\w-]+|"
    r"[|·•]+.*$|\s+-\s+(melbourne|sydney|brisbane|perth|adelaide|victoria|vic|nsw|qld)\b.*$",
    re.IGNORECASE,
)
_ABBREVIATIONS = {
    r"\bgm\b": "general manager",
    r"\begm\b": "executive general manager",
    r"\bmd\b": "managing director",
    r"\bceo\b": "chief executive officer",
    r"\bcoo\b": "chief operating officer",
    r"\bcco\b": "chief commercial officer",
    r"\bsnr\b": "senior",
    r"\bmgr\b": "manager",
    r"\bhd\b": "head",
    r"\bops\b": "operations",
    r"\bm\s*&\s*a\b": "mergers and acquisitions",
    r"&": " and ",
    r"\bnat\.?\b": "national",
}
_REFERENCE = re.compile(
    r"(?:\bref(?:erence)?(?:\s*(?:no\.?|number|#))?\s*[:#]?\s*|\bjob\s*(?:id|no\.?|number|ref)\s*[:#]?\s*)"
    r"([A-Z]{0,4}-?\d{3,}[A-Z0-9-]*)",
    re.IGNORECASE,
)
_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
    "src",
    "source",
    "ref",
    "trk",
    "trackingid",
    "refid",
}


def fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def html_to_text(raw: str | None) -> str:
    if not raw:
        return ""
    if "<" not in raw and "&" not in raw:
        return raw.strip()
    soup = BeautifulSoup(html.unescape(raw) if "&lt;" in raw else raw, "html.parser")
    for br in soup.find_all(["br"]):
        br.replace_with("\n")
    for block in soup.find_all(["p", "li", "div", "h1", "h2", "h3", "h4", "tr"]):
        block.insert_after("\n")
    for li in soup.find_all("li"):
        li.insert_before("• ")
    text = soup.get_text()
    text = re.sub(r"[ \t\xa0]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def norm_company(name: str | None) -> str:
    if not name:
        return ""
    s = fold(name).lower()
    s = _COMPANY_SUFFIXES.sub(" ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_title(title: str) -> str:
    s = fold(title).lower()
    s = _TITLE_NOISE.sub(" ", s)
    for pattern, repl in _ABBREVIATIONS.items():
        s = re.sub(pattern, repl, s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def clean_title(title: str) -> str:
    return re.sub(r"\s+", " ", (title or "").strip())


def description_hash(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "", fold(text or "").lower())
    return hashlib.sha256(s.encode()).hexdigest() if s else ""


def extract_reference(*texts: str | None) -> str | None:
    for text in texts:
        if not text:
            continue
        m = _REFERENCE.search(text)
        if m:
            return m.group(1).upper()
    return None


def canonical_url(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in _TRACKING_PARAMS]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or "/", urlencode(query), ""))


def parse_datetime(value: object) -> datetime | None:
    """ISO strings, epoch milliseconds or dates → aware UTC datetime."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if isinstance(value, int | float):
        seconds = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(seconds, tz=UTC)
    text = str(value).strip()
    if text.isdigit():
        return parse_datetime(int(text))
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
