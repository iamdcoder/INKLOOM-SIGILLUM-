"""Deterministic lexical + structured evidence candidate retrieval.

This is a local, database-independent retrieval baseline. It combines two
independent rankings using Reciprocal Rank Fusion (RRF):
  1. lexical overlap against subject, identifiers and approved source snippets;
  2. structured fit against predicate, unit, scope and subject.

Vector retrieval is intentionally not claimed as active in this build. The
ranked candidates remain evidence candidates, not proof; temporal eligibility,
source authority and deterministic claim comparison are still adjudicated later.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sigillum.modules.retrieval.temporal import assess_temporality

SCOPE_FIELDS = ("offer_id", "geography", "channel", "locale", "audience")
TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)?", re.UNICODE)
STOP_WORDS = {"the", "a", "an", "and", "or", "to", "of", "for", "on", "in", "up", "with", "is", "are"}
RRF_K = 60


def _tokens(value: str) -> set[str]:
    return {token.casefold() for token in TOKEN_RE.findall(value) if token.casefold() not in STOP_WORDS}


def _normal(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def scope_matches(record: dict[str, Any], context: dict[str, Any]) -> bool:
    """Fail closed whenever a record specifies a scope dimension not supplied by the review."""
    for field in SCOPE_FIELDS:
        expected = record.get(field)
        if expected in (None, "", []):
            continue
        actual = context.get(field)
        if actual in (None, "", []):
            return False
        if isinstance(expected, list):
            values = {str(item).casefold() for item in expected}
            if str(actual).casefold() not in values:
                return False
        elif str(actual).casefold() != str(expected).casefold():
            return False
    expected_brand = record.get("brand_id")
    actual_brand = context.get("brand_id")
    if expected_brand and actual_brand and str(expected_brand).casefold() != str(actual_brand).casefold():
        return False
    return True


def _subject_matches(record: dict[str, Any], query: str) -> bool:
    subject = _normal(record.get("subject"))
    if not subject:
        return True
    query_norm = _normal(query)
    if subject in query_norm:
        return True
    subject_tokens = _tokens(subject)
    query_tokens = _tokens(query)
    if not subject_tokens:
        return True
    return len(subject_tokens & query_tokens) / len(subject_tokens) >= 0.6


def _lexical_score(record: dict[str, Any], query: str) -> float:
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0.0
    source = record.get("source_ref") or {}
    searchable = " ".join(
        str(value or "")
        for value in (
            record.get("subject"), record.get("predicate"), record.get("fact_id"),
            source.get("source_id"), source.get("quote"), record.get("qualifier"),
        )
    )
    source_tokens = _tokens(searchable)
    overlap = len(query_tokens & source_tokens) / max(1, len(query_tokens))
    subject = _normal(record.get("subject"))
    phrase_bonus = 0.35 if subject and subject in _normal(query) else 0.0
    quote = _normal(source.get("quote"))
    quote_bonus = 0.1 if quote and any(token in quote for token in query_tokens) else 0.0
    return overlap + phrase_bonus + quote_bonus


def _structured_score(
    record: dict[str, Any], context: dict[str, Any], query: str,
    predicate: str | None, unit: str | None,
) -> float:
    score = 0.0
    if predicate and _normal(record.get("predicate")) == _normal(predicate):
        score += 2.0
    if unit and _normal(record.get("unit")) == _normal(unit):
        score += 1.0
    for field in SCOPE_FIELDS:
        expected = record.get(field)
        if expected in (None, "", []):
            score += 0.1
        elif context.get(field) not in (None, "", []) and _normal(context.get(field)) == _normal(expected):
            score += 1.0
    if record.get("subject") and _subject_matches(record, query):
        score += 1.5
    try:
        score += min(max(float(record.get("authority_rank", record.get("source_precedence", 1))), 0), 100) / 1000
    except (TypeError, ValueError):
        pass
    return score


def _rrf_ranks(rows: list[dict[str, Any]], score_key: str) -> dict[str, int]:
    ordered = sorted(rows, key=lambda row: (-row[score_key], str(row["record"].get("fact_id", ""))))
    return {str(row["record"].get("fact_id")): index for index, row in enumerate(ordered, start=1)}


def retrieve_fact_candidates(
    facts: list[dict[str, Any]],
    query: str,
    context: dict[str, Any],
    publication_at: datetime | str,
    knowledge_as_of: datetime | str | None = None,
    predicate: str | None = None,
    unit: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Return scoped approved candidates, temporal assessments and deterministic RRF ranks."""
    rows: list[dict[str, Any]] = []
    excluded = {"unapproved": 0, "scope_mismatch": 0, "subject_mismatch": 0, "not_recorded_at_review": 0}
    for record in facts:
        if record.get("status") != "approved":
            excluded["unapproved"] += 1
            continue
        if predicate and _normal(record.get("predicate")) != _normal(predicate):
            continue
        if unit and _normal(record.get("unit")) != _normal(unit):
            continue
        if not scope_matches(record, context):
            excluded["scope_mismatch"] += 1
            continue
        if not _subject_matches(record, query):
            excluded["subject_mismatch"] += 1
            continue
        temporal = assess_temporality(record, publication_at, knowledge_as_of)
        if temporal.record_state in {"NOT_YET_RECORDED", "NO_LONGER_RECORDED"}:
            excluded["not_recorded_at_review"] += 1
        rows.append({
            "record": record,
            "temporal": temporal.to_dict(),
            "eligible": temporal.eligible,
            "lexical_score": _lexical_score(record, query),
            "structured_score": _structured_score(record, context, query, predicate, unit),
        })

    lexical_ranks = _rrf_ranks(rows, "lexical_score")
    structured_ranks = _rrf_ranks(rows, "structured_score")
    for row in rows:
        fact_id = str(row["record"].get("fact_id"))
        lexical_rank = lexical_ranks.get(fact_id)
        structured_rank = structured_ranks.get(fact_id)
        row["lexical_rank"] = lexical_rank
        row["structured_rank"] = structured_rank
        row["rrf_score"] = (1 / (RRF_K + lexical_rank)) + (1 / (RRF_K + structured_rank))
        row["retrieval_method"] = "lexical+structured_rrf"

    rows.sort(key=lambda row: (-row["rrf_score"], str(row["record"].get("fact_id", ""))))
    selected = rows[: max(1, min(limit, 100))]
    return {
        "candidates": selected,
        "trace": {
            "method": "lexical+structured_rrf",
            "vector_search": "NOT_CONFIGURED",
            "rrf_constant": RRF_K,
            "candidate_count": len(rows),
            "eligible_count": sum(1 for row in rows if row["eligible"]),
            "excluded_counts": excluded,
            "publication_at": str(publication_at),
            "knowledge_as_of": str(knowledge_as_of) if knowledge_as_of is not None else None,
            "scope_fields": list(SCOPE_FIELDS),
        },
    }
