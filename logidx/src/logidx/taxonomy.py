"""Executive search taxonomy: loading, term matching, classification and daily query rotation.

The taxonomy lives in ``config/taxonomy.yaml`` so it can be audited and edited without code changes.
Classification here is deterministic and explainable; it decides which vacancies are worth an AI
assessment, it never decides eligibility on its own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

from logidx.settings import get_settings

# Families whose title match is generic (it says "senior", not "what function").
GENERIC_FAMILIES = {"A_general_management", "B_head_of_lead", "K_recruiter_terms"}


class Seniority(BaseModel):
    executive: list[str]
    senior: list[str]
    lead: list[str]
    prefixes: list[str]
    exclude: list[str]


class Family(BaseModel):
    label: str
    titles: list[str]
    responsibilities: list[str] = []


class Category(BaseModel):
    label: str
    families: list[str]
    title_terms: list[str] = []
    core_queries: list[str]
    rotating_queries: list[str] = []


class Knockouts(BaseModel):
    essential_markers: list[str]
    patterns: dict[str, list[str]]


class TaxonomyConfig(BaseModel):
    version: int
    seniority: Seniority
    scope_signals: list[str]
    negative_signals: dict[str, list[str]]
    knockouts: Knockouts
    families: dict[str, Family]
    categories: dict[str, Category]


def _word_variants(word: str) -> set[str]:
    """Australian ↔ US spelling variants for one word."""
    out = {word}
    for au, us in (("isation", "ization"), ("ising", "izing"), ("ised", "ized"), ("ise", "ize"), ("yse", "yze")):
        if word.endswith(au):
            out.add(word[: -len(au)] + us)
    if word.endswith("our") and len(word) > 4:
        out.add(word[:-3] + "or")
    if word.endswith("tre"):
        out.add(word[:-3] + "ter")
    return out


def _term_regex(term: str) -> str:
    """Regex for a term: whole-word, spelling variants, '&'≡'and', hyphen≡space, optional plural."""
    parts: list[str] = []
    for token in re.split(r"[\s\-]+", term.lower().strip()):
        if token in ("&", "and"):
            parts.append(r"(?:&|and)")
        elif "&" in token:  # m&a, p&l, 3pl-style abbreviations: allow spaces around '&'
            parts.append(r"\s*&\s*".join(re.escape(p) for p in token.split("&")))
        else:
            variants = sorted(_word_variants(token), key=len, reverse=True)
            parts.append("(?:" + "|".join(re.escape(v) for v in variants) + ")")
    body = r"[\s\-]+".join(parts)
    return rf"(?<![a-z0-9]){body}(?:s|es)?(?![a-z0-9])"


@dataclass(frozen=True)
class TermMatcher:
    terms: tuple[str, ...]
    pattern: re.Pattern[str]

    @classmethod
    def build(cls, terms: list[str]) -> TermMatcher:
        unique = dict.fromkeys(t.lower().strip() for t in terms if t.strip())
        # Longest first so overlapping alternatives prefer the longer, more specific term.
        ordered = tuple(sorted(unique, key=len, reverse=True))
        if not ordered:
            return cls(ordered, re.compile(r"(?!x)x"))
        named = "|".join(f"(?P<t{i}>{_term_regex(t)})" for i, t in enumerate(ordered))
        return cls(tuple(ordered), re.compile(named, re.IGNORECASE))

    def find(self, text: str) -> list[str]:
        """Distinct terms found in text (by canonical term)."""
        found: list[str] = []
        for m in self.pattern.finditer(text or ""):
            idx = int(m.lastgroup[1:]) if m.lastgroup else -1
            term = self.terms[idx]
            if term not in found:
                found.append(term)
        return found

    def count(self, text: str) -> int:
        return sum(1 for _ in self.pattern.finditer(text or ""))


@dataclass
class Classification:
    seniority: str  # executive | senior | lead_scoped | scope_inferred | lead | excluded | none
    seniority_terms: list[str]
    families: dict[str, list[str]]  # family -> title terms matched
    description_families: dict[str, int]  # family -> description hit count
    categories: dict[str, float]  # category -> score
    primary_category: str | None
    scope_signals: list[str]
    negative_signals: dict[str, list[str]]
    flags: list[str] = field(default_factory=list)
    prescore: float = 0.0
    is_relevant: bool = False


class Taxonomy:
    def __init__(self, config: TaxonomyConfig) -> None:
        self.config = config
        s = config.seniority
        self.executive = TermMatcher.build(s.executive)
        self.senior = TermMatcher.build(s.senior)
        self.lead = TermMatcher.build(s.lead)
        self.exclude = TermMatcher.build([t for t in s.exclude if t != "officer"])
        self.officer = TermMatcher.build(["officer"])
        self.scope = TermMatcher.build(config.scope_signals)
        self.negative = {k: TermMatcher.build(v) for k, v in config.negative_signals.items()}
        self.family_titles = {k: TermMatcher.build(f.titles) for k, f in config.families.items()}
        self.family_desc = {k: TermMatcher.build(f.titles + f.responsibilities) for k, f in config.families.items()}
        self.category_titles = {k: TermMatcher.build(c.title_terms) for k, c in config.categories.items()}
        self.knockout_patterns = {k: TermMatcher.build(v) for k, v in config.knockouts.patterns.items()}
        self.essential_markers = TermMatcher.build(config.knockouts.essential_markers)

    @property
    def category_keys(self) -> list[str]:
        return list(self.config.categories)

    def category_label(self, key: str | None) -> str:
        if key and key in self.config.categories:
            return self.config.categories[key].label
        return key or "—"

    # ------------------------------------------------------------------ queries
    def queries_for_run(self, slot_index: int, slots_per_day: int) -> dict[str, list[str]]:
        """Queries per category for one scheduled run.

        Every run executes each category's core queries; rotating queries are dealt across the day's
        slots (slot N takes items N, N+slots, ...), so over one day every query runs at least once.
        """
        slots = max(1, slots_per_day)
        idx = slot_index % slots
        out: dict[str, list[str]] = {}
        for key, cat in self.config.categories.items():
            rotating = cat.rotating_queries[idx::slots]
            out[key] = list(dict.fromkeys(cat.core_queries + rotating))
        return out

    def all_queries(self) -> dict[str, list[str]]:
        return {k: list(dict.fromkeys(c.core_queries + c.rotating_queries)) for k, c in self.config.categories.items()}

    # ------------------------------------------------------------- classification
    def classify(
        self, title: str, description: str = "", salary_max: float | None = None, salary_threshold: float = 160_000
    ) -> Classification:
        title_l = (title or "").lower()
        desc_l = (description or "").lower()

        exec_terms = self.executive.find(title_l)
        senior_terms = self.senior.find(title_l)
        lead_terms = self.lead.find(title_l)
        excluded = self.exclude.find(title_l)
        scope_hits = self.scope.find(desc_l)
        flags: list[str] = []

        if excluded:
            seniority, sen_terms = "excluded", excluded
        elif exec_terms:
            seniority, sen_terms = "executive", exec_terms
        elif senior_terms:
            seniority, sen_terms = "senior", senior_terms
        elif lead_terms:
            if len(scope_hits) >= 2:
                seniority, sen_terms = "lead_scoped", lead_terms
                flags.append("lead title promoted: executive scope signals in description")
            else:
                seniority, sen_terms = "lead", lead_terms
                flags.append("lead title: executive scope not evidenced — check authority, P&L, team size")
        elif self.officer.find(title_l):
            seniority, sen_terms = "excluded", ["officer"]
        elif len(scope_hits) >= 3:
            seniority, sen_terms = "scope_inferred", scope_hits[:3]
            flags.append("no senior title term; executive scope inferred from responsibilities")
        else:
            seniority, sen_terms = "none", []

        families = {k: m.find(title_l) for k, m in self.family_titles.items()}
        families = {k: v for k, v in families.items() if v}
        desc_families = {k: m.count(desc_l) for k, m in self.family_desc.items()}
        desc_families = {k: v for k, v in desc_families.items() if v}

        categories: dict[str, float] = {}
        for key, cat in self.config.categories.items():
            score = 0.0
            for fam in cat.families:
                if fam in families:
                    score += 3.0 if fam not in GENERIC_FAMILIES else 1.5
                score += min(desc_families.get(fam, 0), 6) * 0.25
            if self.category_titles[key].find(title_l):
                score += 2.0
            if score >= 0.75:
                categories[key] = round(score, 2)

        primary = None
        if categories:

            def rank(item: tuple[str, float]) -> tuple[float, int]:
                key, score = item
                specific = any(
                    f not in GENERIC_FAMILIES and f in families for f in self.config.categories[key].families
                )
                return (score + (1.0 if specific else 0.0), -self.category_keys.index(key))

            primary = max(categories.items(), key=rank)[0]

        negatives = {k: m.find(desc_l + " " + title_l) for k, m in self.negative.items()}
        negatives = {k: v for k, v in negatives.items() if v}

        salary_signal = salary_max is not None and salary_max >= salary_threshold
        functional_title = any(f not in GENERIC_FAMILIES for f in families)
        strong_desc_function = any(v >= 3 for k, v in desc_families.items() if k not in GENERIC_FAMILIES)

        relevant = False
        if seniority in ("executive", "senior", "lead_scoped"):
            relevant = bool(families) or strong_desc_function
        elif seniority == "scope_inferred":
            relevant = functional_title or strong_desc_function
        elif seniority == "lead":
            # No scope evidence: keep only while there is no description to judge it by.
            relevant = functional_title and not negatives and not desc_l.strip()
        elif seniority == "none" and salary_signal and (functional_title or strong_desc_function):
            relevant = True
            flags.append("no senior title term, but advertised salary meets the discovery threshold")
        if seniority == "excluded":
            flags.append(f"junior/support title term: {', '.join(sen_terms)}")
        if relevant and not primary:
            relevant = False

        score = {
            "executive": 4.0,
            "senior": 3.0,
            "lead_scoped": 2.5,
            "scope_inferred": 2.0,
            "lead": 1.0,
            "none": 0.0,
            "excluded": 0.0,
        }[seniority]
        score += min(sum(3 if f not in GENERIC_FAMILIES else 1 for f in families), 3)
        score += min(len(scope_hits) * 0.5, 2.0)
        if salary_max is not None:
            if salary_max >= 200_000:
                score += 1.0
            elif salary_max < salary_threshold:
                score -= 2.0
                flags.append("advertised salary below discovery threshold")
        for kind, hits in negatives.items():
            score -= 1.5
            flags.append(f"{kind.replace('_', ' ')} signals: {', '.join(hits[:3])}")

        return Classification(
            seniority=seniority,
            seniority_terms=sen_terms,
            families=families,
            description_families=desc_families,
            categories=categories,
            primary_category=primary,
            scope_signals=scope_hits,
            negative_signals=negatives,
            flags=flags,
            prescore=round(max(0.0, min(10.0, score)), 2),
            is_relevant=relevant,
        )

    def deterministic_knockouts(self, description: str) -> list[dict[str, str]]:
        """Credential requirements found in the text. 'essential' if a marker is in the same sentence."""
        out: list[dict[str, str]] = []
        for sentence in re.split(r"(?<=[.!?;\n•])\s+", description or ""):
            low = sentence.lower()
            for kind, matcher in self.knockout_patterns.items():
                for term in matcher.find(low):
                    essential = bool(self.essential_markers.find(low))
                    if not any(k["category"] == kind and k["term"] == term for k in out):
                        out.append(
                            {
                                "category": kind,
                                "term": term,
                                "type": "ESSENTIAL" if essential else "UNCLEAR",
                                "evidence": sentence.strip()[:300],
                            }
                        )
        return out


def load_taxonomy(path: Path | None = None) -> Taxonomy:
    path = path or get_settings().config_dir / "taxonomy.yaml"
    with path.open(encoding="utf-8") as fh:
        return Taxonomy(TaxonomyConfig.model_validate(yaml.safe_load(fh)))


@lru_cache
def default_taxonomy() -> Taxonomy:
    return load_taxonomy()
