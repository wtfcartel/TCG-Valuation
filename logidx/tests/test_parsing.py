"""Salary, location, normalisation, taxonomy and dedup — the deterministic core."""

import pytest

from logidx.enums import Geography, WorkMode
from logidx.pipeline.dedup import DedupCandidate, Incoming, match_reason
from logidx.pipeline.location import classify_location
from logidx.pipeline.normalize import canonical_url, extract_reference, html_to_text, norm_company, norm_title
from logidx.pipeline.salary import SUPER_GUARANTEE_RATE, parse_salary
from logidx.taxonomy import default_taxonomy


# ------------------------------------------------------------------ salary
@pytest.mark.parametrize(
    ("text", "lo", "hi", "period", "super_"),
    [
        ("$200,000 - $250,000 + super", 200_000, 250_000, "year", False),
        ("$220k–$260k package", 220_000, 260_000, "year", True),
        ("AUD 180K base plus super and bonus", 180_000, 180_000, "year", False),
        ("Package up to $300K TRP", 300_000, 300_000, "year", True),
        ("200-250k + super", 200_000, 250_000, "year", False),
        ("$1,200 per day", 1_200 * 220, 1_200 * 220, "day", None),
        ("$150 - $170 per hour", 150 * 1976, 170 * 1976, "hour", None),
    ],
)
def test_salary_formats(text, lo, hi, period, super_):
    s = parse_salary(text)
    assert (s.min_annual, s.max_annual, s.period, s.includes_super) == (lo, hi, period, super_)


def test_salary_package_base_estimate_removes_super():
    s = parse_salary("$336,000 total remuneration package")
    assert s.includes_super is True
    assert s.base_estimate_max == round(336_000 / (1 + SUPER_GUARANTEE_RATE))


def test_salary_ignores_revenue_figures_and_detects_benefits():
    s = parse_salary("Lead a $90m revenue business. Salary $250k + super, STI and LTI, novated vehicle.")
    assert s.max_annual == 250_000
    assert set(s.benefits) == {"STI / bonus", "LTI", "Vehicle"}


def test_salary_undisclosed():
    assert not parse_salary("Attractive executive package").disclosed
    assert not parse_salary(None).disclosed


# ------------------------------------------------------------------ location
@pytest.mark.parametrize(
    ("loc", "desc", "expected"),
    [
        ("Ingleburn, NSW", "", Geography.INTERSTATE),
        ("Ormond VIC 3204", "", Geography.MELBOURNE),
        ("Truganina, Melbourne", "", Geography.MELBOURNE),
        ("Geelong VIC", "", Geography.REGIONAL_VIC),
        ("Sydney or Melbourne", "", Geography.NATIONAL_MELBOURNE_OK),
        ("Sydney NSW", "Location is flexible across Australia.", Geography.NATIONAL_MELBOURNE_OK),
        ("Australia", "National role.", Geography.NATIONAL_UNCONFIRMED),
        ("Remote", "", Geography.REMOTE_AU),
        ("Auckland, New Zealand", "", Geography.OVERSEAS),
        ("Brisbane QLD", "", Geography.INTERSTATE),
        (None, "", Geography.UNKNOWN),
    ],
)
def test_geography(loc, desc, expected):
    assert classify_location(loc, desc).geography == expected


def test_national_title_does_not_imply_melbourne():
    r = classify_location("Sydney NSW", "National General Manager leading teams across Australia.")
    assert r.geography == Geography.INTERSTATE


def test_travel_and_work_mode():
    r = classify_location("Melbourne", "Hybrid working. Interstate travel required up to 30% of the time.")
    assert r.work_mode == WorkMode.HYBRID
    assert r.travel and "interstate travel" in r.travel.lower()


# ------------------------------------------------------------------ normalisation
def test_normalisation_helpers():
    assert norm_company("Linfox Australia Pty Ltd") == norm_company("LINFOX")
    assert norm_title("GM – Supply Chain & Logistics (Ref: 12345)") == "general manager supply chain and logistics"
    assert extract_reference("General Manager Supply Chain", "Reference: BH-31092. Apply now") == "BH-31092"
    assert canonical_url("https://Example.com/job/1/?utm_source=x&id=5") == "https://example.com/job/1?id=5"
    assert html_to_text("&lt;p&gt;One&lt;/p&gt;&lt;ul&gt;&lt;li&gt;Two&lt;/li&gt;&lt;/ul&gt;").split() == [
        "One",
        "•",
        "Two",
    ]


# ------------------------------------------------------------------ taxonomy
def test_spelling_variants_and_ampersand():
    tax = default_taxonomy()
    assert tax.classify("Head of Network Optimization").is_relevant  # US spelling of 'optimisation'
    assert "mna" in tax.classify("Director, Mergers & Acquisitions").categories
    assert "mna" in tax.classify("M & A Lead").categories


def test_lead_titles_need_scope():
    tax = default_taxonomy()
    assert tax.classify("Commercial Lead", "Reporting to the CEO, full P&L and EBITDA ownership.").is_relevant
    assert not tax.classify("Commercial Lead", "Answer inbound calls and process orders.").is_relevant


def test_excluded_titles_even_with_executive_words():
    tax = default_taxonomy()
    c = tax.classify("Executive Assistant to the CEO")
    assert c.seniority == "excluded" and not c.is_relevant


def test_cold_calling_penalised():
    tax = default_taxonomy()
    a = tax.classify("Head of Commercial", "Lead commercial strategy.")
    b = tax.classify("Head of Commercial", "Daily cold calling and call targets.")
    assert b.prescore < a.prescore


def test_query_rotation_covers_every_query_daily():
    tax = default_taxonomy()
    slots = 3
    for key, planned in tax.all_queries().items():
        ran: set[str] = set()
        for i in range(slots):
            ran |= set(tax.queries_for_run(i, slots)[key])
        assert ran == set(planned), key
        for i in range(slots):  # core queries every run
            assert set(tax.config.categories[key].core_queries) <= set(tax.queries_for_run(i, slots)[key])


def test_all_nine_categories_present():
    assert len(default_taxonomy().category_keys) == 9


def test_deterministic_knockouts():
    tax = default_taxonomy()
    ks = tax.deterministic_knockouts("A current NV1 security clearance is mandatory. CPA desirable.")
    kinds = {(k["category"], k["type"]) for k in ks}
    assert ("security_clearance", "ESSENTIAL") in kinds
    assert ("accounting_qualification", "UNCLEAR") in kinds


# ------------------------------------------------------------------ dedup
def _cand(**kw):
    base = dict(
        vacancy_id=1,
        norm_employer="acme",
        agency=None,
        normalized_title="general manager operations",
        location="Melbourne",
        description="Lead national operations " * 20,
        description_is_snippet=False,
        description_hash="h1",
        reference=None,
    )
    base.update(kw)
    return DedupCandidate(**base)


def _inc(**kw):
    base = dict(
        norm_employer="acme",
        agency=None,
        normalized_title="general manager operations",
        location="Melbourne",
        description="Lead national operations " * 20,
        description_is_snippet=False,
        description_hash="h2",
        reference=None,
    )
    base.update(kw)
    return Incoming(**base)


def test_dedup_same_reference():
    assert "reference" in match_reason(_inc(reference="R1", normalized_title="gm ops"), _cand(reference="R1"))


def test_dedup_does_not_merge_different_locations():
    assert match_reason(_inc(location="Sydney"), _cand(location="Melbourne")) is None


def test_dedup_does_not_merge_different_text():
    other = "Completely different role covering finance systems and payroll " * 10
    assert match_reason(_inc(description=other), _cand()) is None


def test_dedup_snippet_merges_on_title_employer_location():
    assert match_reason(_inc(description="Lead...", description_is_snippet=True), _cand()) is not None


def test_dedup_confidential_by_agency():
    assert (
        match_reason(
            _inc(norm_employer="", agency="Six Degrees Executive"),
            _cand(norm_employer="", agency="Six Degrees Executive"),
        )
        is not None
    )
    assert match_reason(_inc(norm_employer="", agency="Hays"), _cand(norm_employer="", agency="Six Degrees")) is None


def test_dedup_boilerplate_text_with_different_titles_stays_separate():
    same = dict(description="Standard company boilerplate " * 20, description_hash="same")
    assert (
        match_reason(
            _inc(normalized_title="head of operations", **same), _cand(normalized_title="head of logistics", **same)
        )
        is None
    )
