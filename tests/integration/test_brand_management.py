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
    from sigillum.api import routes as api_routes

    # API integration tests use a deterministic clean scanner. Scanner transport
    # failures and infected-result gating are exercised in dedicated tests.
    api_routes.scan_upload_bytes = lambda _payload: {
        "status": "CLEAN", "engine": "test-clamav",
        "scanned_at": "2026-11-09T00:00:00+00:00", "signature": None,
    }
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

    comparison = client.get(
        "/api/v1/brands/current/versions/compare",
        headers=headers,
        params={"from_version_id": "v0001", "to_version_id": "v0002"},
    )
    assert comparison.status_code == 200, comparison.text
    brand_change = next(item for item in comparison.json()["changes"] if item["section"] == "brand")
    description_change = next(item for item in brand_change["fields"] if item["field"] == "description")
    assert description_change["after"] == updated_brand["description"]

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

    decision_history = client.get(
        f"/api/v1/brands/current/drafts/{draft_id}/decisions", headers=headers
    )
    assert decision_history.status_code == 200, decision_history.text
    decision_rows = decision_history.json()["decisions"]
    assert [(item["record_type"], item["record_id"], item["status"]) for item in decision_rows] == [
        ("source", source_id, "approved"),
        ("asset", asset_id, "approved"),
    ]
    assert all(item["reason"] and item["actor_id"] for item in decision_rows)

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


def test_knowledge_pack_database_is_canonical_across_store_instances_and_rejects_stale_drafts(client, tmp_path):
    from sigillum.config import get_settings
    from sigillum.infrastructure.database.session import SessionLocal
    from sigillum.modules.knowledge.store import KnowledgePackStore

    tenant_id = f"tenant_pack_restart_{uuid4().hex[:10]}"
    owner_email = f"restart.owner.{uuid4().hex[:8]}@orbita.demo"
    _create_user(owner_email, "brand_owner", tenant_id)
    headers = {"Authorization": f"Bearer {_token(client, owner_email)}"}

    created = client.post("/api/v1/brands/current/drafts", headers=headers)
    assert created.status_code == 200, created.text
    draft_id = created.json()["draft_id"]

    settings = get_settings()
    store = KnowledgePackStore(settings.brand_pack_path, tmp_path / "instance_a", SessionLocal)
    stale_reader = KnowledgePackStore(settings.brand_pack_path, tmp_path / "instance_b", SessionLocal)

    first = store.get_draft(tenant_id, draft_id, "brand_orbita_demo")
    stale = stale_reader.get_draft(tenant_id, draft_id, "brand_orbita_demo")
    first["snapshot"]["brand"]["description"] = "Persisted by instance A."
    first["updated_by"] = "instance-a"
    persisted = store._persist_draft(tenant_id, "brand_orbita_demo", first)
    assert persisted["revision"] == first["revision"] + 1

    stale["snapshot"]["brand"]["description"] = "Must never overwrite instance A."
    with pytest.raises(ValueError, match="changed in another session"):
        stale_reader._persist_draft(tenant_id, "brand_orbita_demo", stale)

    reloaded = stale_reader.get_draft(tenant_id, draft_id, "brand_orbita_demo")
    assert reloaded["snapshot"]["brand"]["description"] == "Persisted by instance A."

    # A fresh storage root has no filesystem pointer; it reconstructs the active
    # pack from the DB snapshot and does not require the original process mirror.
    active = store.active_pack(tenant_id, "brand_orbita_demo")
    import shutil
    mirror_root = store._pack_root(tenant_id, "brand_orbita_demo")
    if mirror_root.exists():
        shutil.rmtree(mirror_root)
    restarted = KnowledgePackStore(settings.brand_pack_path, tmp_path / "fresh_instance", SessionLocal)
    restored = restarted.active_pack(tenant_id, "brand_orbita_demo")
    assert restored.brand["brand_id"] == active.brand["brand_id"]
    assert restored.brand["brand_name"] == active.brand["brand_name"]
    assert restored.fingerprint() == active.fingerprint()


def test_build_012_filesystem_draft_is_imported_into_database_catalog(client, tmp_path):
    import json
    from sigillum.config import get_settings
    from sigillum.infrastructure.database.session import SessionLocal
    from sigillum.modules.knowledge.store import KnowledgePackStore

    tenant_id = f"tenant_legacy_draft_{uuid4().hex[:10]}"
    owner_email = f"legacy.draft.{uuid4().hex[:8]}@orbita.demo"
    _create_user(owner_email, "brand_owner", tenant_id)
    headers = {"Authorization": f"Bearer {_token(client, owner_email)}"}
    management = client.get("/api/v1/brands/current/management", headers=headers)
    assert management.status_code == 200, management.text

    settings = get_settings()
    store = KnowledgePackStore(settings.brand_pack_path, tmp_path / "legacy-build-012-root", SessionLocal)
    active = store.active_pack(tenant_id, "brand_orbita_demo")
    metadata = store.active_metadata(tenant_id, "brand_orbita_demo")
    draft_id = str(uuid4())
    legacy_snapshot = active.snapshot()
    legacy_snapshot["brand"]["description"] = "Draft recovered from the Build 012 filesystem store."
    legacy_draft = {
        "draft_id": draft_id,
        "brand_id": "brand_orbita_demo",
        "pack_id": metadata["pack_id"],
        "base_version_id": metadata["version_id"],
        "base_fingerprint": metadata["fingerprint"],
        "status": "DRAFT",
        "created_at": "2026-11-09T00:00:00+00:00",
        "created_by": "legacy-build-012-owner",
        "updated_at": "2026-11-09T00:00:00+00:00",
        "updated_by": "legacy-build-012-owner",
        "snapshot": legacy_snapshot,
        "validation": None,
    }
    draft_path = store._draft_path(tenant_id, draft_id, "brand_orbita_demo")
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(json.dumps(legacy_draft), encoding="utf-8")

    # A fresh store instance sees the DB head, imports the Build 012 draft once,
    # and serves the recovered draft from the database catalogue.
    store.ensure_initialized(tenant_id, "brand_orbita_demo")
    recovered = store.get_draft(tenant_id, draft_id, "brand_orbita_demo")
    assert recovered["snapshot"]["brand"]["description"] == legacy_snapshot["brand"]["description"]
    assert recovered["base_version_id"] == metadata["version_id"]
    with SessionLocal() as db:
        from sqlalchemy import select
        row = db.scalar(select(models.BrandKnowledgePackDraft).where(
            models.BrandKnowledgePackDraft.tenant_id == tenant_id,
            models.BrandKnowledgePackDraft.brand_id == "brand_orbita_demo",
            models.BrandKnowledgePackDraft.draft_id == draft_id,
        ))
        assert row is not None


def test_build_012_version_history_and_published_draft_migrate_into_catalogue(client):
    from sigillum.api import routes as api_routes
    from sigillum.modules.knowledge.store import KnowledgePackStore

    tenant_id = f"tenant_pack_history_{uuid4().hex[:10]}"
    owner_email = f"history.owner.{uuid4().hex[:8]}@orbita.demo"
    _create_user(owner_email, "brand_owner", tenant_id)
    headers = {"Authorization": f"Bearer {_token(client, owner_email)}"}

    # Simulate a Build 012 installation: create and publish using the old
    # filesystem adapter before the API's DB-backed store has a catalogue head.
    filesystem_store = KnowledgePackStore(
        api_routes.settings.brand_pack_path,
        api_routes.pack_store.root,
    )
    draft = filesystem_store.create_draft(tenant_id, "legacy-owner", "brand_orbita_demo", "ORBITA")
    changed_brand = dict(draft["snapshot"]["brand"])
    changed_brand["description"] = "Published by the Build 012 filesystem-only store."
    filesystem_store.update_section(
        tenant_id, draft["draft_id"], "brand", changed_brand, "legacy-owner", "brand_orbita_demo"
    )
    assert filesystem_store.validate_draft(tenant_id, draft["draft_id"], "brand_orbita_demo")["valid"]
    published = filesystem_store.publish_draft(
        tenant_id, draft["draft_id"], "legacy-owner", "brand_orbita_demo"
    )
    assert published["version_id"] == "v0002"

    # The first DB-backed API read imports the full version history, not only
    # the active version, and recovers the published draft record as well.
    management = client.get("/api/v1/brands/current/management", headers=headers)
    assert management.status_code == 200, management.text
    result = management.json()
    assert result["active_version"]["version_id"] == "v0002"
    assert {item["version_id"] for item in result["versions"]} == {"v0001", "v0002"}
    assert result["snapshot"]["brand"]["description"] == "Published by the Build 012 filesystem-only store."

    recovered_draft = client.get(
        f"/api/v1/brands/current/drafts/{draft['draft_id']}", headers=headers
    )
    assert recovered_draft.status_code == 200, recovered_draft.text
    assert recovered_draft.json()["status"] == "PUBLISHED"
    assert recovered_draft.json()["published_version_id"] == "v0002"



def test_uploaded_knowledge_source_waits_for_clean_scan_then_extracts_and_downloads(client):
    from io import BytesIO
    from docx import Document
    from sigillum.api import routes as api_routes

    tenant_id = f"tenant_source_scan_{uuid4().hex[:10]}"
    owner_email = f"source.scan.{uuid4().hex[:8]}@orbita.demo"
    _create_user(owner_email, "brand_owner", tenant_id)
    headers = {"Authorization": f"Bearer {_token(client, owner_email)}"}
    draft_response = client.post("/api/v1/brands/current/drafts", headers=headers)
    assert draft_response.status_code == 200, draft_response.text
    draft_id = draft_response.json()["draft_id"]

    document = Document()
    document.add_heading("ORBITA Product Specification", level=1)
    document.add_paragraph("The ORBITA Air One includes a verified 24-hour battery life under controlled test conditions.")
    payload = BytesIO()
    document.save(payload)
    docx_bytes = payload.getvalue()

    old_scanner = api_routes.scan_upload_bytes
    try:
        api_routes.scan_upload_bytes = lambda _data: {
            "status": "UNAVAILABLE", "engine": "test-clamav", "scanned_at": "2026-11-09T00:00:00+00:00", "signature": None,
        }
        upload = client.post(
            f"/api/v1/brands/current/drafts/{draft_id}/sources/upload",
            headers=headers,
            data={"name": "ORBITA Product Specification", "source_type": "product_specification", "version": "1"},
            files={"file": ("orbita-spec.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert upload.status_code == 200, upload.text
        source = upload.json()["source"]
        source_id = source["source_id"]
        assert source["scan_status"] == "UNAVAILABLE"
        assert source["extraction_status"] == "PENDING_SCAN"
        assert source["reference_text"] is None
        assert upload.json()["authoritative"] is False

        blocked_decision = client.post(
            f"/api/v1/brands/current/drafts/{draft_id}/records/source/{source_id}/decision",
            headers=headers,
            json={"status": "approved", "reason": "Attempt before successful malware scan."},
        )
        assert blocked_decision.status_code == 422
        assert blocked_decision.json()["detail"]["code"] == "INVALID_KNOWLEDGE_DECISION"
        blocked_download = client.get(
            f"/api/v1/brands/current/drafts/{draft_id}/sources/{source_id}/download", headers=headers
        )
        assert blocked_download.status_code == 423

        api_routes.scan_upload_bytes = lambda _data: {
            "status": "CLEAN", "engine": "test-clamav", "scanned_at": "2026-11-09T00:01:00+00:00", "signature": None,
        }
        rescanned = client.post(
            f"/api/v1/brands/current/drafts/{draft_id}/sources/{source_id}/scan", headers=headers
        )
        assert rescanned.status_code == 200, rescanned.text
        assert rescanned.json()["scan_status"] == "CLEAN"
        assert rescanned.json()["extraction_status"] == "COMPLETED"

        extraction = client.get(
            f"/api/v1/brands/current/drafts/{draft_id}/sources/{source_id}/extraction", headers=headers
        )
        assert extraction.status_code == 200, extraction.text
        assert extraction.json()["regions_returned"] >= 1
        assert "24-hour battery life" in extraction.json()["regions"][1]["text"] or "24-hour battery life" in " ".join(
            str(item.get("text", "")) for item in extraction.json()["regions"]
        )

        download = client.get(
            f"/api/v1/brands/current/drafts/{draft_id}/sources/{source_id}/download", headers=headers
        )
        assert download.status_code == 200
        assert download.content == docx_bytes

        decision = client.post(
            f"/api/v1/brands/current/drafts/{draft_id}/records/source/{source_id}/decision",
            headers=headers,
            json={"status": "approved", "reason": "Scanned clean and checked extracted product specification."},
        )
        assert decision.status_code == 200, decision.text
        validation = client.post(f"/api/v1/brands/current/drafts/{draft_id}/validate", headers=headers)
        assert validation.status_code == 200, validation.text
        assert validation.json()["valid"] is True, validation.json()
    finally:
        api_routes.scan_upload_bytes = old_scanner


def test_infected_uploaded_knowledge_source_is_never_extracted_or_downloadable(client):
    from io import BytesIO
    from docx import Document
    from sigillum.api import routes as api_routes

    tenant_id = f"tenant_source_infected_{uuid4().hex[:10]}"
    owner_email = f"source.infected.{uuid4().hex[:8]}@orbita.demo"
    _create_user(owner_email, "brand_owner", tenant_id)
    headers = {"Authorization": f"Bearer {_token(client, owner_email)}"}
    draft = client.post("/api/v1/brands/current/drafts", headers=headers).json()

    document = Document()
    document.add_paragraph("This document must remain quarantined.")
    payload = BytesIO()
    document.save(payload)

    old_scanner = api_routes.scan_upload_bytes
    try:
        api_routes.scan_upload_bytes = lambda _data: {
            "status": "INFECTED", "engine": "test-clamav", "scanned_at": "2026-11-09T00:00:00+00:00", "signature": "Test.Malware",
        }
        response = client.post(
            f"/api/v1/brands/current/drafts/{draft['draft_id']}/sources/upload",
            headers=headers,
            data={"name": "Infected source", "source_type": "policy_document", "version": "1"},
            files={"file": ("infected-fixture.docx", payload.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert response.status_code == 200, response.text
        source = response.json()["source"]
        assert source["scan_status"] == "INFECTED"
        assert source["extraction_status"] == "NOT_RUN"
        assert source["reference_text"] is None
        download = client.get(
            f"/api/v1/brands/current/drafts/{draft['draft_id']}/sources/{source['source_id']}/download", headers=headers
        )
        assert download.status_code == 423
        decision = client.post(
            f"/api/v1/brands/current/drafts/{draft['draft_id']}/records/source/{source['source_id']}/decision",
            headers=headers,
            json={"status": "approved", "reason": "This should be rejected because malware was detected."},
        )
        assert decision.status_code == 422
    finally:
        api_routes.scan_upload_bytes = old_scanner


def test_owner_asset_usage_policy_is_saved_validated_and_published(client):
    tenant_id = f"tenant_asset_usage_{uuid4().hex[:10]}"
    owner_email = f"asset.policy.{uuid4().hex[:10]}@orbita.demo"
    _create_user(owner_email, "brand_owner", tenant_id)
    headers = {"Authorization": f"Bearer {_token(client, owner_email)}"}
    created = client.post("/api/v1/brands/current/drafts", headers=headers)
    assert created.status_code == 200, created.text
    draft = created.json()
    manifest = dict(draft["snapshot"]["assets"])
    manifest["usage_policies"] = {
        "logo": {
            "allowed_channels": ["direct_web", "social"],
            "allowed_uses": ["brand_lockup", "campaign", "social_ad"],
            "min_width": 0,
            "min_height": 0,
            "palette_hex": [],
            "palette_tolerance": 80,
            "minimum_palette_match_ratio": 0.7,
            "clear_space_ratio": 0.1,
            "valid_from": "2026-11-09T00:00:00+05:30",
            "valid_until": None,
            "severity": "review_required",
        }
    }
    saved = client.put(
        f"/api/v1/brands/current/drafts/{draft['draft_id']}/section",
        headers=headers,
        json={"section": "assets", "content": manifest},
    )
    assert saved.status_code == 200, saved.text
    validation = client.post(
        f"/api/v1/brands/current/drafts/{draft['draft_id']}/validate",
        headers=headers,
    )
    assert validation.status_code == 200, validation.text
    assert validation.json()["valid"] is True
    assert any(item["code"] == "ASSET_CLEAR_SPACE_MANUAL_REVIEW" for item in validation.json()["warnings"])
    published = client.post(
        f"/api/v1/brands/current/drafts/{draft['draft_id']}/publish",
        headers=headers,
    )
    assert published.status_code == 200, published.text
    latest = client.get("/api/v1/brands/current/management", headers=headers)
    assert latest.status_code == 200
    assert latest.json()["snapshot"]["assets"]["usage_policies"]["logo"]["allowed_uses"] == [
        "brand_lockup", "campaign", "social_ad"
    ]
