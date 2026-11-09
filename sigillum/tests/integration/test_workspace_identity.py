from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from apps.api.main import SessionLocal, app
from sigillum.infrastructure.database import models
from sigillum.infrastructure.database.session import set_database_scope
from sigillum.infrastructure.security import hash_password


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _create_member(
    email: str,
    *,
    tenant_id: str | None = None,
    account_role: str = "creator",
    membership_role: str | None = None,
    password: str = "Workspace-Test-Password",
) -> dict:
    tenant_id = tenant_id or f"tenant_{uuid4().hex[:12]}"
    membership_role = membership_role or account_role
    with SessionLocal() as db:
        user = models.User(
            email=email,
            display_name=f"Test {email.split('@')[0]}",
            role=account_role,
            password_hash=hash_password(password),
            tenant_id=tenant_id,
            is_active=True,
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
            tenant = models.Tenant(id=tenant_id, name=f"Workspace {tenant_id}", is_active=True)
            db.add(tenant)
            db.flush()
        brand = db.scalar(
            select(models.Brand).where(
                models.Brand.tenant_id == tenant_id,
                models.Brand.external_id == "brand_orbita_demo",
            )
        )
        if brand is None:
            brand = models.Brand(
                tenant_id=tenant_id,
                external_id="brand_orbita_demo",
                name="ORBITA",
                is_active=True,
            )
            db.add(brand)
            db.flush()
        membership = models.Membership(
            user_id=user.id,
            tenant_id=tenant_id,
            brand_id=brand.id,
            role=membership_role,
            is_active=True,
        )
        db.add(membership)
        db.commit()
        return {
            "user_id": user.id,
            "tenant_id": tenant_id,
            "brand_record_id": brand.id,
            "brand_id": brand.external_id,
            "membership_id": membership.id,
            "email": email,
            "password": password,
        }


def _add_membership(user_id: str, tenant_id: str) -> dict:
    with SessionLocal() as db:
        set_database_scope(
            db,
            user_id=user_id,
            tenant_id=tenant_id,
            brand_id="brand_orbita_demo",
            membership_role="administrator",
        )
        tenant = db.get(models.Tenant, tenant_id)
        if tenant is None:
            tenant = models.Tenant(id=tenant_id, name=f"Workspace {tenant_id}", is_active=True)
            db.add(tenant)
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
        set_database_scope(
            db,
            user_id=user_id,
            tenant_id=tenant_id,
            brand_id=brand.external_id,
            brand_record_id=brand.id,
            membership_role="administrator",
        )
        membership = models.Membership(
            user_id=user_id,
            tenant_id=tenant_id,
            brand_id=brand.id,
            role="creator",
            is_active=True,
        )
        db.add(membership)
        db.commit()
        return {"tenant_id": tenant_id, "brand_record_id": brand.id, "membership_id": membership.id}


def _login(client: TestClient, member: dict, brand_id: str | None = None):
    payload = {"email": member["email"], "password": member["password"]}
    if brand_id:
        payload["brand_id"] = brand_id
    return client.post("/api/v1/auth/login", json=payload)


def test_membership_role_is_authoritative_not_legacy_user_role(client):
    member = _create_member(
        f"role-source-{uuid4().hex[:8]}@example.test",
        account_role="creator",
        membership_role="brand_owner",
    )
    response = _login(client, member)
    assert response.status_code == 200, response.text
    assert response.json()["user"]["role"] == "brand_owner"
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    assert client.post("/api/v1/brands/current/drafts", headers=headers).status_code == 200


def test_session_is_server_revocable_and_logout_invalidates_token(client):
    member = _create_member(f"logout-{uuid4().hex[:8]}@example.test")
    login = _login(client, member)
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    logged_out = client.post("/api/v1/auth/logout", headers=headers)
    assert logged_out.status_code == 200
    invalid = client.get("/api/v1/auth/me", headers=headers)
    assert invalid.status_code == 401
    assert invalid.json()["detail"]["code"] == "INVALID_SESSION"


def test_multiple_workspace_memberships_require_explicit_selection(client):
    member = _create_member(f"multi-{uuid4().hex[:8]}@example.test")
    second = _add_membership(member["user_id"], f"tenant_{uuid4().hex[:12]}")

    ambiguous = _login(client, member)
    assert ambiguous.status_code == 409
    assert ambiguous.json()["detail"]["code"] == "WORKSPACE_SELECTION_REQUIRED"
    assert len(ambiguous.json()["detail"]["workspaces"]) == 2

    selected = _login(client, member, second["brand_record_id"])
    assert selected.status_code == 200, selected.text
    assert selected.json()["user"]["tenant_id"] == second["tenant_id"]
    headers = {"Authorization": f"Bearer {selected.json()['access_token']}"}
    assert client.get("/api/v1/auth/me", headers=headers).json()["tenant_id"] == second["tenant_id"]


def test_inactive_membership_invalidates_an_existing_session(client):
    member = _create_member(f"inactive-{uuid4().hex[:8]}@example.test")
    login = _login(client, member)
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    with SessionLocal() as db:
        set_database_scope(
            db,
            user_id=member["user_id"],
            tenant_id=member["tenant_id"],
            brand_id=member["brand_id"],
            brand_record_id=member["brand_record_id"],
            membership_role="creator",
        )
        membership = db.get(models.Membership, member["membership_id"])
        membership.is_active = False
        db.commit()
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "MEMBERSHIP_INACTIVE"


def test_cross_tenant_submission_and_file_grant_are_not_accessible(client):
    owner = _create_member(f"owner-{uuid4().hex[:8]}@example.test")
    outsider = _create_member(f"outsider-{uuid4().hex[:8]}@example.test")
    owner_login = _login(client, owner)
    outsider_login = _login(client, outsider)
    owner_headers = {"Authorization": f"Bearer {owner_login.json()['access_token']}"}
    outsider_headers = {"Authorization": f"Bearer {outsider_login.json()['access_token']}"}
    upload = client.post(
        "/api/v1/submissions",
        headers=owner_headers,
        data={
            "title": "Workspace-isolated submission",
            "channel": "direct_web",
            "locale": "en-IN",
            "geography": "IN",
            "audience": "consumer",
            "offer_id": "OFFER-ORBITA-OCT-NOV-2026",
            "publication_at": "2026-11-10T12:00:00+05:30",
        },
        files={"file": ("private.txt", b"A private ORBITA workspace submission.", "text/plain")},
    )
    assert upload.status_code == 200, upload.text
    submission_id = upload.json()["submission"]["id"]
    version_id = upload.json()["content_version"]["id"]

    hidden = client.get(f"/api/v1/submissions/{submission_id}", headers=outsider_headers)
    assert hidden.status_code == 404
    grant = client.post(f"/api/v1/content-versions/{version_id}/grant", headers=owner_headers)
    assert grant.status_code == 200, grant.text
    forbidden_grant = client.post(f"/api/v1/content-versions/{version_id}/grant", headers=outsider_headers)
    assert forbidden_grant.status_code == 404


def test_download_grant_expires_with_the_issuing_session(client):
    member = _create_member(f"grant-{uuid4().hex[:8]}@example.test")
    login = _login(client, member)
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    upload = client.post(
        "/api/v1/submissions",
        headers=headers,
        data={
            "title": "Download grant lifecycle",
            "channel": "direct_web",
            "locale": "en-IN",
            "geography": "IN",
            "audience": "consumer",
            "offer_id": "OFFER-ORBITA-OCT-NOV-2026",
            "publication_at": "2026-11-10T12:00:00+05:30",
        },
        files={"file": ("grant.txt", b"A grant-bound source file.", "text/plain")},
    )
    assert upload.status_code == 200, upload.text
    version_id = upload.json()["content_version"]["id"]
    grant = client.post(f"/api/v1/content-versions/{version_id}/grant", headers=headers)
    assert grant.status_code == 200, grant.text
    granted = client.get(grant.json()["download_url"])
    assert granted.status_code == 200
    assert granted.content == b"A grant-bound source file."

    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    revoked = client.get(grant.json()["download_url"])
    assert revoked.status_code == 401


def test_administrator_can_add_and_deactivate_brand_membership(client):
    admin = _create_member(f"workspace-admin-{uuid4().hex[:8]}@example.test", membership_role="administrator")
    target = _create_member(f"workspace-target-{uuid4().hex[:8]}@example.test")
    admin_login = _login(client, admin)
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    added = client.post(
        "/api/v1/workspace/memberships",
        headers=admin_headers,
        json={"email": target["email"], "role": "creator"},
    )
    assert added.status_code == 200, added.text
    membership_id = added.json()["membership_id"]

    listing = client.get("/api/v1/workspace/memberships", headers=admin_headers)
    assert listing.status_code == 200
    assert any(item["membership_id"] == membership_id for item in listing.json())

    target_login = _login(client, target, admin["brand_record_id"])
    assert target_login.status_code == 200, target_login.text
    target_headers = {"Authorization": f"Bearer {target_login.json()['access_token']}"}

    disabled = client.patch(
        f"/api/v1/workspace/memberships/{membership_id}",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert disabled.status_code == 200, disabled.text
    denied = client.get("/api/v1/auth/me", headers=target_headers)
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "MEMBERSHIP_INACTIVE"


def test_brand_owner_cannot_grant_administrator_and_last_admin_is_protected(client):
    owner = _create_member(f"membership-owner-{uuid4().hex[:8]}@example.test", membership_role="brand_owner")
    target = _create_member(f"membership-target2-{uuid4().hex[:8]}@example.test")
    owner_login = _login(client, owner)
    owner_headers = {"Authorization": f"Bearer {owner_login.json()['access_token']}"}
    blocked = client.post(
        "/api/v1/workspace/memberships",
        headers=owner_headers,
        json={"email": target["email"], "role": "administrator"},
    )
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "ROLE_GRANT_NOT_ALLOWED"

    agency_membership = client.post(
        "/api/v1/workspace/memberships",
        headers=owner_headers,
        json={"email": target["email"], "role": "agency"},
    )
    assert agency_membership.status_code == 200, agency_membership.text
    assert agency_membership.json()["role"] == "agency"

    admin = _create_member(f"last-admin-{uuid4().hex[:8]}@example.test", membership_role="administrator")
    admin_login = _login(client, admin)
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
    # The only active administrator cannot remove their own membership.
    self_disable = client.patch(
        f"/api/v1/workspace/memberships/{admin['membership_id']}",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert self_disable.status_code == 409
    assert self_disable.json()["detail"]["code"] == "SELF_DEACTIVATION_BLOCKED"

    # Demotion must be protected even when is_active is omitted from the PATCH.
    self_demotion = client.patch(
        f"/api/v1/workspace/memberships/{admin['membership_id']}",
        headers=admin_headers,
        json={"role": "creator"},
    )
    assert self_demotion.status_code == 409
    assert self_demotion.json()["detail"]["code"] == "LAST_ADMIN_PROTECTED"


def test_agency_contributor_is_scoped_to_submissions_they_created(client):
    admin = _create_member(f"agency-scope-admin-{uuid4().hex[:8]}@example.test", membership_role="administrator")
    other_creator = _create_member(
        f"agency-scope-other-creator-{uuid4().hex[:8]}@example.test",
        tenant_id=admin["tenant_id"],
        membership_role="creator",
    )
    agency = _create_member(f"agency-scope-user-{uuid4().hex[:8]}@example.test")
    admin_login = _login(client, admin)
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
    other_creator_login = _login(client, other_creator, admin["brand_record_id"])
    other_creator_headers = {"Authorization": f"Bearer {other_creator_login.json()['access_token']}"}

    invited = client.post(
        "/api/v1/workspace/memberships",
        headers=admin_headers,
        json={"email": agency["email"], "role": "agency"},
    )
    assert invited.status_code == 200, invited.text

    other_upload = client.post(
        "/api/v1/submissions",
        headers=other_creator_headers,
        data={
            "title": "Other creator private submission",
            "channel": "direct_web",
            "locale": "en-IN",
            "geography": "IN",
            "audience": "consumer",
            "offer_id": "OFFER-ORBITA-OCT-NOV-2026",
            "publication_at": "2026-11-10T12:00:00+05:30",
        },
        files={"file": ("admin-private.txt", b"Admin-owned workspace copy.", "text/plain")},
    )
    assert other_upload.status_code == 200, other_upload.text
    other_submission_id = other_upload.json()["submission"]["id"]

    agency_login = _login(client, agency, admin["brand_record_id"])
    assert agency_login.status_code == 200, agency_login.text
    agency_headers = {"Authorization": f"Bearer {agency_login.json()['access_token']}"}
    assert client.get("/api/v1/submissions", headers=agency_headers).json() == []
    assert client.get(f"/api/v1/submissions/{other_submission_id}", headers=agency_headers).status_code == 404

    own_upload = client.post(
        "/api/v1/submissions",
        headers=agency_headers,
        data={
            "title": "Agency own submission",
            "channel": "direct_web",
            "locale": "en-IN",
            "geography": "IN",
            "audience": "consumer",
            "offer_id": "OFFER-ORBITA-OCT-NOV-2026",
            "publication_at": "2026-11-10T12:00:00+05:30",
        },
        files={"file": ("agency-own.txt", b"Agency-authored workspace copy.", "text/plain")},
    )
    assert own_upload.status_code == 200, own_upload.text
    visible = client.get("/api/v1/submissions", headers=agency_headers)
    assert visible.status_code == 200
    assert [item["id"] for item in visible.json()] == [own_upload.json()["submission"]["id"]]


def test_postgresql_rls_denies_unscoped_and_cross_brand_reads(client):
    with SessionLocal() as db:
        if db.get_bind().dialect.name != "postgresql":
            pytest.skip("PostgreSQL Row Level Security is exercised by the PostgreSQL CI job.")

    from sigillum.infrastructure.database.models import Submission

    with SessionLocal() as db:
        actor = db.scalar(select(models.User).where(models.User.email == "creator@orbita.demo"))
        assert actor is not None
        set_database_scope(db, user_id=actor.id)
        membership = db.scalar(
            select(models.Membership).where(
                models.Membership.user_id == actor.id,
                models.Membership.is_active.is_(True),
            )
        )
        assert membership is not None
        brand = db.get(models.Brand, membership.brand_id)
        assert brand is not None
        set_database_scope(
            db,
            user_id=actor.id,
            tenant_id=membership.tenant_id,
            brand_id=brand.external_id,
            brand_record_id=brand.id,
            membership_role=membership.role,
        )
        submission = Submission(
            id=str(uuid4()),
            tenant_id=membership.tenant_id,
            brand_id=brand.external_id,
            title="RLS isolation fixture",
            channel="direct_web",
            locale="en-IN",
            geography="IN",
            audience="consumer",
            offer_id=None,
            publication_at="2026-11-10T12:00:00+05:30",
            created_by=actor.id,
        )
        db.add(submission)
        session_record = models.UserSession(
            id=str(uuid4()),
            user_id=actor.id,
            membership_id=membership.id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=20),
        )
        db.add(session_record)
        db.commit()
        submission_id = submission.id
        session_id = session_record.id

    with SessionLocal() as db:
        assert db.get(Submission, submission_id) is None
        assert db.get(models.UserSession, session_id) is None
        set_database_scope(db, user_id=actor.id)
        assert db.get(models.UserSession, session_id) is not None
        set_database_scope(
            db,
            user_id=actor.id,
            tenant_id=membership.tenant_id,
            brand_id=brand.external_id,
            brand_record_id=brand.id,
            membership_role=membership.role,
        )
        escalated = db.execute(
            update(models.Membership)
            .where(models.Membership.id == membership.id)
            .values(role="administrator")
        )
        assert escalated.rowcount == 0
        db.commit()
        set_database_scope(db, user_id=actor.id)
        assert db.get(models.Membership, membership.id).role == "creator"
        set_database_scope(
            db,
            user_id=actor.id,
            tenant_id=membership.tenant_id,
            brand_id="different-brand-context",
            brand_record_id="different-brand-record",
            membership_role=membership.role,
        )
        assert db.get(Submission, submission_id) is None
        set_database_scope(
            db,
            user_id=actor.id,
            tenant_id=membership.tenant_id,
            brand_id=brand.external_id,
            brand_record_id=brand.id,
            membership_role=membership.role,
        )
        assert db.get(Submission, submission_id) is not None


def test_switch_context_revokes_old_token_and_issues_new_membership_context(client):
    member = _create_member(f"switch-context-{uuid4().hex[:8]}@example.test")
    second = _add_membership(member["user_id"], f"tenant_{uuid4().hex[:12]}")
    first_login = _login(client, member, member["brand_record_id"])
    assert first_login.status_code == 200, first_login.text
    first_headers = {"Authorization": f"Bearer {first_login.json()['access_token']}"}

    switched = client.post(
        "/api/v1/auth/switch-context",
        headers=first_headers,
        json={"brand_id": second["brand_record_id"]},
    )
    assert switched.status_code == 200, switched.text
    assert switched.json()["user"]["tenant_id"] == second["tenant_id"]
    assert client.get("/api/v1/auth/me", headers=first_headers).status_code == 401

    second_headers = {"Authorization": f"Bearer {switched.json()['access_token']}"}
    me = client.get("/api/v1/auth/me", headers=second_headers)
    assert me.status_code == 200
    assert me.json()["brand_id"] == "brand_orbita_demo"
