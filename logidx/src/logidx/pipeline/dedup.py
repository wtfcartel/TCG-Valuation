"""Cross-source duplicate detection.

Order of evidence:
1. Same (source, source_job_id) — always the same vacancy (handled by the unique constraint).
2. Same advertiser reference number from the same employer/agency.
3. Same normalised employer (or agency, for confidential listings) + near-identical normalised title +
   compatible location, *and* — when both descriptions are full text — similar descriptions.

A wrong merge hides a vacancy, so the description check is deliberately conservative: two
different roles at one employer with the same title (e.g. GM Operations NSW vs GM Operations VIC)
stay separate unless their locations are compatible and their text agrees.
"""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

TITLE_THRESHOLD = 92
DESCRIPTION_THRESHOLD = 80


@dataclass
class DedupCandidate:
    vacancy_id: int
    norm_employer: str
    agency: str | None
    normalized_title: str
    location: str | None
    description: str
    description_is_snippet: bool
    description_hash: str
    reference: str | None


@dataclass
class Incoming:
    norm_employer: str
    agency: str | None
    normalized_title: str
    location: str | None
    description: str
    description_is_snippet: bool
    description_hash: str
    reference: str | None


def _loc_key(loc: str | None) -> str:
    return (loc or "").lower().split(",")[0].strip()


def _locations_compatible(a: str | None, b: str | None) -> bool:
    ka, kb = _loc_key(a), _loc_key(b)
    if not ka or not kb:
        return True
    return ka == kb or ka in kb or kb in ka or fuzz.ratio(ka, kb) >= 85


def match_reason(new: Incoming, old: DedupCandidate) -> str | None:
    """Why `new` is the same vacancy as `old`, or None."""
    same_party = (new.norm_employer and new.norm_employer == old.norm_employer) or (
        new.agency and old.agency and new.agency.lower() == old.agency.lower()
    )
    if not same_party:
        return None
    if new.reference and old.reference and new.reference == old.reference:
        return f"same advertiser reference {new.reference}"
    title_score = fuzz.token_sort_ratio(new.normalized_title, old.normalized_title)
    # Employers reuse boilerplate text across different roles, so identical text alone is not enough.
    if new.description_hash and new.description_hash == old.description_hash and title_score >= 80:
        return f"identical description, similar title ({title_score:.0f}%)"
    if title_score < TITLE_THRESHOLD or not _locations_compatible(new.location, old.location):
        return None
    if new.description_is_snippet or old.description_is_snippet or not new.description or not old.description:
        # Snippets cannot be compared reliably; title + employer + location agreement is enough.
        return f"same employer, title ({title_score:.0f}%) and location; description not comparable"
    desc_score = fuzz.token_set_ratio(new.description[:3000], old.description[:3000])
    if desc_score >= DESCRIPTION_THRESHOLD:
        return f"same employer, title ({title_score:.0f}%), location and description ({desc_score:.0f}%)"
    return None


def find_duplicate(new: Incoming, candidates: list[DedupCandidate]) -> tuple[int, str] | None:
    for cand in candidates:
        reason = match_reason(new, cand)
        if reason:
            return cand.vacancy_id, reason
    return None
