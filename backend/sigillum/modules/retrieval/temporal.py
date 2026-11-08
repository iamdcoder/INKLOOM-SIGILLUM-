"""Bitemporal helpers for approved knowledge records.

Valid time answers: when was this fact true in the real world?
Record time answers: when was this fact present in the governed knowledge system?

Naive timestamps are interpreted as UTC for compatibility with legacy packs. New
Knowledge Pack records should use timezone-aware ISO-8601 timestamps.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class TemporalAssessment:
    eligible: bool
    valid_state: str
    record_state: str
    reason_code: str | None
    publication_at: str
    knowledge_as_of: str | None
    valid_from: str | None
    valid_until: str | None
    recorded_at: str | None
    recorded_until: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_instant(value: str | datetime | None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def assess_temporality(
    record: dict[str, Any],
    publication_at: str | datetime,
    knowledge_as_of: str | datetime | None = None,
) -> TemporalAssessment:
    """Assess a record against publication (valid) and review (record) time.

    A record is eligible only when it was recorded by the review's as-of time and
    its real-world validity covers the intended publication time. When no review
    as-of timestamp is provided, record-time filtering is deliberately disabled
    for backwards-compatible offline unit calls; production review orchestration
    supplies the persisted ReviewRun creation timestamp.
    """
    publication = parse_instant(publication_at)
    as_of = parse_instant(knowledge_as_of)
    valid_from = parse_instant(record.get("valid_from"))
    valid_until = parse_instant(record.get("valid_until"))
    recorded_at = parse_instant(record.get("recorded_at") or record.get("recorded_from"))
    recorded_until = parse_instant(record.get("recorded_until") or record.get("superseded_at"))

    if publication is None:
        return TemporalAssessment(
            False, "INVALID", "UNKNOWN", "INVALID_PUBLICATION_TIME", str(publication_at),
            _iso(as_of), _iso(valid_from), _iso(valid_until), _iso(recorded_at), _iso(recorded_until),
        )

    for field_name in ("valid_from", "valid_until", "recorded_at", "recorded_from", "recorded_until", "superseded_at"):
        raw = record.get(field_name)
        if raw not in (None, "") and parse_instant(raw) is None:
            return TemporalAssessment(
                False, "INVALID", "INVALID", "INVALID_TEMPORAL_METADATA", _iso(publication),
                _iso(as_of), _iso(valid_from), _iso(valid_until), _iso(recorded_at), _iso(recorded_until),
            )

    if valid_from and valid_until and valid_until < valid_from:
        return TemporalAssessment(
            False, "INVALID", "UNKNOWN", "INVALID_VALIDITY_INTERVAL", _iso(publication),
            _iso(as_of), _iso(valid_from), _iso(valid_until), _iso(recorded_at), _iso(recorded_until),
        )
    if recorded_at and recorded_until and recorded_until <= recorded_at:
        return TemporalAssessment(
            False, "VALIDITY_UNCHECKED", "INVALID", "INVALID_RECORD_TIME_INTERVAL", _iso(publication),
            _iso(as_of), _iso(valid_from), _iso(valid_until), _iso(recorded_at), _iso(recorded_until),
        )

    if as_of is None:
        record_state = "UNSCOPED_AS_OF"
    elif recorded_at and recorded_at > as_of:
        record_state = "NOT_YET_RECORDED"
    elif recorded_until and as_of >= recorded_until:
        record_state = "NO_LONGER_RECORDED"
    elif recorded_at is None:
        record_state = "LEGACY_RECORD_TIME_UNKNOWN"
    else:
        record_state = "RECORDED_AT_REVIEW"

    if record_state in {"NOT_YET_RECORDED", "NO_LONGER_RECORDED"}:
        return TemporalAssessment(
            False, "NOT_EVALUATED", record_state,
            "FACT_NOT_RECORDED_AT_REVIEW_TIME" if record_state == "NOT_YET_RECORDED" else "FACT_NO_LONGER_RECORDED_AT_REVIEW_TIME",
            _iso(publication), _iso(as_of), _iso(valid_from), _iso(valid_until), _iso(recorded_at), _iso(recorded_until),
        )

    if valid_from and publication < valid_from:
        return TemporalAssessment(
            False, "FUTURE", record_state, "FACT_NOT_YET_VALID", _iso(publication),
            _iso(as_of), _iso(valid_from), _iso(valid_until), _iso(recorded_at), _iso(recorded_until),
        )
    if valid_until and publication > valid_until:
        return TemporalAssessment(
            False, "EXPIRED", record_state, "FACT_OUTSIDE_VALIDITY_WINDOW", _iso(publication),
            _iso(as_of), _iso(valid_from), _iso(valid_until), _iso(recorded_at), _iso(recorded_until),
        )

    return TemporalAssessment(
        True, "CURRENT", record_state, None, _iso(publication), _iso(as_of),
        _iso(valid_from), _iso(valid_until), _iso(recorded_at), _iso(recorded_until),
    )
