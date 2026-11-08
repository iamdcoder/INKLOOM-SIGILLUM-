from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from sigillum.domain.enums import Role
from sigillum.infrastructure.database import models
from sigillum.infrastructure.database.session import get_db, set_database_scope
from sigillum.infrastructure.security import decode_access_token


DbSession = Annotated[Session, Depends(get_db)]


@dataclass(frozen=True)
class WorkspaceContext:
    membership_id: str
    tenant_id: str
    tenant_name: str
    brand_record_id: str
    brand_id: str
    brand_name: str
    role: str


@dataclass(frozen=True)
class CurrentActor:
    id: str
    email: str
    display_name: str
    role: str
    tenant_id: str
    tenant_name: str
    brand_record_id: str
    brand_id: str
    brand_name: str
    membership_id: str
    session_id: str
    workspaces: tuple[WorkspaceContext, ...]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _workspace_rows(db: Session, user_id: str) -> list[WorkspaceContext]:
    query = (
        select(models.Membership, models.Tenant, models.Brand)
        .join(models.Tenant, models.Tenant.id == models.Membership.tenant_id)
        .join(models.Brand, models.Brand.id == models.Membership.brand_id)
        .where(
            models.Membership.user_id == user_id,
            models.Membership.is_active.is_(True),
            models.Tenant.is_active.is_(True),
            models.Brand.is_active.is_(True),
        )
        .order_by(models.Tenant.name, models.Brand.name)
    )
    return [
        WorkspaceContext(
            membership_id=membership.id,
            tenant_id=tenant.id,
            tenant_name=tenant.name,
            brand_record_id=brand.id,
            brand_id=brand.external_id,
            brand_name=brand.name,
            role=membership.role,
        )
        for membership, tenant, brand in db.execute(query).all()
    ]


def current_user(
    authorization: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> CurrentActor:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_REQUIRED", "message": "Sign in to continue."},
        )

    try:
        payload = decode_access_token(authorization.split(" ", 1)[1])
        user_id = str(payload.get("sub") or "")
        session_id = str(payload.get("jti") or "")
    except (jwt.InvalidTokenError, ValueError, TypeError):
        user_id = ""
        session_id = ""

    if not user_id or not session_id:
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_SESSION", "message": "Session is invalid or expired. Sign in again."},
        )

    # The signed subject is safe to use for the first RLS lookup. Tenant and brand
    # context are not set until the membership row is loaded and validated.
    set_database_scope(db, user_id=user_id)
    user = db.get(models.User, user_id)
    session = db.get(models.UserSession, session_id)
    if (
        not user
        or not user.is_active
        or not session
        or session.user_id != user.id
        or session.revoked_at is not None
        or _utc(session.expires_at) <= datetime.now(timezone.utc)
    ):
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_SESSION", "message": "Session is invalid, expired or revoked. Sign in again."},
        )

    membership = db.get(models.Membership, session.membership_id)
    if not membership or membership.user_id != user.id or not membership.is_active:
        raise HTTPException(
            status_code=403,
            detail={"code": "MEMBERSHIP_INACTIVE", "message": "Your workspace access is inactive. Contact its administrator."},
        )

    tenant = db.get(models.Tenant, membership.tenant_id)
    brand = db.get(models.Brand, membership.brand_id)
    if not tenant or not tenant.is_active or not brand or not brand.is_active or brand.tenant_id != tenant.id:
        raise HTTPException(
            status_code=403,
            detail={"code": "WORKSPACE_UNAVAILABLE", "message": "This workspace or brand is no longer available."},
        )

    set_database_scope(
        db,
        user_id=user.id,
        tenant_id=tenant.id,
        brand_id=brand.external_id,
        brand_record_id=brand.id,
        membership_role=membership.role,
    )
    workspaces = tuple(_workspace_rows(db, user.id))
    return CurrentActor(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=membership.role,
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        brand_record_id=brand.id,
        brand_id=brand.external_id,
        brand_name=brand.name,
        membership_id=membership.id,
        session_id=session.id,
        workspaces=workspaces,
    )


CurrentUser = Annotated[CurrentActor, Depends(current_user)]


def require_roles(*roles: Role):
    allowed = {role.value for role in roles}

    def dependency(user: CurrentUser) -> CurrentActor:
        if user.role not in allowed:
            raise HTTPException(
                status_code=403,
                detail={"code": "ACCESS_DENIED", "message": "Your workspace role cannot perform this action."},
            )
        return user

    return dependency
