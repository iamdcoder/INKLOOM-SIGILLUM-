"""Conservative deterministic checks for the synthetic ORBITA demonstration pack.

This module deliberately does not attempt unrestricted semantic fact verification.
It evaluates supported structured claim patterns against approved, scoped evidence.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sigillum.modules.knowledge.brand_pack import BrandPack

PERCENT_CLAIM = re.compile(
    r"(?P<qualifier>up\s+to\s+)?(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>%|percent)",
    re.IGNORECASE,
)
OTHER_QUANTIFIED_CLAIM = re.compile(
    r"\b(?P<value>\d+(?:\.\d+)?)\s+(?P<unit>hours?|days?|weeks?|months?|years?|litres?|liters?|kg|kilograms?|watts?|hours?\s+of\s+runtime)\b",
    re.IGNORECASE,
)
PROMPT_INJECTION = re.compile(
    r"ignore\s+(all\s+)?(previous|prior)\s+instructions|reveal\s+(the\s+)?(system|developer)\s+(prompt|secrets?)|"
    r"override\s+(the\s+)?(system|safety)\s+instructions|exfiltrate\s+(the\s+)?(secrets?|credentials?)",
    re.IGNORECASE,
)

SCOPE_FIELDS = ("offer_id", "geography", "channel", "locale", "audience")


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _normalise_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _active(fact: dict[str, Any], publication_at: datetime) -> bool:
    start = _parse_datetime(fact.get("valid_from"))
    end = _parse_datetime(fact.get("valid_until"))
    when = _normalise_datetime(publication_at)
    return (start is None or start <= when) and (end is None or when <= end)


def _scope_match(fact: dict[str, Any], context: dict[str, Any]) -> bool:
    """Fail closed: each non-empty fact scope dimension must be present and equal."""
    for field in SCOPE_FIELDS:
        expected = fact.get(field)
        if expected is None or expected == "":
            continue
        actual = context.get(field)
        if actual is None or str(actual).strip() == "":
            return False
        if str(actual).casefold() != str(expected).casefold():
            return False
    return True


def _authority(fact: dict[str, Any]) -> int:
    try:
        return int(fact.get("authority_rank", 1))
    except (TypeError, ValueError):
        return 1


def _source_evidence(fact: dict[str, Any]) -> dict[str, Any]:
    source = fact.get("source_ref") or {}
    return {
        "fact_id": fact.get("fact_id"),
        "source_id": source.get("source_id"),
        "source_version": source.get("source_version"),
        "quote": source.get("quote"),
        "value": fact.get("value"),
        "unit": fact.get("unit"),
        "qualifier": fact.get("qualifier"),
        "valid_from": fact.get("valid_from"),
        "valid_until": fact.get("valid_until"),
        "authority_rank": _authority(fact),
        "scope": {key: fact.get(key) for key in SCOPE_FIELDS},
    }


def _base_finding(
    *,
    code: str,
    category: str,
    severity: str,
    verdict: str,
    title: str,
    explanation: str,
    reason_code: str,
    evidence_sufficiency: str,
    confidence: float,
    extraction_confidence: float,
    start: int | None,
    end: int | None,
    quote: str | None,
    regions: list[dict[str, Any]],
    evidence: list[dict[str, Any]] | None = None,
    suggestions: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "category": category,
        "severity": severity,
        "verdict": verdict,
        "title": title,
        "explanation": explanation,
        "reason_code": reason_code,
        "evidence_sufficiency": evidence_sufficiency,
        "confidence": confidence,
        "extraction_confidence": extraction_confidence,
        "content_start": start,
        "content_end": end,
        "content_quote": quote,
        "region": VerificationEngine._region_for(start, end, regions),
        "evidence": evidence or [],
        "suggestions": suggestions or [],
    }


class VerificationEngine:
    def __init__(self, pack: BrandPack):
        self.pack = pack

    def analyse(
        self,
        text: str,
        context: dict[str, Any],
        publication_at: datetime,
        extraction_confidence: float = 1.0,
        regions: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        content_regions = regions or []
        confidence = max(0.0, min(1.0, extraction_confidence))

        if confidence < 0.75:
            findings.append(
                _base_finding(
                    code="OCR_LOW_CONFIDENCE",
                    category="extraction",
                    severity="review_required",
                    verdict="NEEDS_MANUAL_REVIEW",
                    title="OCR text needs visual confirmation",
                    explanation=(
                        "Text extraction confidence is below the configured 0.75 threshold. "
                        "Numeric claims must be checked against the original image before use."
                    ),
                    reason_code="LOW_EXTRACTION_CONFIDENCE",
                    evidence_sufficiency="INSUFFICIENT",
                    confidence=0.0,
                    extraction_confidence=confidence,
                    start=None,
                    end=None,
                    quote=None,
                    regions=content_regions,
                )
            )

        self._analyse_percentage_claims(
            text, context, publication_at, confidence, content_regions, findings
        )
        self._analyse_unmatched_quantities(text, confidence, content_regions, findings)
        self._analyse_terminology(text, confidence, content_regions, findings)
        self._analyse_voice(text, confidence, content_regions, findings)
        self._analyse_untrusted_instructions(text, confidence, content_regions, findings)
        return findings

    def _analyse_percentage_claims(
        self,
        text: str,
        context: dict[str, Any],
        publication_at: datetime,
        extraction_confidence: float,
        regions: list[dict[str, Any]],
        findings: list[dict[str, Any]],
    ) -> None:
        all_facts = [
            fact
            for fact in self.pack.facts
            if fact.get("status") == "approved"
            and fact.get("predicate") == "maximum_saving"
            and fact.get("unit") == "%"
            and _scope_match(fact, context)
        ]
        active_facts = [fact for fact in all_facts if _active(fact, publication_at)]
        relevant_active = [
            fact
            for fact in active_facts
            if not fact.get("subject") or fact["subject"].casefold() in text.casefold()
        ]

        for match in PERCENT_CLAIM.finditer(text):
            claimed_value = float(match.group("value"))
            has_up_to = bool(match.group("qualifier"))
            quote = match.group(0).strip()
            verdict = "UNVERIFIABLE"
            severity = "review_required"
            reason = "NO_APPLICABLE_APPROVED_EVIDENCE"
            sufficiency = "INSUFFICIENT"
            explanation = (
                "No approved fact matches all supplied scope dimensions and the intended publication "
                "time. Sigillum abstains rather than using unrelated brand information."
            )
            evidence: list[dict[str, Any]] = []
            suggestions: list[str] = []

            if not relevant_active and all_facts:
                future = [
                    fact
                    for fact in all_facts
                    if _parse_datetime(fact.get("valid_from"))
                    and _parse_datetime(fact.get("valid_from")) > _normalise_datetime(publication_at)
                ]
                expired = [
                    fact
                    for fact in all_facts
                    if _parse_datetime(fact.get("valid_until"))
                    and _parse_datetime(fact.get("valid_until")) < _normalise_datetime(publication_at)
                ]
                if future and not expired:
                    reason = "FACT_NOT_YET_VALID"
                    explanation = (
                        "Approved evidence exists, but its effective period begins after the intended "
                        "publication time. Future-effective evidence cannot prove a current claim."
                    )
                    evidence = [_source_evidence(fact) for fact in future]
                elif expired:
                    verdict = "STALE"
                    reason = "FACT_OUTSIDE_VALIDITY_WINDOW"
                    explanation = (
                        "Related approved evidence has expired and cannot substantiate a claim at the "
                        "intended publication time."
                    )
                    evidence = [_source_evidence(fact) for fact in expired]

            elif relevant_active:
                highest_rank = max(_authority(fact) for fact in relevant_active)
                authoritative = [
                    fact for fact in relevant_active if _authority(fact) == highest_rank
                ]
                values = {
                    (fact.get("value"), fact.get("unit"), fact.get("qualifier"))
                    for fact in authoritative
                }
                if len(values) > 1:
                    verdict = "CONFLICTING"
                    severity = "blocking"
                    reason = "EQUAL_AUTHORITY_EVIDENCE_CONFLICT"
                    sufficiency = "CONFLICTING"
                    explanation = (
                        "The highest-authority approved sources disagree. Sigillum will not choose "
                        "one by retrieval order; a brand owner must resolve the conflict."
                    )
                    evidence = [_source_evidence(fact) for fact in authoritative]
                else:
                    fact = authoritative[0]
                    approved_value = float(fact["value"])
                    evidence = [_source_evidence(fact)]
                    if claimed_value > approved_value:
                        verdict = "CONTRADICTED"
                        severity = "blocking"
                        reason = "CLAIM_EXCEEDS_APPROVED_VALUE"
                        sufficiency = "SUFFICIENT_TO_CONTRADICT"
                        explanation = (
                            f"The submitted claim states {claimed_value:g}% while the applicable "
                            f"approved fact supports up to {approved_value:g}%. The submitted amount "
                            "exceeds the authorised evidence."
                        )
                        suggestions = [
                            f"up to {approved_value:g}%" if has_up_to else f"{approved_value:g}%"
                        ]
                    elif claimed_value == approved_value and (
                        fact.get("qualifier") != "up_to" or has_up_to
                    ):
                        verdict = "SUPPORTED"
                        severity = "informational"
                        reason = "EXACT_SCOPED_FACT_MATCH"
                        sufficiency = "SUFFICIENT"
                        explanation = (
                            f"The {claimed_value:g}% claim matches approved evidence for the "
                            "selected offer, channel, geography, locale, audience and publication date."
                        )
                    else:
                        reason = "CLAIM_NOT_EXACTLY_SUBSTANTIATED"
                        sufficiency = "PARTIAL"
                        explanation = (
                            "The approved maximum does not establish this exact claim wording and "
                            "qualifier. Sigillum abstains rather than inferring equivalence."
                        )

            if extraction_confidence < 0.75:
                verdict = "NEEDS_MANUAL_REVIEW"
                severity = "review_required"
                reason = "LOW_EXTRACTION_CONFIDENCE_BLOCKS_ADJUDICATION"
                sufficiency = "INSUFFICIENT"
                explanation = (
                    "A possible numeric claim was extracted, but OCR confidence is too low for a "
                    "decisive factual verdict. Inspect the original image."
                )
                evidence = []
                suggestions = []

            findings.append(
                _base_finding(
                    code="CLAIM_NUMERIC_SAVING",
                    category="claims",
                    severity=severity,
                    verdict=verdict,
                    title="Promotional percentage claim",
                    explanation=explanation,
                    reason_code=reason,
                    evidence_sufficiency=sufficiency,
                    confidence=1.0 if relevant_active else 0.65,
                    extraction_confidence=extraction_confidence,
                    start=match.start(),
                    end=match.end(),
                    quote=quote,
                    regions=regions,
                    evidence=evidence,
                    suggestions=suggestions,
                )
            )

    @staticmethod
    def _analyse_unmatched_quantities(
        text: str,
        extraction_confidence: float,
        regions: list[dict[str, Any]],
        findings: list[dict[str, Any]],
    ) -> None:
        for match in OTHER_QUANTIFIED_CLAIM.finditer(text):
            quote = match.group(0)
            findings.append(
                _base_finding(
                    code="CLAIM_UNVERIFIABLE_QUANTITY",
                    category="claims",
                    severity="review_required",
                    verdict="UNVERIFIABLE",
                    title="Quantified claim without an approved fact",
                    explanation=(
                        "This quantified statement is outside the deterministic fact patterns "
                        "currently configured in the Brand Knowledge Pack. No factual support is "
                        "being inferred; a reviewer must provide or locate approved evidence."
                    ),
                    reason_code="NO_MATCHING_APPROVED_FACT_TYPE",
                    evidence_sufficiency="INSUFFICIENT",
                    confidence=0.65,
                    extraction_confidence=extraction_confidence,
                    start=match.start(),
                    end=match.end(),
                    quote=quote,
                    regions=regions,
                )
            )

    def _analyse_terminology(
        self,
        text: str,
        extraction_confidence: float,
        regions: list[dict[str, Any]],
        findings: list[dict[str, Any]],
    ) -> None:
        terminology = self.pack.terminology
        for term in terminology.get("prohibited_or_review_terms", []):
            variant = term.get("variant", "")
            if not variant:
                continue
            preferred = next(
                (
                    item.get("preferred")
                    for item in terminology.get("preferred_terms", [])
                    if item.get("term_id") == term.get("preferred_term_id")
                ),
                "",
            )
            for match in re.finditer(re.escape(variant), text, re.IGNORECASE):
                suffix = preferred[len(variant) :] if preferred.lower().startswith(variant.lower()) else ""
                if suffix and text[match.end() :].casefold().startswith(suffix.casefold()):
                    continue
                findings.append(
                    _base_finding(
                        code="TERMINOLOGY_VARIANT",
                        category="terminology",
                        severity=term.get("severity", "review_required"),
                        verdict="NEEDS_MANUAL_REVIEW",
                        title="Non-canonical terminology",
                        explanation=(
                            f"'{variant}' is not the approved product terminology. Use '{preferred}' "
                            "where that preferred term applies."
                        ),
                        reason_code="PROHIBITED_OR_REVIEW_TERM",
                        evidence_sufficiency="RULE_MATCH",
                        confidence=1.0,
                        extraction_confidence=extraction_confidence,
                        start=match.start(),
                        end=match.end(),
                        quote=match.group(0),
                        regions=regions,
                        evidence=[
                            {
                                "term_id": term.get("term_id"),
                                "preferred_term_id": term.get("preferred_term_id"),
                                "reason": term.get("reason"),
                            }
                        ],
                        suggestions=[preferred] if preferred else [],
                    )
                )

    def _analyse_voice(
        self,
        text: str,
        extraction_confidence: float,
        regions: list[dict[str, Any]],
        findings: list[dict[str, Any]],
    ) -> None:
        for pattern in self.pack.voice.get("disallowed_patterns", []):
            phrase = pattern.get("pattern", "")
            if not phrase:
                continue
            for match in re.finditer(re.escape(phrase), text, re.IGNORECASE):
                findings.append(
                    _base_finding(
                        code="VOICE_PATTERN",
                        category="tone",
                        severity=pattern.get("severity", "review_required"),
                        verdict="NEEDS_MANUAL_REVIEW",
                        title="Unapproved voice pattern",
                        explanation=(
                            f"The phrase '{phrase}' is listed for review: "
                            f"{pattern.get('reason', 'No rationale supplied')}"
                        ),
                        reason_code="VOICE_GUIDELINE_MATCH",
                        evidence_sufficiency="RULE_MATCH",
                        confidence=1.0,
                        extraction_confidence=extraction_confidence,
                        start=match.start(),
                        end=match.end(),
                        quote=match.group(0),
                        regions=regions,
                        evidence=[
                            {"policy_source": "Brand Knowledge Pack voice guidance", "pattern": phrase}
                        ],
                    )
                )

    @staticmethod
    def _analyse_untrusted_instructions(
        text: str,
        extraction_confidence: float,
        regions: list[dict[str, Any]],
        findings: list[dict[str, Any]],
    ) -> None:
        for match in PROMPT_INJECTION.finditer(text):
            findings.append(
                _base_finding(
                    code="UNTRUSTED_INSTRUCTION_TEXT",
                    category="security",
                    severity="review_required",
                    verdict="NEEDS_MANUAL_REVIEW",
                    title="Instruction-like text in uploaded content",
                    explanation=(
                        "The uploaded content contains text resembling an instruction to an AI system. "
                        "Uploaded content is treated as untrusted data and is not executed or allowed "
                        "to change system instructions or permissions."
                    ),
                    reason_code="POSSIBLE_PROMPT_INJECTION_IN_DOCUMENT",
                    evidence_sufficiency="RULE_MATCH",
                    confidence=1.0,
                    extraction_confidence=extraction_confidence,
                    start=match.start(),
                    end=match.end(),
                    quote=match.group(0),
                    regions=regions,
                )
            )

    @staticmethod
    def _region_for(start: int | None, end: int | None, regions: list[dict[str, Any]]):
        if start is None or end is None:
            return None
        for region in regions:
            region_start = region.get("start", -1)
            region_end = region.get("end", -1)
            if region_start <= start and end <= region_end:
                return region
        return None
