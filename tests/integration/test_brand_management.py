from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api.main import SessionLocal
from sigillum.infrastructure.database import models
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
