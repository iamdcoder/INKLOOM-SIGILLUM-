import pytest
from uuid import uuid4
from sqlalchemy import select
from fastapi.testclient import TestClient
from apps.api.main import app

@pytest.fixture(scope="module")
def client():
    from sigillum.api import routes

    original_scanner = routes.scan_upload_bytes
    routes.scan_upload_bytes = lambda _payload: {
        "status": "CLEAN",
        "engine": "test-clamav",
        "scanned_at": "2026-11-09T00:00:00+00:00",
        "signature": None,
    }
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        routes.scan_upload_bytes = original_scanner

def _brand_record_id(db, user_id):
    from sigillum.infrastructure.database import models
    membership = db.scalar(select(models.Membership).where(models.Membership.user_id == user_id, models.Membership.is_active.is_(True)))
    return membership.brand_id


def token(client, email="creator@orbita.demo", password="ChangeMe-Local-Only"):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]

def test_health_endpoints(client):
    assert client.get("/health/live").json()["status"] == "ok"
    readiness = client.get("/health/ready")
    assert readiness.status_code == 200
    assert readiness.json()["status"] == "ready"
    assert readiness.json()["database"] == "connected"
    assert readiness.json()["database_schema"] == "current"
    assert readiness.json()["migration_revision"] == readiness.json()["expected_migration_revision"]
    assert readiness.json()["database_dialect"] in {"sqlite", "postgresql"}
    assert readiness.json()["storage"] == "available"
    assert readiness.json()["storage_driver"] == "local_filesystem"


def test_storage_outage_is_not_misreported_as_a_parse_failure(client, monkeypatch):
    from sigillum.api import routes
    from sigillum.infrastructure.storage import StorageUnavailable

    class UnavailableStorage:
        def put_bytes(self, key, data, content_type=None):
            raise StorageUnavailable("simulated object store outage")

    monkeypatch.setattr(routes, "get_storage", lambda settings: UnavailableStorage())

    creator = token(client)
    headers = {"Authorization": f"Bearer {creator}"}
    response = client.post(
        "/api/v1/submissions",
        headers=headers,
        data={
            "title": "Storage failure state",
            "channel": "direct_web",
            "locale": "en-IN",
            "geography": "IN",
            "audience": "consumer",
            "offer_id": "OFFER-ORBITA-OCT-NOV-2026",
            "publication_at": "2026-11-10T12:00:00+05:30",
        },
        files={"file": ("storage-outage.txt", b"A simple ORBITA product description.", "text/plain")},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "STORAGE_UNAVAILABLE"
    listing = client.get("/api/v1/submissions", headers=headers)
    assert listing.status_code == 200
    assert all(item["title"] != "Storage failure state" for item in listing.json())


def test_uploaded_original_download_is_authenticated_and_hash_verified(client):
    from hashlib import sha256

    from apps.api.main import SessionLocal
    from sigillum.config import get_settings
    from sigillum.infrastructure.database import models
    from sigillum.infrastructure.storage import get_storage

    creator = token(client)
    headers = {"Authorization": f"Bearer {creator}"}
    original = b"A calm product description for the ORBITA Air One."
    submitted = client.post(
        "/api/v1/submissions",
        headers=headers,
        data={
            "title": "Original content download integrity",
            "channel": "direct_web",
            "locale": "en-IN",
            "geography": "IN",
            "audience": "consumer",
            "offer_id": "OFFER-ORBITA-OCT-NOV-2026",
            "publication_at": "2026-11-10T12:00:00+05:30",
        },
        files={"file": ("original.txt", original, "text/plain")},
    )
    assert submitted.status_code == 200, submitted.text
    version_id = submitted.json()["content_version"]["id"]

    downloaded = client.get(
        f"/api/v1/content-versions/{version_id}/download",
        headers=headers,
    )
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.content == original
    assert sha256(downloaded.content).hexdigest() == submitted.json()["content_version"]["sha256"]
    assert downloaded.headers["x-content-type-options"] == "nosniff"
    assert downloaded.headers["cache-control"] == "private, no-store"

    with SessionLocal() as db:
        actor = db.scalar(select(models.User).where(models.User.email == "creator@orbita.demo"))
        from sigillum.infrastructure.database.session import set_database_scope
        set_database_scope(db, user_id=actor.id)
        brand_record_id = _brand_record_id(db, actor.id)
        set_database_scope(db, user_id=actor.id, tenant_id="tenant_demo", brand_id="brand_orbita_demo", brand_record_id=brand_record_id, membership_role="creator")
        version = db.get(models.ContentVersion, version_id)
        storage_key = version.storage_key
    get_storage(get_settings()).put_bytes(storage_key, b"tampered original", "text/plain")

    tampered = client.get(
        f"/api/v1/content-versions/{version_id}/download",
        headers=headers,
    )
    assert tampered.status_code == 503
    assert tampered.json()["detail"]["code"] == "ARTEFACT_INTEGRITY_FAILURE"


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
    creator = token(client, "creator@orbita.demo")
    reviewer = token(client, "reviewer@orbita.demo")
    creator_headers = {"Authorization": f"Bearer {creator}"}
    reviewer_headers = {"Authorization": f"Bearer {reviewer}"}
    response = client.post(
        "/api/v1/submissions",
        headers=creator_headers,
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
        headers=reviewer_headers,
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
            db.flush()
        else:
            second.password_hash = hash_password("Second-Creator-Password")
        from sigillum.infrastructure.database.session import set_database_scope
        set_database_scope(db, user_id=second.id, tenant_id="tenant_demo", brand_id="brand_orbita_demo", membership_role="administrator")
        brand = db.scalar(select(models.Brand).where(models.Brand.tenant_id == "tenant_demo", models.Brand.external_id == "brand_orbita_demo"))
        set_database_scope(db, user_id=second.id, tenant_id="tenant_demo", brand_id="brand_orbita_demo", brand_record_id=brand.id, membership_role="administrator")
        existing_membership = db.scalar(select(models.Membership).where(models.Membership.user_id == second.id, models.Membership.brand_id == brand.id))
        if not existing_membership:
            db.add(models.Membership(user_id=second.id, tenant_id="tenant_demo", brand_id=brand.id, role="creator", is_active=True))
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
    assert after["content_version"]["parent_version_id"] == before["content_version"]["id"]
    assert after["content_version"]["scan_status"] == "CLEAN"
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
    assert versions[0]["analysis_config_version"] == "deterministic-temporal-rrf-v2"
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


def test_submission_intended_use_is_versioned_and_invalid_use_is_rejected(client):
    creator = token(client)
    headers = {"Authorization": f"Bearer {creator}"}
    fields = {
        "title": "Asset policy context",
        "channel": "social",
        "locale": "en-IN",
        "geography": "IN",
        "audience": "consumer",
        "offer_id": "",
        "intended_use": "social_ad",
        "publication_at": "2026-11-12T12:00:00+05:30",
    }
    submitted = client.post(
        "/api/v1/submissions",
        headers=headers,
        data=fields,
        files={"file": ("asset-policy-context.txt", b"A simple campaign description.", "text/plain")},
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["submission"]["intended_use"] == "social_ad"

    invalid_fields = {**fields, "intended_use": "unrestricted_everywhere"}
    rejected = client.post(
        "/api/v1/submissions",
        headers=headers,
        data=invalid_fields,
        files={"file": ("invalid-use.txt", b"A simple campaign description.", "text/plain")},
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["code"] == "INVALID_INTENDED_USE"


def _create_submission_draft(client, headers, **overrides):
    payload = {
        "title": "Resumable Phase 05 draft",
        "channel": "direct_web",
        "locale": "en-IN",
        "geography": "IN",
        "audience": "consumer",
        "offer_id": "OFFER-ORBITA-OCT-NOV-2026",
        "intended_use": "general",
        "product_scope": "ORBITA Air One",
        "campaign_scope": "Winter launch",
        "context_note": "Saved before choosing the file.",
        "publication_at": "2026-11-12T12:00:00+05:30",
    }
    payload.update(overrides)
    response = client.post("/api/v1/submissions/drafts", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_resumable_draft_upload_is_idempotent_and_creates_durable_review_job(client):
    from apps.api.main import SessionLocal
    from sigillum.infrastructure.database import models
    from sigillum.infrastructure.database.session import set_database_scope

    creator = token(client)
    headers = {"Authorization": f"Bearer {creator}"}
    draft = _create_submission_draft(client, headers)
    assert draft["status"] == "DRAFT"
    assert draft["product_scope"] == "ORBITA Air One"

    file_bytes = b"The ORBITA Air One delivers clear, accurate product information."
    upload_key = f"phase05-upload-{uuid4().hex}"
    request_headers = {**headers, "Idempotency-Key": upload_key}
    first = client.post(
        f"/api/v1/submissions/{draft['id']}/content",
        headers=request_headers,
        files={"file": ("phase05-copy.txt", file_bytes, "text/plain")},
    )
    assert first.status_code == 200, first.text
    result = first.json()
    version = result["content_version"]
    assert version["version_number"] == 1
    assert version["scan_status"] == "CLEAN"
    assert len(version["sha256"]) == 64

    repeated = client.post(
        f"/api/v1/submissions/{draft['id']}/content",
        headers=request_headers,
        files={"file": ("phase05-copy.txt", file_bytes, "text/plain")},
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["content_version"]["id"] == version["id"]
    assert repeated.json()["review"]["id"] == result["review"]["id"]

    conflicting = client.post(
        f"/api/v1/submissions/{draft['id']}/content",
        headers=request_headers,
        files={"file": ("phase05-copy.txt", file_bytes + b" updated", "text/plain")},
    )
    assert conflicting.status_code == 409
    assert conflicting.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    duplicate = client.post(
        "/api/v1/submissions/duplicate-check",
        headers=headers,
        json={"sha256": version["sha256"]},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True
    assert duplicate.json()["matches"][0]["version_id"] == version["id"]

    with SessionLocal() as db:
        actor = db.scalar(select(models.User).where(models.User.email == "creator@orbita.demo"))
        set_database_scope(db, user_id=actor.id)
        job = db.scalar(select(models.ReviewJob).where(models.ReviewJob.content_version_id == version["id"]))
        assert job is not None
        assert job.status == "COMPLETED"
        assert job.context_snapshot["content_sha256"] == version["sha256"]
        upload_request = db.scalar(
            select(models.SubmissionUploadRequest).where(
                models.SubmissionUploadRequest.idempotency_key == upload_key
            )
        )
        assert upload_request is not None
        assert upload_request.status == "COMPLETED"
        assert upload_request.review_id == result["review"]["id"]
        review_context = db.get(models.ReviewRun, upload_request.review_id)
        assert review_context is not None
        assert review_context.status == "COMPLETED"
        assert review_context.content_hash == version["sha256"]


def test_draft_context_can_be_updated_and_cancelled(client):
    creator = token(client)
    headers = {"Authorization": f"Bearer {creator}"}
    draft = _create_submission_draft(client, headers)
    payload = {
        "title": "Updated draft context",
        "channel": "social",
        "locale": "en-IN",
        "geography": "IN",
        "audience": "consumer",
        "offer_id": None,
        "intended_use": "social_ad",
        "product_scope": "ORBITA Air One",
        "campaign_scope": "Social teaser",
        "context_note": "Updated before upload.",
        "publication_at": "2026-11-13T09:00:00+05:30",
    }
    updated = client.patch(
        f"/api/v1/submissions/{draft['id']}/draft",
        headers=headers,
        json=payload,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["title"] == "Updated draft context"
    assert updated.json()["channel"] == "social"
    cancelled = client.delete(f"/api/v1/submissions/{draft['id']}", headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"


def test_invalid_upload_is_rejected_and_draft_can_be_retried(client):
    creator = token(client)
    headers = {"Authorization": f"Bearer {creator}"}
    draft = _create_submission_draft(client, headers)
    rejected = client.post(
        f"/api/v1/submissions/{draft['id']}/content",
        headers={**headers, "Idempotency-Key": f"phase05-invalid-{uuid4().hex}"},
        files={"file": ("wrong-signature.png", b"not a PNG image", "image/png")},
    )
    assert rejected.status_code == 415
    assert rejected.json()["detail"]["code"] == "INVALID_UPLOAD"
    latest = client.get(f"/api/v1/submissions/{draft['id']}", headers=headers)
    assert latest.status_code == 200
    assert latest.json()["status"] == "DRAFT"
    assert latest.json()["current_version_id"] is None


def test_malware_detection_blocks_submission_before_storage(client, monkeypatch):
    from sigillum.api import routes

    creator = token(client)
    headers = {"Authorization": f"Bearer {creator}"}
    draft = _create_submission_draft(client, headers)
    monkeypatch.setattr(
        routes,
        "scan_upload_bytes",
        lambda _payload: {
            "status": "INFECTED",
            "engine": "test-clamav",
            "scanned_at": "2026-11-09T00:00:00+00:00",
            "signature": "Eicar-Test-Signature",
        },
    )
    rejected = client.post(
        f"/api/v1/submissions/{draft['id']}/content",
        headers={**headers, "Idempotency-Key": f"phase05-malware-{uuid4().hex}"},
        files={"file": ("malicious-test.txt", b"This test payload is marked infected by the injected scanner.", "text/plain")},
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["code"] == "MALWARE_DETECTED"
    latest = client.get(f"/api/v1/submissions/{draft['id']}", headers=headers)
    assert latest.status_code == 200
    assert latest.json()["status"] == "DRAFT"
    assert latest.json()["current_version_id"] is None


def test_scanner_outage_fails_closed_without_creating_a_content_version(client, monkeypatch):
    from sigillum.api import routes

    creator = token(client)
    headers = {"Authorization": f"Bearer {creator}"}
    draft = _create_submission_draft(client, headers)
    monkeypatch.setattr(
        routes,
        "scan_upload_bytes",
        lambda _payload: {"status": "UNAVAILABLE", "engine": "test-clamav", "scanned_at": None, "signature": None},
    )
    rejected = client.post(
        f"/api/v1/submissions/{draft['id']}/content",
        headers={**headers, "Idempotency-Key": f"phase05-scan-outage-{uuid4().hex}"},
        files={"file": ("scanner-outage.txt", b"A simple valid text file.", "text/plain")},
    )
    assert rejected.status_code == 503
    assert rejected.json()["detail"]["code"] == "MALWARE_SCANNER_UNAVAILABLE"
    latest = client.get(f"/api/v1/submissions/{draft['id']}", headers=headers)
    assert latest.status_code == 200
    assert latest.json()["status"] == "DRAFT"
    assert latest.json()["current_version_id"] is None


def test_jpeg_upload_is_scanned_versioned_and_reviewed(client):
    from pathlib import Path

    creator = token(client)
    headers = {"Authorization": f"Bearer {creator}"}
    path = Path(__file__).parents[2] / "fixtures" / "images" / "social_unsupported_claim.jpg"
    response = client.post(
        "/api/v1/submissions",
        headers=headers,
        data={
            "title": "JPEG image intake",
            "channel": "social",
            "locale": "en-IN",
            "geography": "IN",
            "audience": "consumer",
            "offer_id": "OFFER-ORBITA-OCT-NOV-2026",
            "publication_at": "2026-11-12T12:00:00+05:30",
        },
        files={"file": (path.name, path.read_bytes(), "image/jpeg")},
    )
    assert response.status_code == 200, response.text
    content = response.json()["content_version"]
    assert content["mime_type"] == "image/jpeg"
    assert content["scan_status"] == "CLEAN"
    assert len(content["sha256"]) == 64
    assert response.json()["review"]["status"] == "COMPLETED"


def test_staged_upload_without_header_has_deterministic_retry_key(client):
    creator = token(client)
    headers = {"Authorization": f"Bearer {creator}"}
    draft = _create_submission_draft(client, headers)
    payload = b"The ORBITA Air One product description is clear and accurate."

    first = client.post(
        f"/api/v1/submissions/{draft['id']}/content",
        headers=headers,
        files={"file": ("idempotent-no-header.txt", payload, "text/plain")},
    )
    assert first.status_code == 200, first.text
    second = client.post(
        f"/api/v1/submissions/{draft['id']}/content",
        headers=headers,
        files={"file": ("idempotent-no-header.txt", payload, "text/plain")},
    )
    assert second.status_code == 200, second.text
    assert second.json()["content_version"]["id"] == first.json()["content_version"]["id"]


def test_declared_mime_must_match_detected_file_type(client):
    creator = token(client)
    headers = {"Authorization": f"Bearer {creator}"}
    draft = _create_submission_draft(client, headers)
    response = client.post(
        f"/api/v1/submissions/{draft['id']}/content",
        headers=headers,
        files={"file": ("not-an-image.txt", b"Valid UTF-8 plain text.", "image/jpeg")},
    )
    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "INVALID_UPLOAD"
    assert "MIME_TYPE_MISMATCH" in response.json()["detail"]["message"]


def test_scanner_exception_fails_closed_and_keeps_draft(client, monkeypatch):
    from sigillum.api import routes

    creator = token(client)
    headers = {"Authorization": f"Bearer {creator}"}
    draft = _create_submission_draft(client, headers)

    def raise_scanner(_payload):
        raise ConnectionError("scanner transport failed")

    monkeypatch.setattr(routes, "scan_upload_bytes", raise_scanner)
    response = client.post(
        f"/api/v1/submissions/{draft['id']}/content",
        headers=headers,
        files={"file": ("scanner-exception.txt", b"A valid text file.", "text/plain")},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "MALWARE_SCANNER_UNAVAILABLE"
    latest = client.get(f"/api/v1/submissions/{draft['id']}", headers=headers)
    assert latest.status_code == 200
    assert latest.json()["status"] == "DRAFT"
    assert latest.json()["current_version_id"] is None


def test_legacy_single_request_upload_is_idempotent_with_header(client):
    creator = token(client)
    headers = {"Authorization": f"Bearer {creator}", "Idempotency-Key": f"legacy-phase05-{uuid4().hex}"}
    form = {
        "title": "Legacy idempotency check",
        "channel": "direct_web",
        "locale": "en-IN",
        "geography": "IN",
        "audience": "consumer",
        "offer_id": "OFFER-ORBITA-OCT-NOV-2026",
        "publication_at": "2026-11-12T12:00:00+05:30",
    }
    payload = b"A simple repeatable direct submission test."
    first = client.post(
        "/api/v1/submissions",
        headers=headers,
        data=form,
        files={"file": ("legacy-idempotent.txt", payload, "text/plain")},
    )
    assert first.status_code == 200, first.text
    second = client.post(
        "/api/v1/submissions",
        headers=headers,
        data=form,
        files={"file": ("legacy-idempotent.txt", payload, "text/plain")},
    )
    assert second.status_code == 200, second.text
    assert second.json()["submission"]["id"] == first.json()["submission"]["id"]
    assert second.json()["content_version"]["id"] == first.json()["content_version"]["id"]


def test_non_creator_roles_cannot_create_submission_drafts(client):
    reviewer = token(client, email="reviewer@orbita.demo")
    response = client.post(
        "/api/v1/submissions/drafts",
        headers={"Authorization": f"Bearer {reviewer}"},
        json={
            "title": "Reviewer must not submit",
            "channel": "direct_web",
            "locale": "en-IN",
            "geography": "IN",
            "audience": "consumer",
            "offer_id": "OFFER-ORBITA-OCT-NOV-2026",
            "intended_use": "general",
            "publication_at": "2026-11-12T12:00:00+05:30",
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ACCESS_DENIED"


def test_pdf_page_preview_is_authenticated_hash_bound_and_uses_extraction_geometry(client):
    import fitz

    creator = token(client)
    headers = {"Authorization": f"Bearer {creator}"}
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((72, 120), "Saves up to 40% on ORBITA Air One.", fontsize=22)
    page.set_rotation(90)
    payload = document.tobytes()
    document.close()

    submitted = client.post(
        "/api/v1/submissions",
        headers=headers,
        data={
            "title": "PDF page preview evidence",
            "channel": "direct_web",
            "locale": "en-IN",
            "geography": "IN",
            "audience": "consumer",
            "offer_id": "OFFER-ORBITA-OCT-NOV-2026",
            "publication_at": "2026-11-10T12:00:00+05:30",
        },
        files={"file": ("preview.pdf", payload, "application/pdf")},
    )
    assert submitted.status_code == 200, submitted.text
    content_version = submitted.json()["content_version"]
    page_region = next(item for item in content_version["regions"] if item["kind"] == "pdf_page")
    text_region = next(item for item in content_version["regions"] if item["kind"] == "pdf_text_line")
    assert page_region["rotation_degrees"] == 90
    assert text_region["page_dimensions"]["width"] == page_region["width"]

    preview = client.get(
        f"/api/v1/content-versions/{content_version['id']}/pages/1/preview",
        headers=headers,
    )
    assert preview.status_code == 200, preview.text
    assert preview.headers["content-type"].startswith("image/png")
    assert int(preview.headers["x-page-width"]) == page_region["width"]
    assert int(preview.headers["x-page-height"]) == page_region["height"]
    assert preview.content.startswith(b"\x89PNG\r\n\x1a\n")

    unauthenticated = client.get(
        f"/api/v1/content-versions/{content_version['id']}/pages/1/preview"
    )
    assert unauthenticated.status_code == 401
