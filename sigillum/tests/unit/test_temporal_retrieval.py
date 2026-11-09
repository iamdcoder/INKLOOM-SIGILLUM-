from copy import deepcopy
from datetime import datetime
from pathlib import Path

from sigillum.modules.knowledge.brand_pack import BrandPack
from sigillum.modules.retrieval.evidence import retrieve_fact_candidates
from sigillum.modules.retrieval.temporal import assess_temporality
from sigillum.modules.verification.engine import VerificationEngine

PACK = BrandPack(Path(__file__).parents[2] / "fixtures" / "brand_pack" / "v1")
PUBLICATION = datetime.fromisoformat("2026-11-08T12:00:00+05:30")
AS_OF = datetime.fromisoformat("2026-11-08T12:05:00+05:30")
CONTEXT = {
    "brand_id": "brand_orbita_demo",
    "offer_id": "OFFER-ORBITA-OCT-NOV-2026",
    "geography": "IN",
    "channel": "direct_web",
    "locale": "en-IN",
    "audience": "consumer",
}


def test_temporal_assessment_checks_valid_time_and_record_time_separately():
    fact = {
        "valid_from": "2026-10-01T00:00:00+05:30",
        "valid_until": "2026-11-30T23:59:59+05:30",
        "recorded_at": "2026-09-25T10:00:00+05:30",
    }
    assessment = assess_temporality(fact, PUBLICATION, AS_OF)
    assert assessment.eligible is True
    assert assessment.valid_state == "CURRENT"
    assert assessment.record_state == "RECORDED_AT_REVIEW"


def test_fact_recorded_after_review_as_of_is_not_eligible():
    fact = {
        "valid_from": "2026-10-01T00:00:00+05:30",
        "valid_until": "2026-11-30T23:59:59+05:30",
        "recorded_at": "2026-09-25T10:00:00+05:30",
    }
    review_as_of = datetime.fromisoformat("2026-09-24T10:00:00+05:30")
    assessment = assess_temporality(fact, PUBLICATION, review_as_of)
    assert assessment.eligible is False
    assert assessment.record_state == "NOT_YET_RECORDED"
    assert assessment.reason_code == "FACT_NOT_RECORDED_AT_REVIEW_TIME"


def test_fact_no_longer_recorded_at_review_is_not_eligible():
    fact = {
        "valid_from": "2026-10-01T00:00:00+05:30",
        "valid_until": "2026-11-30T23:59:59+05:30",
        "recorded_at": "2026-09-25T10:00:00+05:30",
        "recorded_until": "2026-11-01T00:00:00+05:30",
    }
    assessment = assess_temporality(fact, PUBLICATION, AS_OF)
    assert assessment.eligible is False
    assert assessment.record_state == "NO_LONGER_RECORDED"
    assert assessment.reason_code == "FACT_NO_LONGER_RECORDED_AT_REVIEW_TIME"


def test_invalid_temporal_interval_fails_closed():
    fact = {
        "valid_from": "2026-11-10T00:00:00+05:30",
        "valid_until": "2026-11-01T00:00:00+05:30",
    }
    assessment = assess_temporality(fact, PUBLICATION, AS_OF)
    assert assessment.eligible is False
    assert assessment.reason_code == "INVALID_VALIDITY_INTERVAL"


def test_retrieval_applies_scope_and_returns_reproducible_rrf_trace():
    result = retrieve_fact_candidates(
        PACK.facts,
        "Saves up to 28% on ORBITA Air One",
        CONTEXT,
        PUBLICATION,
        AS_OF,
        predicate="maximum_saving",
        unit="%",
    )
    candidates = result["candidates"]
    assert candidates
    assert candidates[0]["record"]["fact_id"] == "FACT-ORBITA-OFFER-001"
    assert candidates[0]["eligible"] is True
    assert candidates[0]["lexical_rank"] >= 1
    assert candidates[0]["structured_rank"] >= 1
    assert candidates[0]["rrf_score"] > 0
    assert candidates[0]["retrieval_method"] == "lexical+structured_rrf"
    assert result["trace"]["vector_search"] == "NOT_CONFIGURED"
    assert result["trace"]["scope_fields"] == ["offer_id", "geography", "channel", "locale", "audience"]
    assert result["trace"]["excluded_counts"]["scope_mismatch"] > 0


def test_retrieval_excludes_unapproved_and_unknown_scope_facts():
    facts = deepcopy(PACK.facts)
    facts.append({
        "fact_id": "DRAFT-FACT", "status": "draft", "predicate": "maximum_saving", "unit": "%",
        "subject": "ORBITA Air One", "value": 99, "offer_id": CONTEXT["offer_id"],
    })
    facts.append({
        "fact_id": "MISSING-SCOPE", "status": "approved", "predicate": "maximum_saving", "unit": "%",
        "subject": "ORBITA Air One", "value": 99, "offer_id": CONTEXT["offer_id"],
        "geography": "IN", "channel": "direct_web", "locale": "en-IN",
    })
    result = retrieve_fact_candidates(
        facts, "Saves up to 28% on ORBITA Air One", CONTEXT, PUBLICATION, AS_OF,
        predicate="maximum_saving", unit="%",
    )
    ids = {item["record"]["fact_id"] for item in result["candidates"]}
    assert "DRAFT-FACT" not in ids
    assert "MISSING-SCOPE" in ids  # An omitted dimension is a broader, not narrower, scope.
    incomplete_context = {key: value for key, value in CONTEXT.items() if key != "audience"}
    incomplete = retrieve_fact_candidates(
        facts, "Saves up to 28% on ORBITA Air One", incomplete_context, PUBLICATION, AS_OF,
        predicate="maximum_saving", unit="%",
    )
    incomplete_ids = {item["record"]["fact_id"] for item in incomplete["candidates"]}
    assert "FACT-ORBITA-OFFER-001" not in incomplete_ids
    assert incomplete["trace"]["excluded_counts"]["unapproved"] >= 1


def test_engine_does_not_use_fact_not_recorded_at_review_time():
    engine = VerificationEngine(PACK)
    review_as_of = datetime.fromisoformat("2026-09-24T10:00:00+05:30")
    findings = engine.analyse(
        "Saves up to 28% on ORBITA Air One", CONTEXT, PUBLICATION,
        knowledge_as_of=review_as_of,
    )
    claim = next(item for item in findings if item["code"] == "CLAIM_NUMERIC_SAVING")
    assert claim["verdict"] == "UNVERIFIABLE"
    assert claim["reason_code"] == "FACT_NOT_RECORDED_AT_REVIEW_TIME"
    assert claim["evidence"]
    assert claim["evidence"][0]["eligible_for_proof"] is False
    assert claim["evidence"][0]["record_time_state"] == "NOT_YET_RECORDED"


def test_engine_exposes_retrieval_and_bitemporal_provenance_for_supported_claim():
    engine = VerificationEngine(PACK)
    findings = engine.analyse(
        "Saves up to 28% on ORBITA Air One", CONTEXT, PUBLICATION,
        knowledge_as_of=AS_OF,
    )
    claim = next(item for item in findings if item["code"] == "CLAIM_NUMERIC_SAVING")
    assert claim["verdict"] == "SUPPORTED"
    proof = claim["evidence"][0]
    assert proof["retrieval_method"] == "lexical+structured_rrf"
    assert proof["temporal_state"] == "CURRENT"
    assert proof["record_time_state"] == "RECORDED_AT_REVIEW"
    assert proof["recorded_at"] == "2026-09-25T10:00:00+05:30"
    assert proof["rrf_score"] > 0


def test_higher_source_precedence_wins_but_equal_top_precedence_conflicts():
    facts = deepcopy(PACK.facts)
    facts.extend([
        {
            "fact_id": "PRECEDENCE-HIGH", "brand_id": "brand_orbita_demo", "subject": "ORBITA Air One",
            "predicate": "maximum_saving", "value": 26, "unit": "%", "qualifier": "up_to",
            **{key: CONTEXT[key] for key in ("offer_id", "geography", "channel", "locale", "audience")},
            "status": "approved", "authority_rank": 3,
            "source_ref": {"source_id": "SRC-HIGH", "source_version": 1, "quote": "Up to 26% for ORBITA Air One."},
            "valid_from": "2026-10-01T00:00:00+05:30", "valid_until": "2026-11-30T23:59:59+05:30",
            "recorded_at": "2026-09-01T00:00:00+05:30",
        },
        {
            "fact_id": "PRECEDENCE-LOW", "brand_id": "brand_orbita_demo", "subject": "ORBITA Air One",
            "predicate": "maximum_saving", "value": 30, "unit": "%", "qualifier": "up_to",
            **{key: CONTEXT[key] for key in ("offer_id", "geography", "channel", "locale", "audience")},
            "status": "approved", "authority_rank": 1,
            "source_ref": {"source_id": "SRC-LOW", "source_version": 1, "quote": "Up to 30% for ORBITA Air One."},
            "valid_from": "2026-10-01T00:00:00+05:30", "valid_until": "2026-11-30T23:59:59+05:30",
            "recorded_at": "2026-09-01T00:00:00+05:30",
        },
    ])
    from types import SimpleNamespace
    pack = SimpleNamespace(facts=facts, brand=PACK.brand, terminology=PACK.terminology, voice=PACK.voice)
    engine = VerificationEngine(pack)
    findings = engine.analyse("Save up to 30% on ORBITA Air One", CONTEXT, PUBLICATION, knowledge_as_of=AS_OF)
    claim = next(item for item in findings if item["code"] == "CLAIM_NUMERIC_SAVING")
    assert claim["verdict"] == "CONTRADICTED"
    assert [e["fact_id"] for e in claim["evidence"]] == ["PRECEDENCE-HIGH"]
