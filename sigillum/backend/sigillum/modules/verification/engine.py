"""Conservative deterministic checks for the synthetic ORBITA demonstration pack.

This module deliberately does not attempt unrestricted semantic fact verification.
It evaluates supported structured claim patterns against approved, scoped evidence.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sigillum.modules.knowledge.brand_pack import BrandPack
from sigillum.modules.retrieval.evidence import retrieve_fact_candidates

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


def _authority(fact: dict[str, Any]) -> int:
    """Higher numeric rank wins; equal top ranks remain visible as conflicts."""
    try:
        return int(fact.get("source_precedence", fact.get("authority_rank", 1)))
    except (TypeError, ValueError):
        return 1


def _source_evidence(fact: dict[str, Any], candidate: dict[str, Any] | None = None) -> dict[str, Any]:
    source = fact.get("source_ref") or {}
    candidate = candidate or {}
    temporal = candidate.get("temporal") or {}
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
        "recorded_at": fact.get("recorded_at") or fact.get("recorded_from"),
        "recorded_until": fact.get("recorded_until") or fact.get("superseded_at"),
        "authority_rank": _authority(fact),
        "source_precedence": _authority(fact),
        "scope": {key: fact.get(key) for key in SCOPE_FIELDS},
        "temporal_state": temporal.get("valid_state"),
        "record_time_state": temporal.get("record_state"),
        "temporal_reason": temporal.get("reason_code"),
        "eligible_for_proof": bool(candidate.get("eligible", True)),
        "retrieval_method": candidate.get("retrieval_method", "legacy_structured_match"),
        "lexical_rank": candidate.get("lexical_rank"),
        "structured_rank": candidate.get("structured_rank"),
        "rrf_score": candidate.get("rrf_score"),
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
        knowledge_as_of: datetime | None = None,
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
            text, context, publication_at, confidence, content_regions, findings, knowledge_as_of
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
        knowledge_as_of: datetime | None = None,
    ) -> None:
        retrieval = retrieve_fact_candidates(
            self.pack.facts,
            query=text,
            context={**context, "brand_id": self.pack.brand.get("brand_id")},
            publication_at=publication_at,
            knowledge_as_of=knowledge_as_of,
            predicate="maximum_saving",
            unit="%",
            limit=20,
        )
        candidates = retrieval["candidates"]
        eligible_candidates = [candidate for candidate in candidates if candidate["eligible"]]
        relevant_active = [candidate["record"] for candidate in eligible_candidates]
        future = [
            candidate for candidate in candidates
            if candidate["temporal"].get("valid_state") == "FUTURE"
            and candidate["temporal"].get("record_state") not in {"NOT_YET_RECORDED", "NO_LONGER_RECORDED"}
        ]
        expired = [
            candidate for candidate in candidates
            if candidate["temporal"].get("valid_state") == "EXPIRED"
            and candidate["temporal"].get("record_state") not in {"NOT_YET_RECORDED", "NO_LONGER_RECORDED"}
        ]
        not_recorded = [
            candidate for candidate in candidates
            if candidate["temporal"].get("record_state") in {"NOT_YET_RECORDED", "NO_LONGER_RECORDED"}
        ]
        candidate_by_id = {str(candidate["record"].get("fact_id")): candidate for candidate in candidates}

        for match in PERCENT_CLAIM.finditer(text):
            claimed_value = float(match.group("value"))
            has_up_to = bool(match.group("qualifier"))
            quote = match.group(0).strip()
            verdict = "UNVERIFIABLE"
            severity = "review_required"
            reason = "NO_APPLICABLE_APPROVED_EVIDENCE"
            sufficiency = "INSUFFICIENT"
            explanation = (
                "No approved fact matches all supplied scope dimensions, the intended publication time "
                "and the knowledge snapshot available when this review was recorded. Sigillum abstains "
                "rather than using unrelated or temporally inapplicable brand information."
            )
            evidence: list[dict[str, Any]] = []
            suggestions: list[str] = []

            if not relevant_active:
                if not_recorded:
                    reason = "FACT_NOT_RECORDED_AT_REVIEW_TIME"
                    explanation = (
                        "A matching approved record exists in the supplied knowledge snapshot, but its "
                        "record-time interval does not include this review. It cannot be used as evidence "
                        "for this decision."
                    )
                    evidence = [
                        _source_evidence(candidate["record"], {**candidate, "eligible": False})
                        for candidate in not_recorded
                    ]
                elif future and not expired:
                    reason = "FACT_NOT_YET_VALID"
                    explanation = (
                        "Approved evidence exists, but its effective period begins after the intended "
                        "publication time. Future-effective evidence cannot prove a current claim."
                    )
                    evidence = [
                        _source_evidence(candidate["record"], {**candidate, "eligible": False})
                        for candidate in future
                    ]
                elif expired:
                    verdict = "STALE"
                    reason = "FACT_OUTSIDE_VALIDITY_WINDOW"
                    explanation = (
                        "Related approved evidence has expired and cannot substantiate a claim at the "
                        "intended publication time. The historical source is retained for explanation, "
                        "not treated as current proof."
                    )
                    evidence = [
                        _source_evidence(candidate["record"], {**candidate, "eligible": False})
                        for candidate in expired
                    ]

            else:
                # Source precedence is applied only after scope and both time dimensions
                # have been resolved. Equal top-precedence sources remain a conflict.
                highest_rank = max(_authority(fact) for fact in relevant_active)
                authoritative = [
                    fact for fact in relevant_active if _authority(fact) == highest_rank
                ]
                authoritative.sort(key=lambda fact: str(fact.get("fact_id", "")))
                values = {
                    (fact.get("value"), fact.get("unit"), fact.get("qualifier"))
                    for fact in authoritative
                }
                evidence = [
                    _source_evidence(fact, candidate_by_id.get(str(fact.get("fact_id"))))
                    for fact in authoritative
                ]
                if len(values) > 1:
                    verdict = "CONFLICTING"
                    severity = "blocking"
                    reason = "EQUAL_AUTHORITY_EVIDENCE_CONFLICT"
                    sufficiency = "CONFLICTING"
                    explanation = (
                        "The highest-precedence approved sources disagree. Sigillum will not select "
                        "one by retrieval order; a Brand Owner must resolve the conflict. Lower-precedence "
                        "records do not silently override the highest-precedence group."
                    )
                else:
                    fact = authoritative[0]
                    approved_value = float(fact["value"])
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
                            "selected offer, channel, geography, locale, audience and publication date. "
                            "The evidence candidate was selected using deterministic lexical and "
                            "structured retrieval, then checked against source precedence and time."
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
            # Historical fixture entries omit status and remain approved; any
            # explicit draft/rejected decision must remove the rule from checks.
            if term.get("status", "approved") != "approved":
                continue
            variant = term.get("variant", "")
            if not variant:
                continue
            preferred = next(
                (
                    item.get("preferred")
                    for item in terminology.get("preferred_terms", [])
                    if item.get("term_id") == term.get("preferred_term_id")
                    and item.get("status", "approved") == "approved"
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
        """Return the most specific source region containing a finding span.

        DOCX paragraphs/rows intentionally coexist with child run/cell regions.
        Choosing the first match would always select the broad container and hide
        the precise source location. Prefer the smallest containing span, then a
        granular region kind when spans are equal.
        """
        if start is None or end is None or end < start:
            return None
        preferred_kinds = {
            "docx_run": 0,
            "docx_table_cell": 1,
            "pdf_text_line": 0,
            "pdf_ocr_line": 0,
            "ocr_line": 0,
            "txt_line": 0,
            "docx_heading": 1,
            "docx_paragraph": 2,
            "docx_table_row": 3,
            "docx_header": 2,
            "docx_footer": 2,
        }
        matches = []
        for region in regions:
            region_start = region.get("start")
            region_end = region.get("end")
            if not isinstance(region_start, int) or not isinstance(region_end, int):
                continue
            if region_start <= start and end <= region_end:
                matches.append((region_end - region_start, preferred_kinds.get(region.get("kind"), 5), region))
        if not matches:
            return None
        matches.sort(key=lambda item: (item[0], item[1]))
        return matches[0][2]
