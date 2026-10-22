"""Salary text parsing for Australian advertisements. Deterministic — the AI layer never sets salary.

Outputs annual AUD figures. Day and hourly rates are annualised and marked as estimates.
Superannuation: "+ super" means the figure is base; "package", "TRP", "TFR" or "incl. super" means
it includes super, so the base is estimated by removing the Superannuation Guarantee rate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SUPER_GUARANTEE_RATE = 0.12  # SG rate from 1 July 2025
HOURS_PER_YEAR = 38 * 52  # full-time award hours
CONTRACT_DAYS_PER_YEAR = 220

_AMOUNT = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*([kKmM](?![a-zA-Z]))?"
_CURRENCY = r"(?:aud|au\$|a\$|\$)"
_MONEY = re.compile(rf"{_CURRENCY}\s*{_AMOUNT}|(?<![\w$.])(\d{{2,3}}(?:\.\d+)?)\s*([kK])(?![a-zA-Z])", re.IGNORECASE)
_BARE_K_RANGE = re.compile(r"(?<![\w$.,])(\d{2,3})\s*(?:-|–|—|to)\s*\$?(\d{2,3})\s*[kK](?![a-zA-Z])")
_RANGE_SEP = re.compile(r"^\s*(?:-|–|—|to|and)\s*$", re.IGNORECASE)

_PERIODS = [
    ("hour", re.compile(r"per\s*hour|/\s*h(ou)?r|p/?h\b|hourly|ph\b", re.IGNORECASE)),
    ("day", re.compile(r"per\s*day|/\s*day|p/?d\b|daily|day\s*rate", re.IGNORECASE)),
    ("year", re.compile(r"per\s*annum|p\.?\s?a\.?\b|annual|per\s*year|/\s*y(ea)?r|package|base", re.IGNORECASE)),
]
_PLUS_SUPER = re.compile(r"(\+|plus|excl(?:uding|\.)?|exclusive of)\s*(super|superannuation)", re.IGNORECASE)
_INC_SUPER = re.compile(
    r"(inc(?:l?\.?|luding|lusive of)?\s*(super|superannuation))|\btrp\b|\btfr\b|total\s+(fixed\s+)?remuneration|"
    r"\bpackage\b|\bpkg\b|\btec\b|total employment cost",
    re.IGNORECASE,
)
_BENEFITS = {
    "STI / bonus": re.compile(r"\bsti\b|bonus|short[\s-]term incentive|incentive plan", re.IGNORECASE),
    "LTI": re.compile(r"\blti\b|long[\s-]term incentive", re.IGNORECASE),
    "Equity": re.compile(r"equity|shares|share scheme|options\b", re.IGNORECASE),
    "Vehicle": re.compile(r"vehicle|car allowance|novated|fully maintained car", re.IGNORECASE),
}


@dataclass
class SalaryInfo:
    text: str | None = None
    min_annual: float | None = None
    max_annual: float | None = None
    period: str | None = None
    includes_super: bool | None = None
    estimated: bool = False
    base_estimate_max: float | None = None
    benefits: list[str] = field(default_factory=list)
    currency: str | None = None

    @property
    def disclosed(self) -> bool:
        return self.max_annual is not None


def _to_number(num: str, suffix: str | None) -> float:
    value = float(num.replace(",", ""))
    if suffix and suffix.lower() == "k":
        value *= 1_000
    elif suffix and suffix.lower() == "m":
        value *= 1_000_000
    return value


def _period_for(text: str, amount: float) -> tuple[str, bool]:
    for name, rx in _PERIODS:
        if rx.search(text):
            return name, name != "year"
    if amount >= 20_000:
        return "year", False
    if amount <= 300:
        return "hour", True
    return "day", True


def _annualise(amount: float, period: str) -> float:
    return {"hour": amount * HOURS_PER_YEAR, "day": amount * CONTRACT_DAYS_PER_YEAR}.get(period, amount)


def parse_salary(text: str | None) -> SalaryInfo:
    info = SalaryInfo(text=(text or "").strip() or None)
    if not text:
        return info
    info.benefits = [name for name, rx in _BENEFITS.items() if rx.search(text)]

    bare = _BARE_K_RANGE.search(text)
    if bare:  # "200-250k": the first figure carries no $ or k
        info.min_annual, info.max_annual = sorted((float(bare.group(1)) * 1_000, float(bare.group(2)) * 1_000))
        info.period, info.estimated, info.currency = "year", False, "AUD"
        return _finish(info, text)
    matches = list(_MONEY.finditer(text))
    amounts: list[tuple[float, int, int]] = []
    for m in matches:
        if m.group(1) is not None:
            amounts.append((_to_number(m.group(1), m.group(2)), m.start(), m.end()))
        else:
            amounts.append((_to_number(m.group(3), m.group(4)), m.start(), m.end()))
    # Ignore implausible figures (e.g. "$5m revenue" next to a salary) — keep 15/hr .. 3M/yr.
    amounts = [a for a in amounts if 15 <= a[0] <= 3_000_000 and not _is_revenue_context(text, a)]
    if not amounts:
        return info

    low = high = amounts[0][0]
    if len(amounts) >= 2 and _RANGE_SEP.match(text[amounts[0][2] : amounts[1][1]]):
        low, high = sorted((amounts[0][0], amounts[1][0]))
    # "200-250k": first number written without its k suffix.
    if low < 1_000 <= high and low * 1_000 <= high * 1.5:
        low *= 1_000

    period, estimated = _period_for(text, high)
    info.period, info.estimated, info.currency = period, estimated, "AUD"
    info.min_annual, info.max_annual = _annualise(low, period), _annualise(high, period)

    return _finish(info, text)


def _finish(info: SalaryInfo, text: str) -> SalaryInfo:
    if _PLUS_SUPER.search(text):
        info.includes_super = False
    elif _INC_SUPER.search(text):
        info.includes_super = True
    base = info.max_annual or 0.0
    if info.includes_super:
        base = base / (1 + SUPER_GUARANTEE_RATE)
    info.base_estimate_max = round(base, 0)
    return info


def _is_revenue_context(text: str, amount: tuple[float, int, int]) -> bool:
    """'$90m revenue', 'turnover of $40m', 'budget of $2m' describe the business, not the pay."""
    after = text[amount[2] : amount[2] + 15].lower()
    before = text[max(0, amount[1] - 14) : amount[1]].lower()
    return any(w in after for w in ("revenue", "turnover", "budget", "business", "p&l", "ebitda")) or any(
        w in before for w in ("revenue of", "turnover of", "budget of", "p&l of", "worth")
    )


def from_structured(
    min_value: float | None, max_value: float | None, *, predicted: bool = False, text: str | None = None
) -> SalaryInfo:
    """Structured salary fields from an API. Predicted salaries (e.g. Adzuna estimates) are discarded."""
    if text:
        parsed = parse_salary(text)
        if parsed.disclosed:
            return parsed
    if predicted or (min_value is None and max_value is None):
        return SalaryInfo(text=text)
    low = min_value if min_value is not None else max_value
    high = max_value if max_value is not None else min_value
    assert low is not None and high is not None
    period, estimated = _period_for(text or "", high)
    return SalaryInfo(
        text=text or f"${low:,.0f} – ${high:,.0f}",
        min_annual=_annualise(low, period),
        max_annual=_annualise(high, period),
        period=period,
        estimated=estimated,
        base_estimate_max=_annualise(high, period),
        currency="AUD",
    )
