"""AI assessment: schema validation, deterministic scoring and overrides, provider wire format (mocked)."""

import json

import httpx
import pytest
import respx
from pydantic import SecretStr

from logidx.ai.evaluate import assess_pending, assess_vacancy, fit_class_for
from logidx.ai.provider import GrokProvider, ProviderError, StaticProvider
from logidx.ai.schemas import json_schema
from logidx.enums import AccessMethod, FitClass
from logidx.models import Assessment, Vacancy
from logidx.pipeline.ingest import ingest
from logidx.profile import seed_profile
from logidx.settings import Settings
from logidx.sources.base import RawVacancy
from logidx.taxonomy import default_taxonomy
from tests.payloads import assessment_json


def make_vacancy(session, description="Reporting to the CEO, lead national operations with full P&L.", title=None):
    raw = RawVacancy(
        source="t",
        source_job_id=title or "1",
        title=title or "Executive General Manager Operations",
        url="https://x/1",
        employer="Southern Freight (Fixture)",
        location="Melbourne VIC",
        description=description,
    )
    v = ingest(
        session, raw, run=None, access_method=AccessMethod.NATIVE, taxonomy=default_taxonomy(), profile=seed_profile()
    ).vacancy
    session.flush()
    return v


def static(payload):
    return StaticProvider(lambda _s, _u: json.dumps(payload) if not isinstance(payload, str) else payload)


@pytest.mark.parametrize(
    ("score", "cls"),
    [
        (9.2, FitClass.PRIORITY),
        (8.5, FitClass.PRIORITY),
        (8.49, FitClass.ADJACENT),
        (7.0, FitClass.ADJACENT),
        (6.5, FitClass.EXPLORATORY),
        (5.9, FitClass.LOW),
    ],
)
def test_fit_thresholds(score, cls):
    assert fit_class_for(score) == cls


def test_valid_assessment_updates_vacancy(session):
    v = make_vacancy(session)
    rec = assess_vacancy(session, v, static(assessment_json()))
    assert rec.valid and v.fit_class == FitClass.PRIORITY
    assert v.overall_fit == pytest.approx(9.0 * 0.3 + 8.8 * 0.25 + 8.6 * 0.15 + 8.5 * 0.1 + 8.9 * 0.2, abs=0.01)
    assert v.conversion_assessment == "STRONG" and v.assessed_description_hash == v.description_hash


def test_invalid_json_is_recorded_and_changes_nothing(session):
    v = make_vacancy(session)
    rec = assess_vacancy(session, v, static("not json"))
    assert not rec.valid and "invalid model output" in rec.error and v.fit_class == FitClass.UNASSESSED


def test_schema_violation_rejected(session):
    v = make_vacancy(session)
    bad = assessment_json(capability_fit={"score": 14, "rationale": "too high a score"})
    assert not assess_vacancy(session, v, static(bad)).valid and v.overall_fit is None


def test_invented_evidence_ids_rejected(session):
    v = make_vacancy(session)
    bad = assessment_json(
        requirements=[
            {
                "requirement": "Board experience",
                "importance": "ESSENTIAL",
                "support": "STRONG",
                "evidence_ids": ["E99"],
                "note": "",
            }
        ]
    )
    rec = assess_vacancy(session, v, static(bad))
    assert not rec.valid and "E99" in rec.error


def test_knockout_quote_must_appear_in_ad(session):
    v = make_vacancy(session)
    out = assessment_json(
        knockouts=[
            {
                "requirement": "Chartered engineer",
                "category": "engineering_qualification",
                "importance": "ESSENTIAL",
                "candidate_meets": "NO",
                "quote": "must be a chartered engineer",
            }
        ]
    )
    rec = assess_vacancy(session, v, static(out))
    assert rec.valid and not v.knockout_blocked  # quote invented → dropped
    assert "dropped knockout" in rec.derived["validation_notes"][0]


def test_unmet_essential_knockout_caps_to_low(session):
    v = make_vacancy(session, "Lead the operations team. Registered professional engineer (RPEQ) is mandatory.")
    out = assessment_json(
        knockouts=[
            {
                "requirement": "RPEQ registration",
                "category": "professional_registration",
                "importance": "ESSENTIAL",
                "candidate_meets": "NO",
                "quote": "Registered professional engineer (RPEQ) is mandatory",
            }
        ]
    )
    assess_vacancy(session, v, static(out))
    assert v.knockout_blocked and v.fit_class == FitClass.LOW and v.overall_fit <= 5.9


def test_pattern_knockout_added_when_model_misses_it(session):
    v = make_vacancy(session, "Lead national operations. A current NV1 security clearance is mandatory.")
    assess_vacancy(session, v, static(assessment_json()))
    assert any(k["origin"] == "pattern" and k["category"] == "security_clearance" for k in v.knockouts)
    assert "check essential requirement" in v.fit_override_reason


def test_conversion_override(session):
    v = make_vacancy(session)
    out = assessment_json(
        conversion={
            "assessment": "STRETCH",
            "rationale": "Lacks direct FMCG category experience.",
            "screening_risks": ["no FMCG"],
        }
    )
    assess_vacancy(session, v, static(out))
    assert v.fit_class == FitClass.ADJACENT and "conversion override" in v.fit_override_reason


def test_specialist_and_scope_caps(session):
    v = make_vacancy(session)
    assess_vacancy(session, v, static(assessment_json(specialist_role=True)))
    assert v.fit_class == FitClass.EXPLORATORY
    v2 = make_vacancy(session, title="Operations Lead")
    assess_vacancy(
        session,
        v2,
        static(assessment_json(seniority={"is_executive_scope": False, "rationale": "Team-level role without P&L."})),
    )
    assert v2.fit_class == FitClass.EXPLORATORY


def test_budget_stops_assessment(session):
    for i in range(3):
        make_vacancy(session, title=f"General Manager Logistics {i}")
    session.commit()
    settings = Settings(LOGIDX_AI_DAILY_BUDGET_USD=0.0)
    result = assess_pending(session, static(assessment_json()), settings=settings)
    assert result["assessed"] == 0 and "budget" in result["stopped"]


def test_pending_skips_already_assessed(session):
    make_vacancy(session)
    session.commit()
    first = assess_pending(session, static(assessment_json()))
    second = assess_pending(session, static(assessment_json()))
    assert first["assessed"] == 1 and second["assessed"] == 0
    assert session.query(Assessment).count() == 1


def test_provider_schema_is_strict():
    schema = json_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert all(d.get("additionalProperties") is False for d in schema["$defs"].values())
    assert "maxLength" not in json.dumps(schema)


@respx.mock
def test_grok_request_shape_and_usage():
    route = respx.post("https://api.x.ai/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "grok-4",
                "choices": [{"message": {"content": json.dumps(assessment_json())}}],
                "usage": {"prompt_tokens": 1200, "completion_tokens": 400},
            },
        )
    )
    p = GrokProvider(Settings(XAI_API_KEY=SecretStr("xai-test")), sleep=lambda _s: None)
    res = p.complete_json("sys", "user", "executive_vacancy_assessment", json_schema())
    body = json.loads(route.calls[0].request.content)
    assert route.calls[0].request.headers["Authorization"] == "Bearer xai-test"
    assert body["response_format"]["type"] == "json_schema" and body["response_format"]["json_schema"]["strict"]
    assert (res.tokens_in, res.tokens_out) == (1200, 400)


@respx.mock
def test_grok_auth_failure_and_retry():
    respx.post("https://api.x.ai/v1/chat/completions").mock(return_value=httpx.Response(401, json={"error": "bad"}))
    p = GrokProvider(Settings(XAI_API_KEY=SecretStr("xai-test")), sleep=lambda _s: None)
    with pytest.raises(ProviderError, match="rejected"):
        p.complete_json("s", "u", "n", {})


@respx.mock
def test_grok_retries_on_429():
    route = respx.post("https://api.x.ai/v1/chat/completions").mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}], "usage": {}}),
        ]
    )
    p = GrokProvider(Settings(XAI_API_KEY=SecretStr("xai-test")), sleep=lambda _s: None)
    assert p.complete_json("s", "u", "n", {}).text == "{}" and route.call_count == 2


def test_grok_requires_key():
    with pytest.raises(ProviderError):
        GrokProvider(Settings(XAI_API_KEY=SecretStr("")))


def test_prompt_contains_only_profile_evidence_and_facts(session):
    captured = {}

    def respond(system, user):
        captured["user"], captured["system"] = user, system
        return json.dumps(assessment_json())

    v = make_vacancy(session)
    assess_vacancy(session, v, StaticProvider(respond))
    assert "deterministic_facts" in captured["user"] and '"E10"' in captured["user"]
    assert "Never invent" in captured["system"]
    assert isinstance(session.get(Vacancy, v.id).ai_summary, str)
