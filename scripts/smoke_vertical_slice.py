"""Exercise the live Sigillum API through the full creator-to-reviewer loop.

Start the API first, then run:
    python scripts/smoke_vertical_slice.py

The script creates one synthetic ORBITA submission, checks that approval is
blocked while the 40% claim is unresolved, accepts a hash-bound TXT patch,
confirms a new immutable version, and approves that exact version as a reviewer.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

ROOT = Path(__file__).resolve().parents[1]
API_PREFIX = "/api/v1"
DEMO_CREATOR = "creator@orbita.demo"
DEMO_REVIEWER = "reviewer@orbita.demo"
DEFAULT_PASSWORD = "ChangeMe-Local-Only"
FIXTURE_TEXT = "Saves up to 40% on ORBITA Air One."


class SmokeFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def check_response(response: httpx.Response, expected: int, label: str) -> dict:
    if response.status_code != expected:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text[:500]
        raise SmokeFailure(
            f"{label}: expected HTTP {expected}, got {response.status_code}: {detail}"
        )
    try:
        return response.json()
    except ValueError as exc:
        raise SmokeFailure(f"{label}: expected a JSON response") from exc


def login(client: httpx.Client, email: str, password: str) -> str:
    response = client.post(
        f"{API_PREFIX}/auth/login",
        json={"email": email, "password": password},
    )
    payload = check_response(response, 200, f"Login {email}")
    token = payload.get("access_token")
    require(isinstance(token, str) and bool(token), f"Login {email}: access token missing")
    return token


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.getenv("SIGILLUM_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument(
        "--password",
        default=os.getenv("SIGILLUM_DEMO_PASSWORD", DEFAULT_PASSWORD),
        help="Demo password; prefer SIGILLUM_DEMO_PASSWORD environment variable.",
    )
    args = parser.parse_args()

    password = args.password
    if not password:
        raise SmokeFailure("Demo password is empty. Set SIGILLUM_DEMO_PASSWORD.")

    pack_facts_path = ROOT / "fixtures" / "brand_pack" / "v1" / "facts.json"
    facts_payload = json.loads(pack_facts_path.read_text(encoding="utf-8"))
    active_fact = next(
        fact for fact in facts_payload["facts"]
        if fact.get("fact_id") == "FACT-ORBITA-OFFER-001"
    )
    now = datetime.now(ZoneInfo("Asia/Kolkata")).replace(microsecond=0)
    valid_from = datetime.fromisoformat(active_fact["valid_from"])
    valid_until = datetime.fromisoformat(active_fact["valid_until"])
    require(
        valid_from <= now <= valid_until,
        "The anchor ORBITA offer is not currently valid. Use a publication time inside its validity window or select another fixture.",
    )

    base_url = args.base_url.rstrip("/")
    report: dict[str, object] = {"base_url": base_url, "checks": []}

    with httpx.Client(base_url=base_url, timeout=30.0, trust_env=False) as client:
        ready = check_response(client.get("/health/ready"), 200, "API readiness")
        require(ready.get("status") == "ready", "API readiness did not return ready")
        report["checks"].append("API readiness")

        creator_token = login(client, DEMO_CREATOR, password)
        reviewer_token = login(client, DEMO_REVIEWER, password)
        creator_headers = {"Authorization": f"Bearer {creator_token}"}
        reviewer_headers = {"Authorization": f"Bearer {reviewer_token}"}
        report["checks"].append("Creator and reviewer authentication")

        publication_at = now.isoformat()
        submitted = check_response(
            client.post(
                f"{API_PREFIX}/submissions",
                headers=creator_headers,
                data={
                    "title": f"Live vertical-slice smoke {now.strftime('%Y%m%d-%H%M%S')}",
                    "channel": "direct_web",
                    "locale": "en-IN",
                    "geography": "IN",
                    "audience": "consumer",
                    "offer_id": "OFFER-ORBITA-OCT-NOV-2026",
                    "publication_at": publication_at,
                },
                files={"file": ("sigillum-smoke.txt", FIXTURE_TEXT.encode("utf-8"), "text/plain")},
            ),
            200,
            "Upload and initial review",
        )
        submission_id = submitted["submission"]["id"]
        first_review_id = submitted["review"]["id"]
        first_version = submitted["content_version"]
        first_hash = first_version["sha256"]
        claim = next(
            (finding for finding in submitted["findings"] if finding["code"] == "CLAIM_NUMERIC_SAVING"),
            None,
        )
        require(claim is not None, "The numeric savings finding was not created")
        require(claim["verdict"] == "CONTRADICTED", f"Expected CONTRADICTED, got {claim['verdict']}")
        require(claim["content_quote"] == "up to 40%", "The exact claim span was not preserved")
        require(
            any(item.get("fact_id") == "FACT-ORBITA-OFFER-001" for item in claim.get("evidence", [])),
            "The finding does not reference the approved ORBITA fact",
        )
        report["submission_id"] = submission_id
        report["initial_review_id"] = first_review_id
        report["checks"].append("Upload, immutable v1 and source-linked CONTRADICTED finding")

        blocked = client.post(
            f"{API_PREFIX}/reviews/{first_review_id}/decisions",
            headers=reviewer_headers,
            json={"action": "APPROVE"},
        )
        blocked_payload = check_response(blocked, 409, "Approval gate before correction")
        require(
            blocked_payload.get("detail", {}).get("code") == "OPEN_BLOCKING_FINDINGS",
            "Approval was not blocked for the unresolved 40% claim",
        )
        report["checks"].append("Human approval correctly blocked while the blocking finding is open")

        suggestions = claim.get("suggestions") or []
        require(bool(suggestions), "No constrained correction suggestion was generated")
        patch = check_response(
            client.post(
                f"{API_PREFIX}/reviews/{first_review_id}/patches",
                headers=creator_headers,
                json={
                    "finding_id": claim["id"],
                    "replacement": suggestions[0],
                    "rationale": "Replace the overstated claim with the currently approved offer value.",
                },
            ),
            200,
            "Propose correction patch",
        )
        revised = check_response(
            client.post(f"{API_PREFIX}/patches/{patch['id']}/accept", headers=creator_headers),
            200,
            "Accept patch and create new version",
        )
        new_version = revised["content_version"]
        require(new_version["version_number"] == 2, "Correction did not create version 2")
        require(new_version["sha256"] != first_hash, "The revised version hash did not change")
        require(new_version["text"] == "Saves up to 28% on ORBITA Air One.", "The revised text is not as expected")
        revised_claim = next(
            (finding for finding in revised["findings"] if finding["code"] == "CLAIM_NUMERIC_SAVING"),
            None,
        )
        require(revised_claim is not None, "The revised review omitted the numeric claim check")
        require(revised_claim["verdict"] == "SUPPORTED", "The corrected 28% claim was not supported")
        report["revised_review_id"] = revised["review"]["id"]
        report["checks"].append("Hash-bound correction created immutable v2 and re-ran verification")

        approval = check_response(
            client.post(
                f"{API_PREFIX}/reviews/{revised['review']['id']}/decisions",
                headers=reviewer_headers,
                json={"action": "APPROVE"},
            ),
            200,
            "Reviewer approval of corrected version",
        )
        require(approval["submission_status"] == "APPROVED", "Submission was not approved")
        require(approval["content_hash"] == new_version["sha256"], "Approval hash is not bound to v2")
        report["checks"].append("Reviewer approved the exact corrected content hash")

        history = check_response(
            client.get(f"{API_PREFIX}/submissions/{submission_id}/history", headers=creator_headers),
            200,
            "Immutable version history",
        )
        versions = history.get("versions", [])
        require(len(versions) >= 2, "Version history does not contain both immutable versions")
        v2 = next((item for item in versions if item["version_number"] == 2), None)
        require(v2 is not None, "Version 2 is missing from history")
        require(v2["sha256"] == new_version["sha256"], "History hash does not match corrected version")
        report["checks"].append("Version history reconstructs v1 and v2")

        audit_events = check_response(
            client.get(f"{API_PREFIX}/audit", headers=reviewer_headers),
            200,
            "Audit trail",
        )
        event_types = {item["event_type"] for item in audit_events}
        required_events = {
            "SUBMISSION_CREATED",
            "PATCH_PROPOSED",
            "PATCH_ACCEPTED_NEW_VERSION_CREATED",
            "REVIEW_DECISION_RECORDED",
        }
        missing = sorted(required_events - event_types)
        require(not missing, f"Audit trail is missing events: {', '.join(missing)}")
        report["checks"].append("Audit trail contains submission, patch and approval events")

    report["result"] = "PASS"
    report["initial_sha256"] = first_hash
    report["approved_sha256"] = approval["content_hash"]
    report["submission_status"] = approval["submission_status"]
    report["checks_passed"] = len(report["checks"])
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SmokeFailure, httpx.HTTPError, KeyError, StopIteration) as exc:
        print(f"SMOKE TEST FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
