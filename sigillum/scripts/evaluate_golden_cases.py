"""Run the synthetic ORBITA golden set against the currently implemented checks.

This is a transparent capability report, not a claim of model accuracy or certification.
Cases requiring visual inspection are explicitly marked MANUAL_REVIEW_REQUIRED.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sigillum.modules.content.extraction import extract, sniff_file  # noqa: E402
from sigillum.modules.knowledge.brand_pack import BrandPack  # noqa: E402
from sigillum.modules.verification.engine import VerificationEngine  # noqa: E402

PACK = BrandPack(ROOT / "fixtures" / "brand_pack" / "v1")
ENGINE = VerificationEngine(PACK)
CASES = json.loads((ROOT / "fixtures" / "golden_cases" / "cases.json").read_text(encoding="utf-8"))


def evaluate(case: dict) -> tuple[str, str]:
    case_id = case["case_id"]
    if case_id == "GOLD-007":
        return "MANUAL_REVIEW_REQUIRED", "Logo identity and contrast are deliberately not auto-certified."
    if case_id == "GOLD-009":
        fixture = ROOT / "fixtures" / "documents" / "malformed.pdf"
        try:
            mime = sniff_file(fixture.name, fixture.read_bytes())
            extract(fixture.name, fixture.read_bytes())
        except ValueError:
            return "PASS", "Malformed PDF rejected by parser after signature validation."
        return "FAIL", f"Malformed fixture was not rejected (detected MIME: {mime})."
    if case_id == "GOLD-008":
        fixture = ROOT / "fixtures" / "images" / "social_low_confidence_ocr.png"
        extracted = extract(fixture.name, fixture.read_bytes())
        findings = ENGINE.analyse(
            extracted.text,
            case["scope"],
            datetime.fromisoformat("2026-11-08T12:00:00+05:30"),
            extracted.confidence,
            extracted.regions,
        )
        passed = (
            extracted.confidence < 0.75
            and any(f["code"] == "OCR_LOW_CONFIDENCE" and f["verdict"] == "NEEDS_MANUAL_REVIEW" for f in findings)
        )
        return ("PASS" if passed else "FAIL", f"Measured OCR confidence: {extracted.confidence:.3f}; low-confidence gate checked.")

    findings = ENGINE.analyse(
        case["input"],
        case["scope"],
        datetime.fromisoformat(case["scope"].get("publication_at", CASES["default_review_time"])),
    )
    by_code = {item["code"]: item for item in findings}
    expectations = {
        "GOLD-001": ("CLAIM_NUMERIC_SAVING", "CONTRADICTED"),
        "GOLD-002": ("CLAIM_NUMERIC_SAVING", "SUPPORTED"),
        "GOLD-003": ("CLAIM_NUMERIC_SAVING", "STALE"),
        "GOLD-004": ("CLAIM_NUMERIC_SAVING", "UNVERIFIABLE"),
        "GOLD-005": ("CLAIM_NUMERIC_SAVING", "CONFLICTING"),
        "GOLD-006": ("CLAIM_UNVERIFIABLE_QUANTITY", "UNVERIFIABLE"),
        "GOLD-010": ("UNTRUSTED_INSTRUCTION_TEXT", "NEEDS_MANUAL_REVIEW"),
        "GOLD-011": ("TERMINOLOGY_VARIANT", "NEEDS_MANUAL_REVIEW"),
        "GOLD-012": ("VOICE_PATTERN", "NEEDS_MANUAL_REVIEW"),
    }
    expected = expectations.get(case_id)
    if not expected:
        return "NOT_IMPLEMENTED", "No evaluator adapter is defined for this case."
    code, verdict = expected
    match = by_code.get(code)
    passed = bool(match and match["verdict"] == verdict)
    if case_id == "GOLD-004" and match:
        passed = passed and match["reason_code"] == "FACT_NOT_YET_VALID"
    if case_id == "GOLD-005" and match:
        passed = passed and len(match["evidence"]) == 2
    return ("PASS" if passed else "FAIL", f"Expected {code} / {verdict}; got {match['verdict'] if match else 'NO_FINDING'}.")


def main() -> int:
    outcomes = []
    for case in CASES["cases"]:
        status, detail = evaluate(case)
        outcomes.append((case["case_id"], case["title"], status, detail))
    passed = sum(row[2] == "PASS" for row in outcomes)
    manual = sum(row[2] == "MANUAL_REVIEW_REQUIRED" for row in outcomes)
    failed = sum(row[2] == "FAIL" for row in outcomes)
    print(f"SIGILLUM GOLDEN EVALUATION | {CASES['corpus_id']}")
    print("-" * 88)
    for case_id, title, status, detail in outcomes:
        print(f"{case_id:8} {status:24} {title}")
        print(f"         {detail}")
    print("-" * 88)
    print(f"PASS: {passed} | MANUAL REVIEW: {manual} | FAIL: {failed} | TOTAL: {len(outcomes)}")
    print("Synthetic deterministic regression only; not a claim of general model accuracy.")
    report = {
        "corpus_id": CASES["corpus_id"],
        "evaluated_at": datetime.now().astimezone().isoformat(),
        "summary": {"pass": passed, "manual_review_required": manual, "fail": failed, "total": len(outcomes)},
        "results": [
            {"case_id": case_id, "title": title, "status": status, "detail": detail}
            for case_id, title, status, detail in outcomes
        ],
    }
    output = ROOT / "reports" / "golden_evaluation_latest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Report written to: {output.relative_to(ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
