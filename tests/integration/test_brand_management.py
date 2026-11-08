from uuid import uuid4

import pytest
from sqlalchemy import select
from fastapi.testclient import TestClient

from apps.api.main import SessionLocal
from sigillum.infrastructure.database import models
from sigillum.infrastructure.database.session import set_database_scope
from sigillum.infrastructure.security import hash_password


@pytest.fixture(scope="module")
def client():
    from apps.api.main import app
    with TestClient(app) as test_client:
        yield test_client


def _create_user(email: str, role: str, tenant_id: str, password: str = "Pack-Owner-Password"):
    with SessionLocal() as db:
        user = models.User(
            email=email,
            display_name="Knowledge Pack Test User",
            role=role,
            password_hash=hash_password(password),
            tenant_id=tenant_id,
        )
        db.add(user)
        db.flush()
        set_database_scope(
            db,
            user_id=user.id,
            tenant_id=tenant_id,
            brand_id="brand_orbita_demo",
            membership_role="administrator",
        )
        tenant = db.get(models.Tenant, tenant_id)
        if tenant is None:
            db.add(models.Tenant(id=tenant_id, name=f"Test workspace {tenant_id}", is_active=True))
            db.flush()
        brand = db.scalar(
            select(models.Brand).where(
                models.Brand.tenant_id == tenant_id,
                models.Brand.external_id == "brand_orbita_demo",
            )
        )
        if brand is None:
            brand = models.Brand(tenant_id=tenant_id, external_id="brand_orbita_demo", name="ORBITA", is_active=True)
            db.add(brand)
            db.flush()
        db.add(models.Membership(user_id=user.id, tenant_id=tenant_id, brand_id=brand.id, role=role, is_active=True))
        db.commit()
        return user.id


def _token(client, email: str, password: str = "Pack-Owner-Password") -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_brand_owner_can_draft_validate_publish_and_version_pack(client):
    tenant_id = f"tenant_pack_{uuid4().hex[:12]}"
    owner_email = f"pack.owner.{uuid4().hex[:10]}@orbita.demo"
    _create_user(owner_email, "brand_owner", tenant_id)
    headers = {"Authorization": f"Bearer {_token(client, owner_email)}"}

    management = client.get("/api/v1/brands/current/management", headers=headers)
    assert management.status_code == 200, management.text
    original = management.json()
    assert original["active_version"]["version_id"] == "v0001"

    upload_fields = {
        "title": "Pack snapshot before publication",
        "channel": "direct_web",
        "locale": "en-IN",
        "geography": "IN",
        "audience": "consumer",
        "offer_id": "OFFER-ORBITA-OCT-NOV-2026",
        "publication_at": "2026-11-08T12:00:00+05:30",
    }
    before_review = client.post(
        "/api/v1/submissions",
        headers=headers,
        data=upload_fields,
        files={"file": ("before.txt", b"A measured product introduction.", "text/plain")},
    )
    assert before_review.status_code == 200, before_review.text
    before_hash = before_review.json()["review"]["knowledge_pack_hash"]
    assert before_hash == original["active_version"]["fingerprint"]

    created = client.post("/api/v1/brands/current/drafts", headers=headers)
    assert created.status_code == 200, created.text
    draft = created.json()
    updated_brand = dict(draft["snapshot"]["brand"])
    updated_brand["description"] = "Owner-approved controlled update for an isolated integration test."

    saved = client.put(
        f"/api/v1/brands/current/drafts/{draft['draft_id']}/section",
        headers=headers,
        json={"section": "brand", "content": updated_brand},
    )
    assert saved.status_code == 200, saved.text

    validation = client.post(
        f"/api/v1/brands/current/drafts/{draft['draft_id']}/validate",
        headers=headers,
    )
    assert validation.status_code == 200, validation.text
    assert validation.json()["valid"] is True

    published = client.post(
        f"/api/v1/brands/current/drafts/{draft['draft_id']}/publish",
        headers=headers,
    )
    assert published.status_code == 200, published.text
    published_payload = published.json()
    assert published_payload["version_id"] == "v0002"
    assert published_payload["pack_version"] == "1.0.1"
    assert published_payload["fingerprint"] != original["active_version"]["fingerprint"]

    latest = client.get("/api/v1/brands/current/management", headers=headers)
    assert latest.status_code == 200
    latest_payload = latest.json()
    assert latest_payload["snapshot"]["brand"]["description"] == updated_brand["description"]
    assert latest_payload["active_version"]["version_id"] == "v0002"
    assert len(latest_payload["versions"]) == 2

    # Publishing changes future review context without rewriting an earlier review snapshot.
    after_review = client.post(
        "/api/v1/submissions",
        headers=headers,
        data={**upload_fields, "title": "Pack snapshot after publication"},
        files={"file": ("after.txt", b"A measured product introduction.", "text/plain")},
    )
    assert after_review.status_code == 200, after_review.text
    after_hash = after_review.json()["review"]["knowledge_pack_hash"]
    assert after_hash == published_payload["fingerprint"]
    assert after_hash != before_hash

    events = client.get("/api/v1/audit", headers=headers)
    assert events.status_code == 200
    event_types = {item["event_type"] for item in events.json()}
    assert "BRAND_KNOWLEDGE_DRAFT_CREATED" in event_types
    assert "BRAND_KNOWLEDGE_DRAFT_SECTION_UPDATED" in event_types
    assert "BRAND_KNOWLEDGE_DRAFT_VALIDATED" in event_types
    assert "BRAND_KNOWLEDGE_PACK_PUBLISHED" in event_types


def test_only_brand_owner_can_mutate_knowledge_pack(client):
    creator = client.post("/api/v1/auth/login", json={"email": "creator@orbita.demo", "password": "ChangeMe-Local-Only"})
    assert creator.status_code == 200
    headers = {"Authorization": f"Bearer {creator.json()['access_token']}"}

    assert client.get("/api/v1/brands/current/management", headers=headers).status_code == 403
    assert client.post("/api/v1/brands/current/drafts", headers=headers).status_code == 403


def test_knowledge_packs_are_brand_scoped_within_one_tenant(client):
    tenant_id = f"tenant_multi_pack_{uuid4().hex[:10]}"
    owner_email = f"multi.pack.owner.{uuid4().hex[:8]}@orbita.demo"
    user_id = _create_user(owner_email, "brand_owner", tenant_id)
    with SessionLocal() as db:
        brand = models.Brand(tenant_id=tenant_id, external_id="brand_second", name="SECOND BRAND", is_active=True)
        db.add(brand)
        db.flush()
        db.add(models.Membership(user_id=user_id, tenant_id=tenant_id, brand_id=brand.id, role="brand_owner", is_active=True))
        db.commit()

    second_login = client.post("/api/v1/auth/login", json={"email": owner_email, "password": "Pack-Owner-Password", "brand_id": "brand_second"})
    assert second_login.status_code == 200, second_login.text
    second_headers = {"Authorization": f"Bearer {second_login.json()['access_token']}"}
    second_management = client.get("/api/v1/brands/current/management", headers=second_headers)
    assert second_management.status_code == 200, second_management.text
    second_pack = second_management.json()
    assert second_pack["brand"]["brand_id"] == "brand_second"
    assert second_pack["brand"]["brand_name"] == "SECOND BRAND"
    assert second_pack["snapshot"]["facts"] == []
    assert second_pack["snapshot"]["policies"] == []
    assert second_pack["snapshot"]["assets"]["approved_assets"] == []

    create_draft = client.post("/api/v1/brands/current/drafts", headers=second_headers)
    assert create_draft.status_code == 200, create_draft.text
    draft_id = create_draft.json()["draft_id"]
    changed = dict(create_draft.json()["snapshot"]["brand"])
    changed["description"] = "A separately governed brand workspace."
    updated = client.put(
        f"/api/v1/brands/current/drafts/{draft_id}/section",
        headers=second_headers,
        json={"section": "brand", "content": changed},
    )
    assert updated.status_code == 200, updated.text
    assert client.post(f"/api/v1/brands/current/drafts/{draft_id}/validate", headers=second_headers).json()["valid"] is True
    published = client.post(f"/api/v1/brands/current/drafts/{draft_id}/publish", headers=second_headers)
    assert published.status_code == 200, published.text

    orbita_login = client.post("/api/v1/auth/login", json={"email": owner_email, "password": "Pack-Owner-Password", "brand_id": "brand_orbita_demo"})
    assert orbita_login.status_code == 200, orbita_login.text
    orbita_headers = {"Authorization": f"Bearer {orbita_login.json()['access_token']}"}
    orbita_management = client.get("/api/v1/brands/current/management", headers=orbita_headers)
    assert orbita_management.status_code == 200
    assert orbita_management.json()["brand"]["brand_id"] == "brand_orbita_demo"
    assert orbita_management.json()["snapshot"]["facts"]
    assert orbita_management.json()["brand"]["description"] != "A separately governed brand workspace."
    cross_brand_draft = client.get(f"/api/v1/brands/current/drafts/{draft_id}", headers=orbita_headers)
    assert cross_brand_draft.status_code == 404


def test_source_registry_and_private_asset_upload_approval_flow(client):
    from io import BytesIO
    from PIL import Image

    tenant_id = f"tenant_source_asset_{uuid4().hex[:10]}"
    owner_email = f"asset.owner.{uuid4().hex[:8]}@orbita.demo"
    _create_user(owner_email, "brand_owner", tenant_id)
    headers = {"Authorization": f"Bearer {_token(client, owner_email)}"}
    created = client.post("/api/v1/brands/current/drafts", headers=headers)
    assert created.status_code == 200, created.text
    draft_id = created.json()["draft_id"]

    source_response = client.post(
        f"/api/v1/brands/current/drafts/{draft_id}/sources",
        headers=headers,
        json={
            "name": "Approved product specification",
            "source_type": "product_specification",
            "version": 1,
            "reference_text": "Product model ORBITA Air One; official reference specification for test fixture.",
            "valid_from": "2026-11-01T00:00:00+05:30",
        },
    )
    assert source_response.status_code == 200, source_response.text
    source_id = source_response.json()["source"]["source_id"]
    source_decision = client.post(
        f"/api/v1/brands/current/drafts/{draft_id}/records/source/{source_id}/decision",
        headers=headers,
        json={"status": "approved", "reason": "Reviewed against the synthetic product specification."},
    )
    assert source_decision.status_code == 200, source_decision.text

    image_bytes = BytesIO()
    Image.new("RGB", (32, 32), (20, 140, 130)).save(image_bytes, format="PNG")
    png_payload = image_bytes.getvalue()
    upload = client.post(
        f"/api/v1/brands/current/drafts/{draft_id}/assets",
        headers=headers,
        data={"name": "Campaign logo test", "kind": "logo"},
        files={"file": ("campaign.png", png_payload, "image/png")},
    )
    assert upload.status_code == 200, upload.text
    uploaded_asset = upload.json()["asset"]
    asset_id = uploaded_asset["asset_id"]
    assert uploaded_asset["status"] == "draft"

    preview = client.get(f"/api/v1/brands/current/drafts/{draft_id}/assets/{asset_id}", headers=headers)
    assert preview.status_code == 200
    assert preview.content == png_payload
    assert preview.headers["x-content-type-options"] == "nosniff"

    asset_decision = client.post(
        f"/api/v1/brands/current/drafts/{draft_id}/records/asset/{asset_id}/decision",
        headers=headers,
        json={"status": "approved", "reason": "Brand owner approved the uploaded campaign logo."},
    )
    assert asset_decision.status_code == 200, asset_decision.text

    validation = client.post(f"/api/v1/brands/current/drafts/{draft_id}/validate", headers=headers)
    assert validation.status_code == 200, validation.text
    assert validation.json()["valid"] is True, validation.json()
    publish = client.post(f"/api/v1/brands/current/drafts/{draft_id}/publish", headers=headers)
    assert publish.status_code == 200, publish.text

    active_asset = client.get(f"/api/v1/brands/current/assets/{asset_id}", headers=headers)
    assert active_asset.status_code == 200, active_asset.text
    assert active_asset.content == png_payload

    # Published asset bytes remain bound to the exact owner-approved upload hash.
    from sigillum.api import routes as api_routes
    api_routes.get_storage(api_routes.settings).put_bytes(
        uploaded_asset["storage_key"], b"tampered-after-publication", "image/png"
    )
    corrupted_asset = client.get(f"/api/v1/brands/current/assets/{asset_id}", headers=headers)
    assert corrupted_asset.status_code == 409
    assert corrupted_asset.json()["detail"]["code"] == "ASSET_INTEGRITY_FAILED"

    management = client.get("/api/v1/brands/current/management", headers=headers)
    records = management.json()["snapshot"]["sources"]["sources"]
    saved_source = next(item for item in records if item["source_id"] == source_id)
    assert saved_source["status"] == "approved"
    assert saved_source["approved_by"]
    saved_asset = next(item for item in management.json()["snapshot"]["assets"]["approved_assets"] if item["asset_id"] == asset_id)
    assert saved_asset["status"] == "approved"
    assert saved_asset["approved_by"]



def test_uploaded_asset_integrity_is_rechecked_for_preview_and_publication(client):
    from io import BytesIO
    from PIL import Image
    from sigillum.api import routes

    tenant_id = f"tenant_asset_hash_{uuid4().hex[:10]}"
    owner_email = f"asset.hash.{uuid4().hex[:8]}@orbita.demo"
    _create_user(owner_email, "brand_owner", tenant_id)
    headers = {"Authorization": f"Bearer {_token(client, owner_email)}"}
    created = client.post("/api/v1/brands/current/drafts", headers=headers)
    assert created.status_code == 200, created.text
    draft_id = created.json()["draft_id"]

    image_bytes = BytesIO()
    Image.new("RGB", (24, 24), (22, 120, 165)).save(image_bytes, format="PNG")
    original = image_bytes.getvalue()
    upload = client.post(
        f"/api/v1/brands/current/drafts/{draft_id}/assets",
        headers=headers,
        data={"name": "Integrity test asset", "kind": "logo"},
        files={"file": ("integrity.png", original, "image/png")},
    )
    assert upload.status_code == 200, upload.text
    asset = upload.json()["asset"]
    decision = client.post(
        f"/api/v1/brands/current/drafts/{draft_id}/records/asset/{asset['asset_id']}/decision",
        headers=headers,
        json={"status": "approved", "reason": "Approved before integrity regression."},
    )
    assert decision.status_code == 200, decision.text

    # Simulate a storage-layer alteration after the owner approved the exact bytes.
    storage = routes.get_storage(routes.settings)
    storage.put_bytes(asset["storage_key"], b"tampered-after-approval", "image/png")

    preview = client.get(
        f"/api/v1/brands/current/drafts/{draft_id}/assets/{asset['asset_id']}",
        headers=headers,
    )
    assert preview.status_code == 409
    assert preview.json()["detail"]["code"] == "ASSET_INTEGRITY_FAILED"

    validation = client.post(f"/api/v1/brands/current/drafts/{draft_id}/validate", headers=headers)
    assert validation.status_code == 200, validation.text
    assert validation.json()["valid"] is False
    assert any(item["code"] == "ASSET_HASH_MISMATCH" for item in validation.json()["errors"])

def test_brand_asset_upload_rejects_svg_and_non_image_payload(client):
    tenant_id = f"tenant_asset_reject_{uuid4().hex[:10]}"
    owner_email = f"asset.reject.{uuid4().hex[:8]}@orbita.demo"
    _create_user(owner_email, "brand_owner", tenant_id)
    headers = {"Authorization": f"Bearer {_token(client, owner_email)}"}
    created = client.post("/api/v1/brands/current/drafts", headers=headers)
    draft_id = created.json()["draft_id"]

    for filename, content, mime in [
        ("bad.svg", b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", "image/svg+xml"),
        ("fake.png", b"not really a png", "image/png"),
    ]:
        response = client.post(
            f"/api/v1/brands/current/drafts/{draft_id}/assets",
            headers=headers,
            data={"name": "Invalid upload", "kind": "logo"},
            files={"file": (filename, content, mime)},
        )
        assert response.status_code == 422, response.text


def test_non_owner_cannot_register_or_decide_knowledge_sources(client):
    tenant_id = f"tenant_source_rbac_{uuid4().hex[:10]}"
    owner_email = f"source.owner.{uuid4().hex[:8]}@orbita.demo"
    creator_email = f"source.creator.{uuid4().hex[:8]}@orbita.demo"
    _create_user(owner_email, "brand_owner", tenant_id)
    _create_user(creator_email, "creator", tenant_id)
    owner_headers = {"Authorization": f"Bearer {_token(client, owner_email)}"}
    creator_headers = {"Authorization": f"Bearer {_token(client, creator_email)}"}

    created = client.post("/api/v1/brands/current/drafts", headers=owner_headers)
    assert created.status_code == 200, created.text
    draft_id = created.json()["draft_id"]
    source = client.post(
        f"/api/v1/brands/current/drafts/{draft_id}/sources",
        headers=creator_headers,
        json={"name": "Creator source", "reference_text": "Unapproved evidence."},
    )
    assert source.status_code == 403, source.text

    owner_source = client.post(
        f"/api/v1/brands/current/drafts/{draft_id}/sources",
        headers=owner_headers,
        json={"name": "Owner source", "reference_text": "Owner reviewed reference excerpt."},
    )
    assert owner_source.status_code == 200, owner_source.text
    source_id = owner_source.json()["source"]["source_id"]
    missing_reason = client.post(
        f"/api/v1/brands/current/drafts/{draft_id}/records/source/{source_id}/decision",
        headers=owner_headers,
        json={"status": "approved"},
    )
    assert missing_reason.status_code == 422
    assert missing_reason.json()["detail"]["code"] == "DECISION_REASON_REQUIRED"

    creator_decision = client.post(
        f"/api/v1/brands/current/drafts/{draft_id}/records/source/{source_id}/decision",
        headers=creator_headers,
        json={"status": "approved"},
    )
    assert creator_decision.status_code == 403, creator_decision.text
