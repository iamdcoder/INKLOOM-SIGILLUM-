import pytest
from fastapi.testclient import TestClient
from apps.api.main import app

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client

def token(client, email="creator@orbita.demo", password="ChangeMe-Local-Only"):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]

def test_health_endpoints(client):
    assert client.get("/health/live").json()["status"] == "ok"
    assert client.get("/health/ready").json()["status"] == "ready"

def test_upload_review_and_role_gated_approval(client):
    creator = token(client)
    headers = {"Authorization": f"Bearer {creator}"}
    response = client.post(
        "/api/v1/submissions",
        headers=headers,
        data={
            "title": "40 percent launch copy",
            "channel": "direct_web",
            "locale": "en-IN",
            "geography": "IN",
            "audience": "consumer",
            "offer_id": "OFFER-ORBITA-OCT-NOV-2026",
            "publication_at": "2026-11-08T12:00:00+05:30",
        },
        files={"file": ("claim.txt", b"Saves up to 40% on ORBITA Air One", "text/plain")},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["content_version"]["version_number"] == 1
    claim = next(f for f in data["findings"] if f["code"] == "CLAIM_NUMERIC_SAVING")
    assert claim["verdict"] == "CONTRADICTED"
    blocked = client.post(
        f"/api/v1/reviews/{data['review']['id']}/decisions",
        headers=headers,
        json={"action": "APPROVE"},
    )
    assert blocked.status_code == 403

def test_reviewer_cannot_approve_open_blocking_finding(client):
    reviewer = token(client, "reviewer@orbita.demo")
    headers = {"Authorization": f"Bearer {reviewer}"}
    response = client.post(
        "/api/v1/submissions",
        headers=headers,
        data={
            "title": "40 percent claim",
            "channel": "direct_web",
            "locale": "en-IN",
            "geography": "IN",
            "audience": "consumer",
            "offer_id": "OFFER-ORBITA-OCT-NOV-2026",
            "publication_at": "2026-11-08T12:00:00+05:30",
        },
        files={"file": ("claim.txt", b"Saves up to 40% on ORBITA Air One", "text/plain")},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    decision = client.post(
        f"/api/v1/reviews/{data['review']['id']}/decisions",
        headers=headers,
        json={"action": "APPROVE"},
    )
    assert decision.status_code == 409

def test_patch_creates_new_immutable_version_then_reviewer_can_approve(client):
    creator = token(client)
    creator_headers = {"Authorization": f"Bearer {creator}"}
    response = client.post(
        "/api/v1/submissions",
        headers=creator_headers,
        data={
            "title": "Anchor scenario patch loop",
            "channel": "direct_web",
            "locale": "en-IN",
            "geography": "IN",
            "audience": "consumer",
            "offer_id": "OFFER-ORBITA-OCT-NOV-2026",
            "publication_at": "2026-11-08T12:00:00+05:30",
        },
        files={"file": ("anchor.txt", b"Saves up to 40% on ORBITA Air One", "text/plain")},
    )
    assert response.status_code == 200, response.text
    first = response.json()
    claim = next(f for f in first["findings"] if f["code"] == "CLAIM_NUMERIC_SAVING")
    proposed = client.post(
        f"/api/v1/reviews/{first['review']['id']}/patches",
        headers=creator_headers,
        json={
            "finding_id": claim["id"],
            "replacement": claim["suggestions"][0],
            "rationale": "Use the exact currently approved offer value.",
        },
    )
    assert proposed.status_code == 200, proposed.text
    patched = client.post(f"/api/v1/patches/{proposed.json()['id']}/accept", headers=creator_headers)
    assert patched.status_code == 200, patched.text
    second = patched.json()
    assert second["content_version"]["version_number"] == 2
    assert second["content_version"]["sha256"] != first["content_version"]["sha256"]
    assert second["content_version"]["text"] == "Saves up to 28% on ORBITA Air One"
    claim_after_patch = next(f for f in second["findings"] if f["code"] == "CLAIM_NUMERIC_SAVING")
    assert claim_after_patch["verdict"] == "SUPPORTED"

    reviewer = token(client, "reviewer@orbita.demo")
    reviewer_headers = {"Authorization": f"Bearer {reviewer}"}
    approved = client.post(
        f"/api/v1/reviews/{second['review']['id']}/decisions",
        headers=reviewer_headers,
        json={"action": "APPROVE"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["submission_status"] == "APPROVED"
    assert approved.json()["content_hash"] == second["content_version"]["sha256"]


def test_submission_id_can_open_latest_review(client):
    creator = token(client)
    headers = {"Authorization": f"Bearer {creator}"}
    response = client.post(
        "/api/v1/submissions",
        headers=headers,
        data={
            "title": "Open by submission identifier",
            "channel": "direct_web",
            "locale": "en-IN",
            "geography": "IN",
            "audience": "consumer",
            "offer_id": "OFFER-ORBITA-OCT-NOV-2026",
            "publication_at": "2026-11-08T12:00:00+05:30",
        },
        files={"file": ("claim.txt", b"A calm product description.", "text/plain")},
    )
    data = response.json()
    opened = client.get(f"/api/v1/reviews/{data['submission']['id']}", headers=headers)
    assert opened.status_code == 200, opened.text
    assert opened.json()["review"]["id"] == data["review"]["id"]


def test_upload_rejects_mismatched_file_signature(client):
    creator = token(client)
    headers = {"Authorization": f"Bearer {creator}"}
    response = client.post(
        "/api/v1/submissions",
        headers=headers,
        data={
            "title": "Signature validation",
            "channel": "direct_web",
            "locale": "en-IN",
            "geography": "IN",
            "audience": "consumer",
            "offer_id": "OFFER-ORBITA-OCT-NOV-2026",
            "publication_at": "2026-11-08T12:00:00+05:30",
        },
        files={"file": ("fake.pdf", b"This is not a PDF", "application/pdf")},
    )
    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "INVALID_UPLOAD"


def test_creator_cannot_read_another_creators_submission(client):
    from apps.api.main import SessionLocal
    from sigillum.infrastructure.database import models
    from sigillum.infrastructure.security import hash_password

    creator_one = token(client)
    headers_one = {"Authorization": f"Bearer {creator_one}"}
    response = client.post(
        "/api/v1/submissions",
        headers=headers_one,
        data={
            "title": "Private creator draft",
            "channel": "direct_web",
            "locale": "en-IN",
            "geography": "IN",
            "audience": "consumer",
            "offer_id": "OFFER-ORBITA-OCT-NOV-2026",
            "publication_at": "2026-11-08T12:00:00+05:30",
        },
        files={"file": ("draft.txt", b"Private content for creator one.", "text/plain")},
    )
    assert response.status_code == 200, response.text
    submission_id = response.json()["submission"]["id"]

    with SessionLocal() as db:
        second = db.query(models.User).filter(models.User.email == "creator.two@orbita.demo").first()
        if second is None:
            second = models.User(
                email="creator.two@orbita.demo",
                display_name="Second Creator",
                role="creator",
                password_hash=hash_password("Second-Creator-Password"),
                tenant_id="tenant_demo",
            )
            db.add(second)
        else:
            second.password_hash = hash_password("Second-Creator-Password")
        db.commit()

    creator_two = token(client, "creator.two@orbita.demo", "Second-Creator-Password")
    headers_two = {"Authorization": f"Bearer {creator_two}"}
    listing = client.get("/api/v1/submissions", headers=headers_two)
    assert listing.status_code == 200
    assert all(item["id"] != submission_id for item in listing.json())
    hidden = client.get(f"/api/v1/submissions/{submission_id}", headers=headers_two)
    assert hidden.status_code == 404


def test_pdf_and_docx_upload_keep_claims_in_shared_review_pipeline(client):
    from pathlib import Path

    creator = token(client)
    headers = {"Authorization": f"Bearer {creator}"}
    fixture_root = Path(__file__).parents[2] / "fixtures" / "documents"
    for filename in ("claim_40_percent.pdf", "claim_40_percent.docx"):
        path = fixture_root / filename
        response = client.post(
            "/api/v1/submissions",
            headers=headers,
            data={
                "title": f"Parser check — {filename}",
                "channel": "direct_web",
                "locale": "en-IN",
                "geography": "IN",
                "audience": "consumer",
                "offer_id": "OFFER-ORBITA-OCT-NOV-2026",
                "publication_at": "2026-11-08T12:00:00+05:30",
            },
            files={"file": (filename, path.read_bytes(), "application/octet-stream")},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        claim = next(item for item in data["findings"] if item["code"] == "CLAIM_NUMERIC_SAVING")
        assert claim["verdict"] == "CONTRADICTED"
        assert any(item["code"] == "DOCUMENT_VISUAL_REVIEW" for item in data["findings"])


def test_uploaded_revision_creates_next_immutable_version(client):
    creator = token(client)
    headers = {"Authorization": f"Bearer {creator}"}
    initial = client.post(
        "/api/v1/submissions",
        headers=headers,
        data={
            "title": "Revision upload history",
            "channel": "direct_web",
            "locale": "en-IN",
            "geography": "IN",
            "audience": "consumer",
            "offer_id": "OFFER-ORBITA-OCT-NOV-2026",
            "publication_at": "2026-11-08T12:00:00+05:30",
        },
        files={"file": ("initial.txt", b"Saves up to 40% on ORBITA Air One", "text/plain")},
    )
    assert initial.status_code == 200, initial.text
    before = initial.json()
    revision = client.post(
        f"/api/v1/submissions/{before['submission']['id']}/revisions/upload",
        headers=headers,
        data={"change_summary": "Corrected offer claim to approved value."},
        files={"file": ("revision.txt", b"Saves up to 28% on ORBITA Air One", "text/plain")},
    )
    assert revision.status_code == 200, revision.text
    after = revision.json()
    assert after["submission"]["id"] == before["submission"]["id"]
    assert after["content_version"]["version_number"] == 2
    assert after["content_version"]["sha256"] != before["content_version"]["sha256"]
    assert next(f for f in after["findings"] if f["code"] == "CLAIM_NUMERIC_SAVING")["verdict"] == "SUPPORTED"


def test_image_review_requires_visual_inspection_before_human_approval(client):
    from pathlib import Path

    creator = token(client)
    creator_headers = {"Authorization": f"Bearer {creator}"}
    fixture = Path(__file__).parents[2] / "fixtures" / "images" / "social_supported_clean.png"
    submitted = client.post(
        "/api/v1/submissions",
        headers=creator_headers,
        data={
            "title": "Approved image claim still needs visual inspection",
            "channel": "direct_web",
            "locale": "en-IN",
            "geography": "IN",
            "audience": "consumer",
            "offer_id": "OFFER-ORBITA-OCT-NOV-2026",
            "publication_at": "2026-11-08T12:00:00+05:30",
        },
        files={"file": (fixture.name, fixture.read_bytes(), "image/png")},
    )
    assert submitted.status_code == 200, submitted.text
    payload = submitted.json()
    assert payload["content_version"]["extraction_confidence"] >= 0.75
    codes = {finding["code"] for finding in payload["findings"]}
    assert "VISUAL_ASSET_MANUAL_REVIEW" in codes
    # This direct_web submission is outside the social/print contrast policy scope.
    # The image-region metadata may say UNMEASURABLE, but no out-of-scope finding is created.
    assert "VISUAL_CONTRAST_REVIEW" not in codes

    reviewer = token(client, "reviewer@orbita.demo")
    reviewer_headers = {"Authorization": f"Bearer {reviewer}"}
    blocked = client.post(
        f"/api/v1/reviews/{payload['review']['id']}/decisions",
        headers=reviewer_headers,
        json={"action": "APPROVE"},
    )
    assert blocked.status_code == 409

    for finding in payload["findings"]:
        if finding["severity"] == "review_required" and finding["verdict"] == "NEEDS_MANUAL_REVIEW":
            resolved = client.post(
                f"/api/v1/reviews/{payload['review']['id']}/findings/{finding['id']}/resolve",
                headers=reviewer_headers,
                data={"reason": "Inspected original image against the approved brand asset and accessibility checklist."},
            )
            assert resolved.status_code == 200, resolved.text

    approved = client.post(
        f"/api/v1/reviews/{payload['review']['id']}/decisions",
        headers=reviewer_headers,
        json={"action": "APPROVE"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["submission_status"] == "APPROVED"
    assert approved.json()["content_hash"] == payload["content_version"]["sha256"]


def test_review_history_binds_each_version_to_knowledge_snapshot_and_rejects_stale_decision(client):
    creator = token(client)
    creator_headers = {"Authorization": f"Bearer {creator}"}
    initial = client.post(
        "/api/v1/submissions",
        headers=creator_headers,
        data={
            "title": "Knowledge snapshot and version history",
            "channel": "direct_web",
            "locale": "en-IN",
            "geography": "IN",
            "audience": "consumer",
            "offer_id": "OFFER-ORBITA-OCT-NOV-2026",
            "publication_at": "2026-11-10T12:00:00+05:30",
        },
        files={"file": ("history-v1.txt", b"Saves up to 40% on ORBITA Air One", "text/plain")},
    )
    assert initial.status_code == 200, initial.text
    first = initial.json()

    revised = client.post(
        f"/api/v1/submissions/{first['submission']['id']}/revisions/upload",
        headers=creator_headers,
        data={"change_summary": "Replaced the unsupported percentage with the approved offer value."},
        files={"file": ("history-v2.txt", b"Saves up to 28% on ORBITA Air One", "text/plain")},
    )
    assert revised.status_code == 200, revised.text
    second = revised.json()

    history = client.get(
        f"/api/v1/submissions/{first['submission']['id']}/history",
        headers=creator_headers,
    )
    assert history.status_code == 200, history.text
    versions = history.json()["versions"]
    assert [item["version_number"] for item in versions] == [2, 1]
    assert versions[0]["sha256"] != versions[1]["sha256"]
    assert all(len(item["knowledge_pack_hash"]) == 64 for item in versions)
    assert versions[0]["analysis_config_version"] == "deterministic-rules-v1"
    assert second["review"]["knowledge_pack_hash"] == versions[0]["knowledge_pack_hash"]

    reviewer = token(client, "reviewer@orbita.demo")
    reviewer_headers = {"Authorization": f"Bearer {reviewer}"}
    stale = client.post(
        f"/api/v1/reviews/{first['review']['id']}/decisions",
        headers=reviewer_headers,
        json={"action": "APPROVE"},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "STALE_VERSION"


def test_creator_cannot_read_another_creators_version_history(client):
    creator_one = token(client)
    creator_one_headers = {"Authorization": f"Bearer {creator_one}"}
    created = client.post(
        "/api/v1/submissions",
        headers=creator_one_headers,
        data={
            "title": "Private history access test",
            "channel": "direct_web",
            "locale": "en-IN",
            "geography": "IN",
            "audience": "consumer",
            "offer_id": "OFFER-ORBITA-OCT-NOV-2026",
            "publication_at": "2026-11-10T12:00:00+05:30",
        },
        files={"file": ("private.txt", b"A simple ORBITA product introduction.", "text/plain")},
    )
    assert created.status_code == 200, created.text
    submission_id = created.json()["submission"]["id"]

    creator_two = token(client, "creator.two@orbita.demo", "Second-Creator-Password")
    denied = client.get(
        f"/api/v1/submissions/{submission_id}/history",
        headers={"Authorization": f"Bearer {creator_two}"},
    )
    assert denied.status_code == 404


def test_image_submission_returns_polygon_regions_and_measurement_status(client):
    from pathlib import Path

    creator = token(client)
    headers = {"Authorization": f"Bearer {creator}"}
    image_path = Path(__file__).parents[2] / "fixtures" / "images" / "social_supported_clean.png"
    response = client.post(
        "/api/v1/submissions",
        headers=headers,
        data={
            "title": "Visual evidence geometry check",
            "channel": "social",
            "locale": "en-IN",
            "geography": "IN",
            "audience": "consumer",
            "offer_id": "OFFER-ORBITA-OCT-NOV-2026",
            "publication_at": "2026-11-08T12:00:00+05:30",
        },
        files={"file": (image_path.name, image_path.read_bytes(), "image/png")},
    )
    assert response.status_code == 200, response.text
    version = response.json()["content_version"]
    metadata = next(region for region in version["regions"] if region["kind"] == "image_metadata")
    assert metadata["width"] > 0 and metadata["height"] > 0
    line_regions = [region for region in version["regions"] if region["kind"] == "ocr_line"]
    for region in line_regions:
        assert region["polygon"]
        assert region["normalised_bbox"]
        assert region["contrast"]["status"] in {"PASS", "FAIL", "UNMEASURABLE"}
    assert any(finding["code"] == "VISUAL_ASSET_MANUAL_REVIEW" for finding in response.json()["findings"])
