from datetime import datetime, timedelta, timezone
import difflib
import json
from io import BytesIO
from hashlib import sha256
from uuid import uuid4
from pathlib import Path
from urllib.parse import quote
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from sigillum.config import get_settings
from sigillum.api.dependencies import CurrentActor, CurrentUser, DbSession, WorkspaceContext, _workspace_rows, require_roles
from sigillum.infrastructure.database.session import SessionLocal, get_db, set_database_scope
from sigillum.api.schemas import (LoginRequest, TokenResponse, DecisionRequest, PatchRequest, RevisionRequest, KnowledgePackSectionUpdate, WorkspaceSwitchRequest, MembershipCreateRequest, MembershipUpdateRequest, FileGrantResponse, KnowledgeSourceCreateRequest, KnowledgeRecordDecisionRequest)
from sigillum.domain.enums import Role
from sigillum.infrastructure.database import models
from sigillum.infrastructure.storage import StorageUnavailable, get_storage
from sigillum.infrastructure.security import verify_password, create_access_token, create_file_grant_token, decode_access_token
from sigillum.infrastructure.malware import scan_bytes
from sigillum.modules.content.extraction import extract, sniff_file
from sigillum.modules.knowledge.brand_pack import BrandPack
from sigillum.modules.knowledge.asset_policy import extract_palette
from sigillum.modules.knowledge.store import KnowledgePackStore
from sigillum.application.services.review_service import ReviewService, audit

router=APIRouter()
settings=get_settings()
pack_store=KnowledgePackStore(settings.brand_pack_path, settings.storage_root.parent / "brand_packs", SessionLocal)

def scan_upload_bytes(data: bytes) -> dict[str, str | None]:
    """Scanner seam used by uploads; tests inject deterministic clean/infected results."""
    return scan_bytes(data, settings)

def _scan_document_and_extract(source: dict, raw: bytes, storage) -> dict:
    scan_result = scan_upload_bytes(raw)
    status = str(scan_result.get("status", "ERROR")).upper()
    if status not in {"CLEAN", "INFECTED", "UNAVAILABLE", "ERROR"}:
        status = "ERROR"
    updates: dict[str, object] = {
        "scan_status": status,
        "scan_engine": scan_result.get("engine") or "clamav",
        "scan_scanned_at": scan_result.get("scanned_at") or datetime.now(timezone.utc).isoformat(),
        "scan_signature": scan_result.get("signature"),
        "extraction_status": "PENDING_SCAN" if status in {"UNAVAILABLE", "ERROR"} else "NOT_RUN",
        "extraction_warnings": [],
        "region_count": 0,
    }
    if status == "INFECTED":
        updates["extraction_warnings"] = ["MALWARE_DETECTED: the source is quarantined and was not parsed."]
    elif status in {"UNAVAILABLE", "ERROR"}:
        updates["extraction_warnings"] = ["MALWARE_SCAN_PENDING: the source remains quarantined until a clean scanner result is available."]
    else:
        try:
            result = extract(source["original_filename"], raw)
            full_text = result.text or ""
            excerpt = full_text[:20000].strip()
            warnings_list = list(result.warnings)
            extraction_status = result.status
            if len(full_text) > 20000:
                warnings_list.append("SOURCE_EXCERPT_TRUNCATED: only the first 20,000 characters are retained for exact evidence matching.")
                extraction_status = "PARTIAL"
            if not excerpt:
                extraction_status = "PARTIAL"
                warnings_list.append("SOURCE_TEXT_EMPTY: the file contains no extractable text; manual review is required.")
            regions = []
            for region in result.regions[:500]:
                if not isinstance(region, dict):
                    continue
                safe_region = dict(region)
                if isinstance(safe_region.get("text"), str) and len(safe_region["text"]) > 4000:
                    safe_region["text"] = safe_region["text"][:3997] + "..."
                safe_region.pop("words", None)
                regions.append(safe_region)
            if len(result.regions) > 500:
                warnings_list.append("SOURCE_REGION_LIMIT: only the first 500 logical regions are exposed in the extraction manifest.")
            manifest = {
                "schema_version": "1.0.0",
                "source_id": source["source_id"],
                "file_sha256": source["file_sha256"],
                "parser_status": result.status,
                "confidence": result.confidence,
                "text_characters": len(full_text),
                "regions_total": len(result.regions),
                "regions_returned": len(regions),
                "warnings": warnings_list,
                "regions": regions,
            }
            manifest_bytes = json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            storage.put_bytes(source["extraction_key"], manifest_bytes, "application/json")
            updates.update({
                "extraction_status": extraction_status,
                "extraction_warnings": warnings_list,
                "region_count": len(result.regions),
                "reference_text": excerpt or None,
                "sha256": sha256(excerpt.encode("utf-8")).hexdigest() if excerpt else None,
            })
        except Exception as exc:
            updates.update({
                "extraction_status": "FAILED",
                "extraction_warnings": [f"SOURCE_PARSE_FAILED: {type(exc).__name__}; manual review is required."],
                "region_count": 0,
                "reference_text": None,
                "sha256": None,
            })
    source.update(updates)
    return source

def _active_pack(user: CurrentActor) -> BrandPack:
    try:
        active_pack = pack_store.active_pack(user.tenant_id, user.brand_id, user.brand_name)
    except (ValueError, OSError, RuntimeError, KeyError) as exc:
        raise HTTPException(503, detail={"code": "BRAND_PACK_UNAVAILABLE", "message": "The active Brand Knowledge Pack could not be loaded."}) from exc
    if active_pack.brand.get("brand_id") != user.brand_id:
        raise HTTPException(409, detail={"code": "BRAND_PACK_CONTEXT_MISMATCH", "message": "The selected brand does not have a matching active Brand Knowledge Pack."})
    return active_pack


def _ensure_submission_access(user: CurrentActor, submission: models.Submission) -> None:
    """Enforce the selected tenant and brand, then apply creator ownership."""
    if submission.tenant_id != user.tenant_id or submission.brand_id != user.brand_id:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Resource not found."})
    if user.role in {Role.CREATOR.value, Role.AGENCY.value} and submission.created_by != user.id:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Resource not found."})


def _workspace_dict(workspace: WorkspaceContext) -> dict:
    return {
        "membership_id": workspace.membership_id,
        "tenant_id": workspace.tenant_id,
        "tenant_name": workspace.tenant_name,
        "brand_record_id": workspace.brand_record_id,
        "brand_id": workspace.brand_id,
        "brand_name": workspace.brand_name,
        "role": workspace.role,
    }


def _user_dict(user: models.User, workspace: WorkspaceContext) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": workspace.role,
        "tenant_id": workspace.tenant_id,
        "tenant_name": workspace.tenant_name,
        "brand_id": workspace.brand_id,
        "brand_record_id": workspace.brand_record_id,
        "brand_name": workspace.brand_name,
    }


def _issue_session(db: Session, user: models.User, workspace: WorkspaceContext) -> dict:
    session_id = str(uuid4())
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.access_token_minutes)
    db.add(models.UserSession(
        id=session_id,
        user_id=user.id,
        membership_id=workspace.membership_id,
        created_at=now,
        expires_at=expires_at,
    ))
    token = create_access_token(user.id, workspace.role, workspace.tenant_id, session_id)
    return {"access_token": token, "user": _user_dict(user, workspace), "workspaces": []}


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: DbSession):
    user = db.scalar(select(models.User).where(models.User.email == payload.email.lower().strip()))
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, detail={"code": "INVALID_CREDENTIALS", "message": "Email or password is incorrect."})

    set_database_scope(db, user_id=user.id)
    workspaces = _workspace_rows(db, user.id)
    if not workspaces:
        raise HTTPException(403, detail={"code": "NO_WORKSPACE_ACCESS", "message": "This account has no active brand workspace membership."})

    selected = None
    if payload.brand_id:
        matches = [
            item for item in workspaces
            if payload.brand_id in {item.brand_record_id, item.brand_id, item.tenant_id}
        ]
        if len(matches) == 1:
            selected = matches[0]
        elif len(matches) > 1:
            raise HTTPException(409, detail={"code": "AMBIGUOUS_WORKSPACE", "message": "The selected brand identifier matches more than one workspace. Use the workspace ID."})
        else:
            raise HTTPException(403, detail={"code": "WORKSPACE_ACCESS_DENIED", "message": "You are not a member of the selected workspace."})
    elif len(workspaces) == 1:
        selected = workspaces[0]
    else:
        raise HTTPException(
            409,
            detail={
                "code": "WORKSPACE_SELECTION_REQUIRED",
                "message": "Select a workspace and brand to continue.",
                "workspaces": [_workspace_dict(item) for item in workspaces],
            },
        )

    session_payload = _issue_session(db, user, selected)
    db.commit()
    session_payload["workspaces"] = [_workspace_dict(item) for item in workspaces]
    return session_payload


@router.get("/auth/me")
def me(user: CurrentUser):
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "tenant_id": user.tenant_id,
        "tenant_name": user.tenant_name,
        "brand_id": user.brand_id,
        "brand_record_id": user.brand_record_id,
        "brand_name": user.brand_name,
        "membership_id": user.membership_id,
    }


@router.get("/auth/workspaces")
def list_my_workspaces(user: CurrentUser):
    return {"workspaces": [_workspace_dict(item) for item in user.workspaces]}


@router.post("/auth/logout")
def logout(user: CurrentUser, db: DbSession):
    session = db.get(models.UserSession, user.session_id)
    if session and session.revoked_at is None:
        session.revoked_at = datetime.now(timezone.utc)
        db.commit()
    return {"status": "revoked"}


@router.post("/auth/switch-context", response_model=TokenResponse)
def switch_context(payload: WorkspaceSwitchRequest, user: CurrentUser, db: DbSession):
    matches = [item for item in user.workspaces if payload.brand_id in {item.brand_record_id, item.brand_id}]
    if len(matches) != 1:
        raise HTTPException(403, detail={"code": "WORKSPACE_ACCESS_DENIED", "message": "You are not a member of the selected workspace."})
    current_session = db.get(models.UserSession, user.session_id)
    if current_session and current_session.revoked_at is None:
        current_session.revoked_at = datetime.now(timezone.utc)
    db.flush()
    basic_user = db.get(models.User, user.id)
    result = _issue_session(db, basic_user, matches[0])
    db.commit()
    result["workspaces"] = [_workspace_dict(item) for item in user.workspaces]
    return result

def _lock_membership_workspace(db: Session, user: CurrentActor) -> None:
    """Serialize membership mutations for one brand.

    This closes the concurrent last-administrator race: two requests cannot
    each observe the other active administrator and then remove both.
    """
    brand = db.scalar(
        select(models.Brand)
        .where(
            models.Brand.id == user.brand_record_id,
            models.Brand.tenant_id == user.tenant_id,
        )
        .with_for_update()
    )
    if not brand:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Workspace brand not found."})


@router.get("/workspace/memberships")
def list_workspace_memberships(user=Depends(require_roles(Role.BRAND_OWNER, Role.ADMINISTRATOR)), db: DbSession = None):
    query = (
        select(models.Membership, models.User)
        .join(models.User, models.User.id == models.Membership.user_id)
        .where(
            models.Membership.tenant_id == user.tenant_id,
            models.Membership.brand_id == user.brand_record_id,
        )
        .order_by(models.User.display_name)
    )
    return [
        {
            "membership_id": membership.id,
            "user_id": member.id,
            "email": member.email,
            "display_name": member.display_name,
            "role": membership.role,
            "is_active": membership.is_active,
            "created_at": membership.created_at,
        }
        for membership, member in db.execute(query).all()
    ]


@router.post("/workspace/memberships")
def add_workspace_membership(
    payload: MembershipCreateRequest,
    user=Depends(require_roles(Role.BRAND_OWNER, Role.ADMINISTRATOR)),
    db: DbSession = None,
):
    _lock_membership_workspace(db, user)
    role = payload.role.strip().lower()
    allowed_roles = {item.value for item in Role}
    if role not in allowed_roles:
        raise HTTPException(422, detail={"code": "INVALID_ROLE", "message": "The requested workspace role is not supported."})
    if user.role == Role.BRAND_OWNER.value and role not in {Role.CREATOR.value, Role.AGENCY.value, Role.REVIEWER.value}:
        raise HTTPException(403, detail={"code": "ROLE_GRANT_NOT_ALLOWED", "message": "Brand owners may add creators, agency contributors and reviewers; elevated privileges require an administrator."})
    target = db.scalar(select(models.User).where(models.User.email == payload.email.lower().strip()))
    if not target:
        raise HTTPException(404, detail={"code": "USER_NOT_FOUND", "message": "Create or invite the user account before adding a workspace membership."})
    if not target.is_active:
        raise HTTPException(409, detail={"code": "USER_INACTIVE", "message": "An inactive user cannot be added to a workspace."})
    existing = db.scalar(
        select(models.Membership).where(
            models.Membership.user_id == target.id,
            models.Membership.brand_id == user.brand_record_id,
        )
    )
    if existing:
        raise HTTPException(409, detail={"code": "MEMBERSHIP_EXISTS", "message": "This user already has a membership in the selected brand."})
    membership = models.Membership(
        user_id=target.id,
        tenant_id=user.tenant_id,
        brand_id=user.brand_record_id,
        role=role,
        is_active=True,
    )
    db.add(membership)
    db.flush()
    audit(db, user.tenant_id, user.id, "WORKSPACE_MEMBERSHIP_CREATED", "membership", membership.id,
          {"member_user_id": target.id, "role": role}, brand_id=user.brand_id)
    db.commit()
    return {"membership_id": membership.id, "user_id": target.id, "email": target.email, "role": role, "is_active": True}


@router.patch("/workspace/memberships/{membership_id}")
def update_workspace_membership(
    membership_id: str,
    payload: MembershipUpdateRequest,
    user=Depends(require_roles(Role.ADMINISTRATOR)),
    db: DbSession = None,
):
    _lock_membership_workspace(db, user)
    membership = db.scalar(
        select(models.Membership).where(
            models.Membership.id == membership_id,
            models.Membership.tenant_id == user.tenant_id,
            models.Membership.brand_id == user.brand_record_id,
        )
    )
    if not membership:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Membership not found."})
    if payload.role is None and payload.is_active is None:
        raise HTTPException(422, detail={"code": "EMPTY_MEMBERSHIP_UPDATE", "message": "Provide a new role or active status."})
    previous_role = membership.role
    requested_role = previous_role
    if payload.role is not None:
        requested_role = payload.role.strip().lower()
        if requested_role not in {item.value for item in Role}:
            raise HTTPException(422, detail={"code": "INVALID_ROLE", "message": "The requested workspace role is not supported."})

    if payload.is_active is False and membership.user_id == user.id and membership.is_active:
        raise HTTPException(409, detail={"code": "SELF_DEACTIVATION_BLOCKED", "message": "Administrators cannot deactivate their own active membership."})

    is_admin_demotion = membership.is_active and previous_role == Role.ADMINISTRATOR.value and (
        payload.is_active is False or requested_role != Role.ADMINISTRATOR.value
    )
    if is_admin_demotion:
        other_admins = db.scalar(
            select(func.count()).select_from(models.Membership).where(
                models.Membership.tenant_id == user.tenant_id,
                models.Membership.brand_id == user.brand_record_id,
                models.Membership.role == Role.ADMINISTRATOR.value,
                models.Membership.is_active.is_(True),
                models.Membership.id != membership.id,
            )
        ) or 0
        if other_admins == 0:
            raise HTTPException(409, detail={"code": "LAST_ADMIN_PROTECTED", "message": "The last active brand administrator cannot be deactivated or demoted."})

    if payload.role is not None:
        membership.role = requested_role
    if payload.is_active is not None:
        membership.is_active = payload.is_active
    audit(db, user.tenant_id, user.id, "WORKSPACE_MEMBERSHIP_UPDATED", "membership", membership.id,
          {"role": membership.role, "is_active": membership.is_active}, brand_id=user.brand_id)
    db.commit()
    return {"membership_id": membership.id, "role": membership.role, "is_active": membership.is_active}


@router.get("/brands/current")
def current_brand(user: CurrentUser):
    active_pack = _active_pack(user)
    metadata = pack_store.active_metadata(user.tenant_id, user.brand_id, user.brand_name)
    return {
        "brand": active_pack.brand,
        "pack_version": active_pack.version(),
        "pack_version_id": metadata["version_id"],
        "knowledge_pack_hash": metadata["fingerprint"],
        "policies": len(active_pack.policies),
        "facts": len(active_pack.facts),
    }


@router.get("/brands/current/management")
def brand_management(user=Depends(require_roles(Role.BRAND_OWNER, Role.REVIEWER, Role.ADMINISTRATOR))):
    active_pack = _active_pack(user)
    metadata = pack_store.active_metadata(user.tenant_id, user.brand_id, user.brand_name)
    return {
        "brand": active_pack.brand,
        "snapshot": active_pack.snapshot(),
        "active_version": metadata,
        "versions": pack_store.list_versions(user.tenant_id, user.brand_id, user.brand_name),
        "can_edit": user.role == Role.BRAND_OWNER.value,
    }


@router.get("/brands/current/versions")
def brand_versions(user=Depends(require_roles(Role.BRAND_OWNER, Role.REVIEWER, Role.ADMINISTRATOR))):
    return {"versions": pack_store.list_versions(user.tenant_id, user.brand_id, user.brand_name)}


@router.get("/brands/current/versions/compare")
def compare_brand_knowledge_versions(
    from_version_id: str, to_version_id: str,
    user=Depends(require_roles(Role.BRAND_OWNER, Role.REVIEWER, Role.ADMINISTRATOR)),
):
    try:
        return pack_store.compare_versions(
            user.tenant_id, user.brand_id, from_version_id, to_version_id, user.brand_name
        )
    except FileNotFoundError:
        raise HTTPException(404, detail={"code": "KNOWLEDGE_PACK_VERSION_NOT_FOUND", "message": "One or both requested Knowledge Pack versions were not found in the selected brand."})
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "INVALID_VERSION_COMPARISON", "message": str(exc)}) from exc


@router.post("/brands/current/drafts")
def create_brand_draft(user=Depends(require_roles(Role.BRAND_OWNER)), db: Session = Depends(get_db)):
    draft = pack_store.create_draft(user.tenant_id, user.id, user.brand_id, user.brand_name)
    audit(db, user.tenant_id, user.id, "BRAND_KNOWLEDGE_DRAFT_CREATED", "brand_knowledge_draft", draft["draft_id"], {"base_version_id": draft["base_version_id"]}, brand_id=user.brand_id)
    db.commit()
    return {"draft_id": draft["draft_id"], "base_version_id": draft["base_version_id"], "status": draft["status"], "snapshot": draft["snapshot"]}


@router.get("/brands/current/drafts/{draft_id}")
def get_brand_draft(draft_id: str, user=Depends(require_roles(Role.BRAND_OWNER))):
    try:
        draft = pack_store.get_draft(user.tenant_id, draft_id, user.brand_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, detail={"code": "DRAFT_NOT_FOUND", "message": "Knowledge Pack draft not found."})
    return draft


@router.get("/brands/current/drafts/{draft_id}/decisions")
def list_brand_draft_decisions(
    draft_id: str,
    user=Depends(require_roles(Role.BRAND_OWNER, Role.REVIEWER, Role.ADMINISTRATOR)),
):
    try:
        return {"decisions": pack_store.list_decisions(user.tenant_id, draft_id, user.brand_id)}
    except FileNotFoundError:
        raise HTTPException(404, detail={"code": "DRAFT_NOT_FOUND", "message": "Knowledge Pack draft not found."})


@router.put("/brands/current/drafts/{draft_id}/section")
def update_brand_draft_section(draft_id: str, payload: KnowledgePackSectionUpdate, user=Depends(require_roles(Role.BRAND_OWNER)), db: Session = Depends(get_db)):
    try:
        draft = pack_store.update_section(user.tenant_id, draft_id, payload.section, payload.content, user.id, user.brand_id)
    except FileNotFoundError:
        raise HTTPException(404, detail={"code": "DRAFT_NOT_FOUND", "message": "Knowledge Pack draft not found."})
    except ValueError as exc:
        if "changed in another session" in str(exc):
            raise HTTPException(409, detail={"code": "STALE_DRAFT_REVISION", "message": str(exc)}) from exc
        raise HTTPException(422, detail={"code": "INVALID_DRAFT_UPDATE", "message": str(exc)}) from exc
    audit(db, user.tenant_id, user.id, "BRAND_KNOWLEDGE_DRAFT_SECTION_UPDATED", "brand_knowledge_draft", draft_id, {"section": payload.section}, brand_id=user.brand_id)
    db.commit()
    return {
        "draft_id": draft["draft_id"], "status": draft["status"],
        "updated_at": draft["updated_at"], "section": payload.section,
        "content": draft["snapshot"].get(payload.section),
    }


@router.post("/brands/current/drafts/{draft_id}/validate")
def validate_brand_draft(draft_id: str, user=Depends(require_roles(Role.BRAND_OWNER)), db: Session = Depends(get_db)):
    try:
        storage = get_storage(settings)
        result = pack_store.validate_draft(
            user.tenant_id, draft_id, user.brand_id,
            asset_exists=storage.exists,
            asset_hash=lambda key: sha256(storage.get_bytes(key)).hexdigest(),
        )
    except FileNotFoundError:
        raise HTTPException(404, detail={"code": "DRAFT_NOT_FOUND", "message": "Knowledge Pack draft not found."})
    except ValueError as exc:
        if "changed in another session" in str(exc):
            raise HTTPException(409, detail={"code": "STALE_DRAFT_REVISION", "message": str(exc)}) from exc
        raise HTTPException(422, detail={"code": "INVALID_DRAFT", "message": str(exc)}) from exc
    audit(db, user.tenant_id, user.id, "BRAND_KNOWLEDGE_DRAFT_VALIDATED", "brand_knowledge_draft", draft_id, {"valid": result["valid"], "error_count": len(result["errors"])}, brand_id=user.brand_id)
    db.commit()
    return result


@router.post("/brands/current/drafts/{draft_id}/publish")
def publish_brand_draft(draft_id: str, user=Depends(require_roles(Role.BRAND_OWNER)), db: Session = Depends(get_db)):
    try:
        metadata = pack_store.publish_draft(user.tenant_id, draft_id, user.id, user.brand_id)
    except FileNotFoundError:
        raise HTTPException(404, detail={"code": "DRAFT_NOT_FOUND", "message": "Knowledge Pack draft not found."})
    except RuntimeError as exc:
        raise HTTPException(409, detail={"code": "STALE_KNOWLEDGE_DRAFT", "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "KNOWLEDGE_PACK_NOT_PUBLISHABLE", "message": str(exc)}) from exc
    audit(db, user.tenant_id, user.id, "BRAND_KNOWLEDGE_PACK_PUBLISHED", "brand_knowledge_pack", metadata["version_id"], metadata, brand_id=user.brand_id)
    db.commit()
    return metadata


@router.post("/brands/current/drafts/{draft_id}/sources")
def add_brand_source(
    draft_id: str,
    payload: KnowledgeSourceCreateRequest,
    user=Depends(require_roles(Role.BRAND_OWNER)),
    db: Session = Depends(get_db),
):
    reference_text = (payload.reference_text or "").strip()
    source_uri = (payload.source_uri or "").strip()
    if not reference_text and not source_uri:
        raise HTTPException(422, detail={"code": "SOURCE_EVIDENCE_REQUIRED", "message": "Provide reference text or a source URI."})
    if source_uri and not source_uri.lower().startswith(("https://", "http://")):
        raise HTTPException(422, detail={"code": "SOURCE_URI_UNSUPPORTED", "message": "Source URIs must use HTTP or HTTPS. Sigillum will not fetch them automatically."})
    if payload.source_type.strip().lower() not in {"reference_text", "policy_document", "product_specification", "campaign_terms", "guideline", "other"}:
        raise HTTPException(422, detail={"code": "SOURCE_TYPE_UNSUPPORTED", "message": "Unsupported source type."})
    source_id = f"SRC-{uuid4().hex[:16].upper()}"
    source = {
        "source_id": source_id,
        "name": payload.name.strip(),
        "source_type": payload.source_type.strip().lower(),
        "version": payload.version,
        "reference_text": reference_text or None,
        "source_uri": source_uri or None,
        "sha256": sha256(reference_text.encode("utf-8")).hexdigest() if reference_text else None,
        "owner_id": user.id,
        "status": "draft",
        "valid_from": payload.valid_from,
        "valid_until": payload.valid_until,
        "created_by": user.id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        draft = pack_store.get_draft(user.tenant_id, draft_id, user.brand_id)
        pack_store.append_source(user.tenant_id, user.brand_id, draft_id, source, user.id)
    except FileNotFoundError:
        raise HTTPException(404, detail={"code": "DRAFT_NOT_FOUND", "message": "Knowledge Pack draft not found."})
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "INVALID_SOURCE", "message": str(exc)}) from exc
    audit(db, user.tenant_id, user.id, "BRAND_KNOWLEDGE_SOURCE_CREATED", "brand_knowledge_source", source_id,
          {"source_type": source["source_type"], "status": source["status"]}, brand_id=user.brand_id)
    db.commit()
    return {"source": source, "draft_status": draft["status"]}


@router.post("/brands/current/drafts/{draft_id}/sources/upload")
async def upload_brand_source_document(
    draft_id: str,
    file: UploadFile = File(...),
    name: str = Form(...),
    source_type: str = Form(default="policy_document"),
    version: int = Form(default=1),
    valid_from: str | None = Form(default=None),
    valid_until: str | None = Form(default=None),
    user=Depends(require_roles(Role.BRAND_OWNER)),
    db: Session = Depends(get_db),
):
    """Store a private PDF/DOCX source in quarantine, scan it, then extract provenance."""
    source_name = (name or "").strip()
    allowed_types = {"reference_text", "policy_document", "product_specification", "campaign_terms", "guideline", "other"}
    if not source_name or len(source_name) > 240:
        raise HTTPException(422, detail={"code": "SOURCE_NAME_INVALID", "message": "Source name must contain 1 to 240 characters."})
    if source_type not in allowed_types:
        raise HTTPException(422, detail={"code": "SOURCE_TYPE_UNSUPPORTED", "message": "Unsupported uploaded source type."})
    if version < 1 or version > 100000:
        raise HTTPException(422, detail={"code": "SOURCE_VERSION_INVALID", "message": "Source version must be a positive integer."})
    original_filename = Path(file.filename or "source-document").name[:240]
    extension = Path(original_filename).suffix.lower()
    if extension not in {".pdf", ".docx"}:
        await file.close()
        raise HTTPException(415, detail={"code": "SOURCE_DOCUMENT_TYPE_UNSUPPORTED", "message": "Knowledge source uploads currently accept PDF and DOCX only."})
    raw = await file.read(settings.max_upload_bytes + 1)
    await file.close()
    if not raw:
        raise HTTPException(422, detail={"code": "EMPTY_SOURCE_DOCUMENT", "message": "The uploaded source document is empty."})
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(413, detail={"code": "SOURCE_DOCUMENT_TOO_LARGE", "message": "The uploaded source document exceeds the configured size limit."})
    try:
        mime_type = sniff_file(original_filename, raw)
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "INVALID_SOURCE_DOCUMENT", "message": str(exc)}) from exc
    if mime_type not in {"application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}:
        raise HTTPException(415, detail={"code": "SOURCE_DOCUMENT_TYPE_UNSUPPORTED", "message": "Knowledge source uploads currently accept PDF and DOCX only."})
    try:
        draft = pack_store.get_draft(user.tenant_id, draft_id, user.brand_id)
        if draft.get("status") == "PUBLISHED":
            raise HTTPException(409, detail={"code": "DRAFT_IMMUTABLE", "message": "Published Knowledge Pack drafts cannot accept new sources."})
        source_id = f"SRC-{uuid4().hex[:16].upper()}"
        file_digest = sha256(raw).hexdigest()
        safe_extension = "pdf" if mime_type == "application/pdf" else "docx"
        storage_key = f"brand-source-documents/{user.tenant_id}/{user.brand_id}/{draft_id}/{source_id}/original.{safe_extension}"
        extraction_key = f"brand-source-extractions/{user.tenant_id}/{user.brand_id}/{draft_id}/{source_id}/extraction.json"
        source = {
            "source_id": source_id, "name": source_name, "source_type": source_type, "version": version,
            "source_format": safe_extension, "original_filename": original_filename, "mime_type": mime_type,
            "size_bytes": len(raw), "file_sha256": file_digest, "storage_key": storage_key,
            "extraction_key": extraction_key, "reference_text": None, "sha256": None,
            "owner_id": user.id, "uploaded_by": user.id, "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "status": "draft", "scan_status": "PENDING", "scan_engine": "clamav",
            "scan_scanned_at": None, "scan_signature": None, "extraction_status": "PENDING_SCAN",
            "extraction_warnings": [], "region_count": 0, "valid_from": valid_from, "valid_until": valid_until,
            "created_by": user.id, "created_at": datetime.now(timezone.utc).isoformat(),
        }
        storage = get_storage(settings)
        storage.put_bytes(storage_key, raw, mime_type)
        _scan_document_and_extract(source, raw, storage)
        pack_store.append_source(user.tenant_id, user.brand_id, draft_id, source, user.id)
    except FileNotFoundError:
        raise HTTPException(404, detail={"code": "DRAFT_NOT_FOUND", "message": "Knowledge Pack draft not found."})
    except StorageUnavailable as exc:
        raise HTTPException(503, detail={"code": "STORAGE_UNAVAILABLE", "message": "Private source storage is unavailable; the document was not registered."}) from exc
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "INVALID_SOURCE_DOCUMENT", "message": str(exc)}) from exc
    audit(db, user.tenant_id, user.id, "BRAND_KNOWLEDGE_SOURCE_DOCUMENT_UPLOADED", "brand_knowledge_source", source_id,
          {"source_format": safe_extension, "scan_status": source["scan_status"], "extraction_status": source["extraction_status"], "file_sha256": file_digest}, brand_id=user.brand_id)
    db.commit()
    return {"source": source, "draft_id": draft_id, "draft_status": "DRAFT", "authoritative": False}


@router.post("/brands/current/drafts/{draft_id}/sources/{source_id}/versions/upload")
async def upload_replacement_brand_source_document(
    draft_id: str,
    source_id: str,
    file: UploadFile = File(...),
    valid_from: str | None = Form(default=None),
    valid_until: str | None = Form(default=None),
    user=Depends(require_roles(Role.BRAND_OWNER)),
    db: Session = Depends(get_db),
):
    """Upload version N+1 of a source and supersede N only inside the draft."""
    try:
        draft = pack_store.get_draft(user.tenant_id, draft_id, user.brand_id)
    except FileNotFoundError:
        raise HTTPException(404, detail={"code": "DRAFT_NOT_FOUND", "message": "Knowledge Pack draft not found."})
    source_rows = (draft.get("snapshot", {}).get("sources", {}) or {}).get("sources", [])
    previous = next((item for item in source_rows if isinstance(item, dict) and item.get("source_id") == source_id), None)
    if not previous:
        raise HTTPException(404, detail={"code": "SOURCE_NOT_FOUND", "message": "Source version to replace was not found."})
    if previous.get("status") == "superseded":
        raise HTTPException(409, detail={"code": "SOURCE_ALREADY_SUPERSEDED", "message": "Replace the latest source version, not a superseded version."})
    original_filename = Path(file.filename or "source-document").name[:240]
    extension = Path(original_filename).suffix.lower()
    if extension not in {".pdf", ".docx"}:
        await file.close()
        raise HTTPException(415, detail={"code": "SOURCE_DOCUMENT_TYPE_UNSUPPORTED", "message": "Replacement source uploads accept PDF and DOCX only."})
    raw = await file.read(settings.max_upload_bytes + 1)
    await file.close()
    if not raw:
        raise HTTPException(422, detail={"code": "EMPTY_SOURCE_DOCUMENT", "message": "The uploaded source document is empty."})
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(413, detail={"code": "SOURCE_DOCUMENT_TOO_LARGE", "message": "The uploaded source document exceeds the configured size limit."})
    try:
        mime_type = sniff_file(original_filename, raw)
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "INVALID_SOURCE_DOCUMENT", "message": str(exc)}) from exc
    if mime_type not in {"application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}:
        raise HTTPException(415, detail={"code": "SOURCE_DOCUMENT_TYPE_UNSUPPORTED", "message": "Replacement source uploads accept PDF and DOCX only."})
    new_source_id = f"SRC-{uuid4().hex[:16].upper()}"
    try:
        version = int(previous.get("version", 1)) + 1
    except (TypeError, ValueError) as exc:
        raise HTTPException(409, detail={"code": "SOURCE_VERSION_INVALID", "message": "The previous source version is invalid."}) from exc
    digest = sha256(raw).hexdigest()
    safe_extension = "pdf" if mime_type == "application/pdf" else "docx"
    storage_key = f"brand-source-documents/{user.tenant_id}/{user.brand_id}/{draft_id}/{new_source_id}/original.{safe_extension}"
    extraction_key = f"brand-source-extractions/{user.tenant_id}/{user.brand_id}/{draft_id}/{new_source_id}/extraction.json"
    source = {
        "source_id": new_source_id, "name": str(previous.get("name", "")),
        "source_type": str(previous.get("source_type", "other")), "version": version,
        "source_format": safe_extension, "original_filename": original_filename, "mime_type": mime_type,
        "size_bytes": len(raw), "file_sha256": digest, "storage_key": storage_key,
        "extraction_key": extraction_key, "reference_text": None, "sha256": None,
        "owner_id": user.id, "uploaded_by": user.id, "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "status": "draft", "scan_status": "PENDING", "scan_engine": "clamav",
        "scan_scanned_at": None, "scan_signature": None, "extraction_status": "PENDING_SCAN",
        "extraction_warnings": [], "region_count": 0,
        "valid_from": valid_from if valid_from is not None else previous.get("valid_from"),
        "valid_until": valid_until if valid_until is not None else previous.get("valid_until"),
        "created_by": user.id, "created_at": datetime.now(timezone.utc).isoformat(),
    }
    storage = get_storage(settings)
    try:
        storage.put_bytes(storage_key, raw, mime_type)
        _scan_document_and_extract(source, raw, storage)
        if source.get("scan_status") != "CLEAN" or source.get("extraction_status") != "COMPLETED":
            cleanup_pending = []
            for key in (storage_key, extraction_key):
                try:
                    storage.delete_bytes(key)
                except StorageUnavailable:
                    cleanup_pending.append(key)
            audit(
                db, user.tenant_id, user.id, "BRAND_KNOWLEDGE_SOURCE_VERSION_REPLACEMENT_BLOCKED",
                "brand_knowledge_source", source_id,
                {"scan_status": source.get("scan_status"), "extraction_status": source.get("extraction_status"),
                 "cleanup_pending": bool(cleanup_pending), "cleanup_item_count": len(cleanup_pending)},
                brand_id=user.brand_id,
            )
            db.commit()
            raise HTTPException(
                423,
                detail={
                    "code": "SOURCE_REPLACEMENT_NOT_READY",
                    "message": "The prior source version was left unchanged because the replacement did not pass malware scanning and complete extraction.",
                    "scan_status": source.get("scan_status"),
                    "extraction_status": source.get("extraction_status"),
                    "cleanup_pending": bool(cleanup_pending),
                },
            )
        updated = pack_store.append_source_version(user.tenant_id, user.brand_id, draft_id, source_id, source, user.id)
    except FileNotFoundError:
        storage.delete_bytes(storage_key)
        raise HTTPException(404, detail={"code": "SOURCE_NOT_FOUND", "message": "Source version to replace was not found."})
    except ValueError as exc:
        storage.delete_bytes(storage_key)
        if storage.exists(extraction_key):
            storage.delete_bytes(extraction_key)
        raise HTTPException(409, detail={"code": "SOURCE_REPLACEMENT_REJECTED", "message": str(exc)}) from exc
    except StorageUnavailable as exc:
        raise HTTPException(503, detail={"code": "STORAGE_UNAVAILABLE", "message": "Private source storage is unavailable."}) from exc
    audit(db, user.tenant_id, user.id, "BRAND_KNOWLEDGE_SOURCE_VERSION_UPLOADED", "brand_knowledge_source", new_source_id,
          {"supersedes_source_id": source_id, "version": version, "scan_status": source["scan_status"], "file_sha256": digest}, brand_id=user.brand_id)
    db.commit()
    new_draft = updated
    return {"source": source, "superseded_source_id": source_id, "draft_id": draft_id, "draft_status": new_draft["status"], "authoritative": False}


@router.get("/brands/current/drafts/{draft_id}/sources/{source_id}/versions/compare")
def compare_brand_source_versions(
    draft_id: str, source_id: str,
    user=Depends(require_roles(Role.BRAND_OWNER)),
):
    """Compare a source version with its immediate predecessor/successor.

    Only the authenticated Brand Owner can retrieve this source-derived diff;
    storage keys and private extraction object references are never returned.
    """
    try:
        draft = pack_store.get_draft(user.tenant_id, draft_id, user.brand_id)
    except FileNotFoundError:
        raise HTTPException(404, detail={"code": "DRAFT_NOT_FOUND", "message": "Knowledge Pack draft not found."})
    rows = (draft.get("snapshot", {}).get("sources", {}) or {}).get("sources", [])
    indexed = {str(item.get("source_id")): item for item in rows if isinstance(item, dict)}
    selected = indexed.get(source_id)
    if selected is None:
        raise HTTPException(404, detail={"code": "SOURCE_NOT_FOUND", "message": "Draft source not found."})
    if selected.get("supersedes_source_id"):
        older = indexed.get(str(selected["supersedes_source_id"]))
        newer = selected
    elif selected.get("superseded_by"):
        older = selected
        newer = indexed.get(str(selected["superseded_by"]))
    else:
        raise HTTPException(409, detail={"code": "SOURCE_VERSION_COMPARISON_UNAVAILABLE", "message": "This source has no immediate replacement version in the current draft."})
    if older is None or newer is None or str(newer.get("supersedes_source_id", "")) != str(older.get("source_id", "")):
        raise HTTPException(409, detail={"code": "SOURCE_VERSION_LINEAGE_INVALID", "message": "The source version chain is incomplete and cannot be compared."})

    before_text = str(older.get("reference_text") or "")[:20000]
    after_text = str(newer.get("reference_text") or "")[:20000]
    comparison_available = bool(before_text.strip() and after_text.strip())
    diff_lines: list[str] = []
    added_lines = removed_lines = 0
    if comparison_available:
        diff_lines = list(difflib.unified_diff(
            before_text.splitlines(), after_text.splitlines(),
            fromfile=f"{older.get('name', 'Source')} v{older.get('version', '?')}",
            tofile=f"{newer.get('name', 'Source')} v{newer.get('version', '?')}",
            lineterm="",
        ))
        added_lines = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
        removed_lines = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
    safe_metadata_fields = ("source_id", "name", "source_type", "version", "status", "file_sha256", "sha256", "scan_status", "extraction_status", "valid_from", "valid_until", "region_count")
    def safe_source(item: dict) -> dict:
        return {key: item.get(key) for key in safe_metadata_fields if key in item}
    return {
        "draft_id": draft_id,
        "from": safe_source(older),
        "to": safe_source(newer),
        "comparison_available": comparison_available,
        "diff": "\n".join(diff_lines[:500])[:50000],
        "diff_truncated": len(diff_lines) > 500 or sum(len(line) + 1 for line in diff_lines[:500]) > 50000,
        "added_line_count": added_lines,
        "removed_line_count": removed_lines,
        "warnings": [] if comparison_available else ["SOURCE_TEXT_UNAVAILABLE: both versions need retained extracted/reference text for a textual comparison."],
    }


@router.delete("/brands/current/drafts/{draft_id}/sources/{source_id}")
def delete_unpublished_brand_source(
    draft_id: str, source_id: str,
    user=Depends(require_roles(Role.BRAND_OWNER)), db: Session = Depends(get_db),
):
    """Delete an unapproved draft source and its private binary/extraction artefacts."""
    try:
        removed = pack_store.remove_unpublished_source(user.tenant_id, user.brand_id, draft_id, source_id, user.id)
    except FileNotFoundError:
        raise HTTPException(404, detail={"code": "SOURCE_NOT_FOUND", "message": "Draft source not found."})
    except ValueError as exc:
        raise HTTPException(409, detail={"code": "SOURCE_DELETE_REJECTED", "message": str(exc)}) from exc

    storage_keys = [removed.get("storage_key"), removed.get("extraction_key")]
    cleanup_pending = []
    storage = get_storage(settings)
    for key in storage_keys:
        if not key:
            continue
        key = str(key)
        allowed_prefixes = (
            f"brand-source-documents/{user.tenant_id}/{user.brand_id}/{draft_id}/",
            f"brand-source-extractions/{user.tenant_id}/{user.brand_id}/{draft_id}/",
        )
        if not key.startswith(allowed_prefixes):
            cleanup_pending.append("untrusted-storage-reference")
            continue
        try:
            storage.delete_bytes(key)
        except StorageUnavailable:
            cleanup_pending.append(key)

    audit(db, user.tenant_id, user.id, "BRAND_KNOWLEDGE_SOURCE_DELETED", "brand_knowledge_source", source_id,
          {"binary_cleanup_pending": bool(cleanup_pending), "cleanup_item_count": len(cleanup_pending)}, brand_id=user.brand_id)
    if cleanup_pending:
        # The source is no longer addressable from the draft. The audit event
        # records that private object cleanup needs operator attention.
        audit(db, user.tenant_id, user.id, "PRIVATE_OBJECT_CLEANUP_PENDING", "brand_knowledge_source", source_id,
              {"storage_keys": cleanup_pending}, brand_id=user.brand_id)
    db.commit()
    return {"source_id": source_id, "deleted": True, "binary_cleanup_pending": bool(cleanup_pending)}


@router.post("/brands/current/drafts/{draft_id}/sources/{source_id}/scan")
def rescan_brand_source_document(
    draft_id: str, source_id: str, user=Depends(require_roles(Role.BRAND_OWNER)), db: Session = Depends(get_db),
):
    try:
        draft = pack_store.get_draft(user.tenant_id, draft_id, user.brand_id)
    except FileNotFoundError:
        raise HTTPException(404, detail={"code": "DRAFT_NOT_FOUND", "message": "Knowledge Pack draft not found."})
    sources = (draft.get("snapshot", {}).get("sources", {}) or {}).get("sources", [])
    source = next((item for item in sources if isinstance(item, dict) and item.get("source_id") == source_id), None)
    if not source or not source.get("storage_key"):
        raise HTTPException(404, detail={"code": "SOURCE_NOT_FOUND", "message": "Uploaded source document not found."})
    expected_prefix = f"brand-source-documents/{user.tenant_id}/{user.brand_id}/{draft_id}/"
    if not str(source["storage_key"]).startswith(expected_prefix):
        raise HTTPException(404, detail={"code": "SOURCE_NOT_FOUND", "message": "Uploaded source document not found."})
    try:
        storage = get_storage(settings)
        raw = storage.get_bytes(source["storage_key"])
    except FileNotFoundError:
        raise HTTPException(404, detail={"code": "SOURCE_OBJECT_MISSING", "message": "The quarantined source file is missing."})
    except StorageUnavailable as exc:
        raise HTTPException(503, detail={"code": "STORAGE_UNAVAILABLE", "message": "Private source storage is unavailable."}) from exc
    if sha256(raw).hexdigest().lower() != str(source.get("file_sha256", "")).lower():
        raise HTTPException(409, detail={"code": "SOURCE_FILE_HASH_MISMATCH", "message": "The quarantined source bytes do not match their recorded SHA-256."})
    updated = dict(source)
    _scan_document_and_extract(updated, raw, storage)
    try:
        pack_store.update_scan_record(user.tenant_id, user.brand_id, draft_id, "source", source_id,
            {key: updated.get(key) for key in ("scan_status", "scan_engine", "scan_scanned_at", "scan_signature", "extraction_key", "extraction_status", "extraction_warnings", "region_count", "reference_text", "sha256")}, user.id)
    except FileNotFoundError:
        raise HTTPException(404, detail={"code": "SOURCE_NOT_FOUND", "message": "Uploaded source document not found."})
    except ValueError as exc:
        raise HTTPException(409, detail={"code": "SOURCE_SCAN_UPDATE_REJECTED", "message": str(exc)}) from exc
    audit(db, user.tenant_id, user.id, "BRAND_KNOWLEDGE_SOURCE_RESCANNED", "brand_knowledge_source", source_id,
          {"scan_status": updated["scan_status"], "extraction_status": updated["extraction_status"]}, brand_id=user.brand_id)
    db.commit()
    return {"source_id": source_id, "scan_status": updated["scan_status"], "extraction_status": updated["extraction_status"], "extraction_warnings": updated["extraction_warnings"]}


@router.get("/brands/current/drafts/{draft_id}/sources/{source_id}/download")
def download_brand_source_document(draft_id: str, source_id: str, user=Depends(require_roles(Role.BRAND_OWNER, Role.REVIEWER, Role.ADMINISTRATOR))):
    try:
        draft = pack_store.get_draft(user.tenant_id, draft_id, user.brand_id)
    except FileNotFoundError:
        raise HTTPException(404, detail={"code": "DRAFT_NOT_FOUND", "message": "Knowledge Pack draft not found."})
    sources = (draft.get("snapshot", {}).get("sources", {}) or {}).get("sources", [])
    source = next((item for item in sources if isinstance(item, dict) and item.get("source_id") == source_id), None)
    if not source or source.get("scan_status") != "CLEAN" or not source.get("storage_key"):
        raise HTTPException(423, detail={"code": "SOURCE_QUARANTINED", "message": "The source is not available for download until malware scanning succeeds."})
    expected_prefix = f"brand-source-documents/{user.tenant_id}/{user.brand_id}/{draft_id}/"
    if not str(source["storage_key"]).startswith(expected_prefix):
        raise HTTPException(404, detail={"code": "SOURCE_NOT_FOUND", "message": "Uploaded source document not found."})
    try:
        content = get_storage(settings).get_bytes(source["storage_key"])
    except FileNotFoundError:
        raise HTTPException(404, detail={"code": "SOURCE_OBJECT_MISSING", "message": "The source object is missing from private storage."})
    except StorageUnavailable as exc:
        raise HTTPException(503, detail={"code": "STORAGE_UNAVAILABLE", "message": "Private source storage is unavailable."}) from exc
    if sha256(content).hexdigest().lower() != str(source.get("file_sha256", "")).lower():
        raise HTTPException(409, detail={"code": "SOURCE_FILE_HASH_MISMATCH", "message": "The source bytes do not match the recorded SHA-256."})
    filename = Path(str(source.get("original_filename") or f"{source_id}.bin")).name.replace("\"", "")
    return Response(content=content, media_type=source.get("mime_type", "application/octet-stream"),
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}", "Cache-Control": "no-store"})


@router.get("/brands/current/drafts/{draft_id}/sources/{source_id}/extraction")
def get_brand_source_extraction(draft_id: str, source_id: str, user=Depends(require_roles(Role.BRAND_OWNER, Role.REVIEWER, Role.ADMINISTRATOR))):
    try:
        draft = pack_store.get_draft(user.tenant_id, draft_id, user.brand_id)
    except FileNotFoundError:
        raise HTTPException(404, detail={"code": "DRAFT_NOT_FOUND", "message": "Knowledge Pack draft not found."})
    sources = (draft.get("snapshot", {}).get("sources", {}) or {}).get("sources", [])
    source = next((item for item in sources if isinstance(item, dict) and item.get("source_id") == source_id), None)
    if not source or source.get("scan_status") != "CLEAN" or not source.get("extraction_key"):
        raise HTTPException(423, detail={"code": "SOURCE_QUARANTINED", "message": "Extraction details are unavailable until malware scanning succeeds."})
    expected_prefix = f"brand-source-extractions/{user.tenant_id}/{user.brand_id}/{draft_id}/"
    if not str(source["extraction_key"]).startswith(expected_prefix):
        raise HTTPException(404, detail={"code": "SOURCE_EXTRACTION_NOT_FOUND", "message": "Extraction details not found."})
    try:
        payload = get_storage(settings).get_bytes(source["extraction_key"])
        return json.loads(payload.decode("utf-8"))
    except FileNotFoundError:
        raise HTTPException(404, detail={"code": "SOURCE_EXTRACTION_NOT_FOUND", "message": "Extraction details not found."})
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(409, detail={"code": "SOURCE_EXTRACTION_INVALID", "message": "Stored extraction details are invalid."})
    except StorageUnavailable as exc:
        raise HTTPException(503, detail={"code": "STORAGE_UNAVAILABLE", "message": "Private source storage is unavailable."}) from exc


@router.post("/brands/current/drafts/{draft_id}/records/{record_type}/{record_id}/decision")
def decide_brand_knowledge_record(
    draft_id: str,
    record_type: str,
    record_id: str,
    payload: KnowledgeRecordDecisionRequest,
    user=Depends(require_roles(Role.BRAND_OWNER)),
    db: Session = Depends(get_db),
):
    if not (payload.reason or "").strip():
        raise HTTPException(422, detail={"code": "DECISION_REASON_REQUIRED", "message": "A decision reason is required for Knowledge Pack record approval or rejection."})
    try:
        draft = pack_store.decide_record(
            user.tenant_id, user.brand_id, draft_id, record_type, record_id,
            payload.status, user.id, payload.reason,
        )
    except FileNotFoundError:
        raise HTTPException(404, detail={"code": "KNOWLEDGE_RECORD_NOT_FOUND", "message": "Draft or knowledge record not found."})
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "INVALID_KNOWLEDGE_DECISION", "message": str(exc)}) from exc
    audit(db, user.tenant_id, user.id, "BRAND_KNOWLEDGE_RECORD_DECIDED", f"brand_knowledge_{record_type}", record_id,
          {"status": payload.status, "reason": payload.reason}, brand_id=user.brand_id)
    db.commit()
    return {"draft_id": draft_id, "record_type": record_type, "record_id": record_id, "status": payload.status}


@router.post("/brands/current/drafts/{draft_id}/assets")
async def upload_brand_asset(
    draft_id: str,
    file: UploadFile = File(...),
    name: str = Form(...),
    kind: str = Form(default="logo"),
    user=Depends(require_roles(Role.BRAND_OWNER)),
    db: Session = Depends(get_db),
):
    """Upload a bounded raster brand asset into private object storage as an unapproved draft record."""
    if not name.strip() or len(name.strip()) > 160:
        raise HTTPException(422, detail={"code": "ASSET_NAME_INVALID", "message": "Asset name must contain 1 to 160 characters."})
    if kind not in {"logo", "product_image", "campaign_image", "icon", "other"}:
        raise HTTPException(422, detail={"code": "ASSET_KIND_INVALID", "message": "Unsupported brand asset kind."})
    raw = await file.read(settings.max_upload_bytes + 1)
    await file.close()
    if not raw:
        raise HTTPException(422, detail={"code": "EMPTY_ASSET", "message": "The uploaded asset is empty."})
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(413, detail={"code": "ASSET_TOO_LARGE", "message": "The uploaded asset exceeds the configured size limit."})
    try:
        image = Image.open(BytesIO(raw))
        image_format = (image.format or "").upper()
        width, height = image.size
        if image_format not in {"PNG", "JPEG", "WEBP"}:
            raise ValueError("Only PNG, JPEG and WebP brand assets are supported.")
        if width < 1 or height < 1 or width * height > 40_000_000:
            raise ValueError("Image dimensions exceed the supported limit.")
        image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError) as exc:
        raise HTTPException(422, detail={"code": "INVALID_BRAND_ASSET", "message": str(exc) or "The uploaded file is not a valid supported image."}) from exc

    scan_result = scan_upload_bytes(raw)
    scan_status = str(scan_result.get("status", "ERROR")).upper()
    if scan_status not in {"CLEAN", "INFECTED", "UNAVAILABLE", "ERROR"}:
        scan_status = "ERROR"

    asset_id = f"ASSET-{uuid4().hex[:16].upper()}"
    extension = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}[image_format]
    mime_type = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}[image_format]
    storage_key = f"brand-assets/{user.tenant_id}/{user.brand_id}/{draft_id}/{asset_id}.{extension}"
    digest = sha256(raw).hexdigest()
    asset = {
        "asset_id": asset_id,
        "name": name.strip(),
        "kind": kind,
        "mime_type": mime_type,
        "size_bytes": len(raw),
        "width": width,
        "height": height,
        "sha256": digest,
        "palette": extract_palette(raw),
        "storage_key": storage_key,
        "status": "draft",
        "scan_status": scan_status,
        "scan_engine": scan_result.get("engine") or "clamav",
        "scan_scanned_at": scan_result.get("scanned_at"),
        "scan_signature": scan_result.get("signature"),
        "owner_id": user.id,
        "uploaded_by": user.id,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "valid_from": None,
        "valid_until": None,
    }
    try:
        draft = pack_store.get_draft(user.tenant_id, draft_id, user.brand_id)
        if draft.get("status") == "PUBLISHED":
            raise HTTPException(409, detail={"code": "DRAFT_IMMUTABLE", "message": "Published Knowledge Pack drafts cannot accept new assets."})
        get_storage(settings).put_bytes(storage_key, raw, mime_type)
        pack_store.append_asset(user.tenant_id, user.brand_id, draft_id, asset, user.id)
    except FileNotFoundError:
        raise HTTPException(404, detail={"code": "DRAFT_NOT_FOUND", "message": "Knowledge Pack draft not found."})
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "INVALID_ASSET", "message": str(exc)}) from exc
    except StorageUnavailable as exc:
        raise HTTPException(503, detail={"code": "STORAGE_UNAVAILABLE", "message": "Private brand asset storage is currently unavailable."}) from exc
    audit(db, user.tenant_id, user.id, "BRAND_ASSET_UPLOADED", "brand_asset", asset_id,
          {"sha256": digest, "size_bytes": len(raw), "mime_type": mime_type}, brand_id=user.brand_id)
    db.commit()
    return {"asset": asset, "draft_id": draft_id, "draft_status": "DRAFT"}


@router.get("/brands/current/drafts/{draft_id}/assets/{asset_id}")
def preview_draft_brand_asset(
    draft_id: str,
    asset_id: str,
    user=Depends(require_roles(Role.BRAND_OWNER)),
):
    try:
        draft = pack_store.get_draft(user.tenant_id, draft_id, user.brand_id)
    except FileNotFoundError:
        raise HTTPException(404, detail={"code": "DRAFT_NOT_FOUND", "message": "Knowledge Pack draft not found."})
    assets = (draft.get("snapshot", {}).get("assets") or {}).get("approved_assets", [])
    asset = next((item for item in assets if isinstance(item, dict) and item.get("asset_id") == asset_id), None)
    if not asset or not asset.get("storage_key"):
        raise HTTPException(404, detail={"code": "ASSET_NOT_FOUND", "message": "Draft asset not found."})
    if asset.get("scan_status") != "CLEAN":
        raise HTTPException(423, detail={"code": "ASSET_QUARANTINED", "message": "The asset remains private until malware scanning succeeds."})
    expected_prefix = f"brand-assets/{user.tenant_id}/{user.brand_id}/"
    if not str(asset["storage_key"]).startswith(expected_prefix):
        raise HTTPException(404, detail={"code": "ASSET_NOT_FOUND", "message": "Draft asset not found."})
    try:
        content = get_storage(settings).get_bytes(asset["storage_key"])
    except FileNotFoundError:
        raise HTTPException(404, detail={"code": "ASSET_OBJECT_NOT_FOUND", "message": "Asset object not found."})
    except StorageUnavailable as exc:
        raise HTTPException(503, detail={"code": "STORAGE_UNAVAILABLE", "message": "Private brand asset storage is currently unavailable."}) from exc
    expected_hash = str(asset.get("sha256", "")).lower()
    if not expected_hash or sha256(content).hexdigest() != expected_hash:
        raise HTTPException(409, detail={"code": "ASSET_INTEGRITY_FAILED", "message": "The private asset failed its SHA-256 integrity check and cannot be previewed."})
    return Response(content=content, media_type=asset.get("mime_type", "application/octet-stream"),
                    headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/brands/current/drafts/{draft_id}/assets/{asset_id}/scan")
def rescan_draft_brand_asset(
    draft_id: str, asset_id: str, user=Depends(require_roles(Role.BRAND_OWNER)), db: Session = Depends(get_db),
):
    try:
        draft = pack_store.get_draft(user.tenant_id, draft_id, user.brand_id)
    except FileNotFoundError:
        raise HTTPException(404, detail={"code": "DRAFT_NOT_FOUND", "message": "Knowledge Pack draft not found."})
    assets = (draft.get("snapshot", {}).get("assets", {}) or {}).get("approved_assets", [])
    asset = next((item for item in assets if isinstance(item, dict) and item.get("asset_id") == asset_id), None)
    expected_prefix = f"brand-assets/{user.tenant_id}/{user.brand_id}/{draft_id}/"
    if not asset or not str(asset.get("storage_key", "")).startswith(expected_prefix):
        raise HTTPException(404, detail={"code": "ASSET_NOT_FOUND", "message": "Uploaded draft asset not found."})
    try:
        storage = get_storage(settings)
        raw = storage.get_bytes(asset["storage_key"])
    except FileNotFoundError:
        raise HTTPException(404, detail={"code": "ASSET_OBJECT_MISSING", "message": "The private asset object is missing."})
    except StorageUnavailable as exc:
        raise HTTPException(503, detail={"code": "STORAGE_UNAVAILABLE", "message": "Private asset storage is unavailable."}) from exc
    if sha256(raw).hexdigest().lower() != str(asset.get("sha256", "")).lower():
        raise HTTPException(409, detail={"code": "ASSET_HASH_MISMATCH", "message": "The private asset bytes do not match their recorded SHA-256."})
    result = scan_upload_bytes(raw)
    scan_status = str(result.get("status", "ERROR")).upper()
    if scan_status not in {"CLEAN", "INFECTED", "UNAVAILABLE", "ERROR"}:
        scan_status = "ERROR"
    updates = {
        "scan_status": scan_status,
        "scan_engine": result.get("engine") or "clamav",
        "scan_scanned_at": result.get("scanned_at"),
        "scan_signature": result.get("signature"),
    }
    try:
        pack_store.update_scan_record(user.tenant_id, user.brand_id, draft_id, "asset", asset_id, updates, user.id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(409, detail={"code": "ASSET_SCAN_UPDATE_REJECTED", "message": str(exc)}) from exc
    audit(db, user.tenant_id, user.id, "BRAND_ASSET_RESCANNED", "brand_asset", asset_id, updates, brand_id=user.brand_id)
    db.commit()
    return {"asset_id": asset_id, **updates}


@router.get("/brands/current/assets/{asset_id}")
def get_published_brand_asset(asset_id: str, user: CurrentUser):
    active_pack = _active_pack(user)
    records = (active_pack.assets or {}).get("approved_assets", [])
    asset = next((item for item in records if isinstance(item, dict) and item.get("asset_id") == asset_id and item.get("status") == "approved"), None)
    if not asset:
        raise HTTPException(404, detail={"code": "ASSET_NOT_FOUND", "message": "Approved brand asset not found."})
    if asset.get("storage_key") and asset.get("scan_status") != "CLEAN":
        raise HTTPException(423, detail={"code": "ASSET_QUARANTINED", "message": "The asset is not available because malware scanning has not succeeded."})
    try:
        if asset.get("storage_key"):
            expected_prefix = f"brand-assets/{user.tenant_id}/{user.brand_id}/"
            if not str(asset["storage_key"]).startswith(expected_prefix):
                raise FileNotFoundError(asset["asset_id"])
            content = get_storage(settings).get_bytes(asset["storage_key"])
        elif asset.get("file_path"):
            root = pack_store.active_root(user.tenant_id, user.brand_id, user.brand_name).resolve()
            candidate = (root / asset["file_path"]).resolve()
            if not candidate.is_relative_to(root) or not candidate.is_file():
                raise FileNotFoundError(asset["asset_id"])
            content = candidate.read_bytes()
        else:
            raise FileNotFoundError(asset["asset_id"])
    except FileNotFoundError:
        raise HTTPException(404, detail={"code": "ASSET_OBJECT_NOT_FOUND", "message": "Approved asset object not found."})
    except StorageUnavailable as exc:
        raise HTTPException(503, detail={"code": "STORAGE_UNAVAILABLE", "message": "Private brand asset storage is currently unavailable."}) from exc
    expected_hash = str(asset.get("sha256", "")).lower()
    if expected_hash and sha256(content).hexdigest() != expected_hash:
        raise HTTPException(409, detail={"code": "ASSET_INTEGRITY_FAILED", "message": "The approved asset failed its SHA-256 integrity check and cannot be served."})
    return Response(content=content, media_type=asset.get("mime_type", "application/octet-stream"),
                    headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/dashboard/summary")
def dashboard(user: CurrentUser, db: DbSession):
    tenant=user.tenant_id
    scope = [models.Submission.tenant_id == tenant, models.Submission.brand_id == user.brand_id]
    if user.role in {Role.CREATOR.value, Role.AGENCY.value}:
        scope.append(models.Submission.created_by == user.id)
    total=db.scalar(select(func.count()).select_from(models.Submission).where(*scope)) or 0
    open_reviews=db.scalar(select(func.count()).select_from(models.Submission).where(*scope,models.Submission.status=="NEEDS_REVIEW")) or 0
    approved=db.scalar(select(func.count()).select_from(models.Submission).where(*scope,models.Submission.status=="APPROVED")) or 0
    findings=db.scalar(select(func.count()).select_from(models.Finding).join(models.ReviewRun).join(models.Submission).where(*scope)) or 0
    active_pack = _active_pack(user)
    return {"submissions":total,"needs_review":open_reviews,"approved":approved,"findings":findings,"brand_name":active_pack.brand["brand_name"]}

@router.get("/submissions")
def list_submissions(user: CurrentUser, db: DbSession):
    query = select(models.Submission).where(models.Submission.tenant_id == user.tenant_id, models.Submission.brand_id == user.brand_id)
    if user.role in {Role.CREATOR.value, Role.AGENCY.value}:
        query = query.where(models.Submission.created_by == user.id)
    rows=db.scalars(query.order_by(models.Submission.created_at.desc()).limit(100)).all()
    result=[]
    for row in rows:
        version=db.get(models.ContentVersion,row.current_version_id) if row.current_version_id else None
        result.append({"id":row.id,"title":row.title,"status":row.status,"channel":row.channel,"publication_at":row.publication_at,"created_at":row.created_at,"filename":version.filename if version else None,"version":version.version_number if version else None})
    return result

@router.post("/submissions")
async def create_submission(
    user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
    title: str = Form("Untitled submission"),
    channel: str = Form("direct_web"),
    locale: str = Form("en-IN"),
    geography: str = Form("IN"),
    audience: str = Form("consumer"),
    offer_id: str = Form("OFFER-ORBITA-OCT-NOV-2026"),
    intended_use: str = Form("general"),
    publication_at: str = Form(...),
):
    active_pack = _active_pack(user)
    if channel not in active_pack.brand.get("channels",[]): raise HTTPException(422,detail={"code":"INVALID_CHANNEL","message":"Channel is not supported by the current Brand Knowledge Pack."})
    allowed_uses = {"general", "brand_lockup", "campaign", "product_detail", "social_ad", "email_banner", "website_hero", "packaging"}
    if intended_use not in allowed_uses:
        raise HTTPException(422, detail={"code": "INVALID_INTENDED_USE", "message": "Select a supported intended content use."})
    if locale not in active_pack.brand.get("supported_locales",[]): raise HTTPException(422,detail={"code":"INVALID_LOCALE","message":"Locale is not supported by this demo pack."})
    data=await file.read(settings.max_upload_bytes+1)
    if len(data)>settings.max_upload_bytes: raise HTTPException(413,detail={"code":"UPLOAD_TOO_LARGE","message":f"Maximum file size is {settings.max_upload_bytes//1024//1024} MB."})
    try: mime=sniff_file(file.filename or "upload.txt",data)
    except ValueError as exc: raise HTTPException(415,detail={"code":"INVALID_UPLOAD","message":str(exc)}) from exc
    try: when=datetime.fromisoformat(publication_at.replace("Z","+00:00"))
    except ValueError: raise HTTPException(422,detail={"code":"INVALID_PUBLICATION_DATE","message":"Use an ISO-8601 date/time with timezone."})
    if when.tzinfo is None: raise HTTPException(422,detail={"code":"TIMEZONE_REQUIRED","message":"Publication time must include a timezone."})
    submission=models.Submission(tenant_id=user.tenant_id,brand_id=user.brand_id,title=title.strip()[:240] or "Untitled submission",channel=channel,locale=locale,geography=geography,audience=audience,offer_id=offer_id or None,intended_use=intended_use,publication_at=when.isoformat(),created_by=user.id)
    db.add(submission); db.flush()
    service=ReviewService(db,active_pack,get_storage(settings))
    try:
        version=service.create_version(submission,file.filename or "upload.txt",mime,data,user)
        review, findings=service.run_review(submission,version)
    except StorageUnavailable as exc:
        db.rollback()
        raise HTTPException(
            503,
            detail={"code": "STORAGE_UNAVAILABLE", "message": "Secure content storage is temporarily unavailable. No submission was approved."},
        ) from exc
    except Exception as exc:
        submission.status="PARSE_FAILED"
        audit(db,user.tenant_id,user.id,"SUBMISSION_PARSE_FAILED","submission",submission.id,{"error_type":type(exc).__name__}, brand_id=user.brand_id)
        db.commit()
        raise HTTPException(422,detail={"code":"PARSE_FAILED","message":"The file could not be safely parsed. The failure was recorded and was not treated as approval."}) from exc
    audit(db,user.tenant_id,user.id,"SUBMISSION_CREATED","submission",submission.id,{"content_version_id":version.id,"sha256":version.sha256,"review_id":review.id,"finding_count":len(findings)}, brand_id=user.brand_id)
    db.commit()
    return serialize_review(db,submission,version,review)

@router.get("/submissions/{submission_id}")
def get_submission(submission_id: str, user: CurrentUser, db: DbSession):
    submission=db.get(models.Submission,submission_id)
    if not submission:
        raise HTTPException(404, detail={"code":"NOT_FOUND", "message":"Submission not found."})
    _ensure_submission_access(user, submission)
    version=db.get(models.ContentVersion,submission.current_version_id) if submission.current_version_id else None
    review=db.scalar(select(models.ReviewRun).where(models.ReviewRun.content_version_id==version.id).order_by(models.ReviewRun.created_at.desc())) if version else None
    return serialize_review(db,submission,version,review) if version and review else {"id":submission.id,"title":submission.title,"status":submission.status}


@router.get("/submissions/{submission_id}/history")
def submission_history(submission_id: str, user: CurrentUser, db: DbSession):
    """Return immutable versions and the review/decision context attached to each."""
    submission = db.get(models.Submission, submission_id)
    if not submission:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Submission not found."})
    _ensure_submission_access(user, submission)

    versions = db.scalars(
        select(models.ContentVersion)
        .where(models.ContentVersion.submission_id == submission.id)
        .order_by(models.ContentVersion.version_number.desc())
    ).all()
    history = []
    for version in versions:
        review = db.scalar(
            select(models.ReviewRun)
            .where(models.ReviewRun.content_version_id == version.id)
            .order_by(models.ReviewRun.created_at.desc())
        )
        if review is None:
            history.append(
                {
                    "version_id": version.id,
                    "version_number": version.version_number,
                    "filename": version.filename,
                    "sha256": version.sha256,
                    "created_at": version.created_at,
                    "extraction_status": version.extraction_status,
                    "review_id": None,
                    "review_status": "NOT_RUN",
                    "finding_count": 0,
                    "decisions": [],
                }
            )
            continue

        finding_count = db.scalar(
            select(func.count()).select_from(models.Finding).where(models.Finding.review_id == review.id)
        ) or 0
        decisions = db.scalars(
            select(models.Decision)
            .where(models.Decision.review_id == review.id)
            .order_by(models.Decision.created_at.desc())
        ).all()
        history.append(
            {
                "version_id": version.id,
                "version_number": version.version_number,
                "filename": version.filename,
                "sha256": version.sha256,
                "created_at": version.created_at,
                "extraction_status": version.extraction_status,
                "review_id": review.id,
                "review_status": review.status,
                "brand_pack_version": review.brand_pack_version,
                "knowledge_pack_hash": review.knowledge_pack_hash,
                "analysis_config_version": review.analysis_config_version,
                "finding_count": finding_count,
                "decisions": [
                    {
                        "action": decision.action,
                        "reason": decision.reason,
                        "content_hash": decision.content_hash,
                        "created_at": decision.created_at,
                    }
                    for decision in decisions
                ],
            }
        )
    return {"submission_id": submission.id, "current_version_id": submission.current_version_id, "versions": history}

def _original_file_response(version: models.ContentVersion) -> Response:
    storage = get_storage(settings)
    try:
        content = storage.get_bytes(version.storage_key)
    except FileNotFoundError as exc:
        raise HTTPException(
            404,
            detail={"code": "ARTEFACT_UNAVAILABLE", "message": "The original artefact is not available."},
        ) from exc
    except StorageUnavailable as exc:
        raise HTTPException(
            503,
            detail={"code": "STORAGE_UNAVAILABLE", "message": "Original content storage is temporarily unavailable."},
        ) from exc

    if sha256(content).hexdigest() != version.sha256:
        raise HTTPException(
            503,
            detail={"code": "ARTEFACT_INTEGRITY_FAILURE", "message": "The stored original failed its integrity check."},
        )
    safe_filename = Path(version.filename).name.replace("\r", "").replace("\n", "")
    return Response(
        content=content,
        media_type=version.mime_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(safe_filename)}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/content-versions/{version_id}/download")
def download_version(version_id: str, user: CurrentUser, db: DbSession):
    version = db.get(models.ContentVersion, version_id)
    if not version:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Content version not found."})
    submission = db.get(models.Submission, version.submission_id)
    if not submission:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Content version not found."})
    _ensure_submission_access(user, submission)
    return _original_file_response(version)


@router.post("/content-versions/{version_id}/grant", response_model=FileGrantResponse)
def create_download_grant(version_id: str, user: CurrentUser, db: DbSession):
    version = db.get(models.ContentVersion, version_id)
    if not version:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Content version not found."})
    submission = db.get(models.Submission, version.submission_id)
    if not submission:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Content version not found."})
    _ensure_submission_access(user, submission)
    token = create_file_grant_token(
        user_id=user.id,
        session_id=user.session_id,
        membership_id=user.membership_id,
        tenant_id=user.tenant_id,
        brand_id=user.brand_id,
        brand_record_id=user.brand_record_id,
        version_id=version.id,
    )
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.file_grant_minutes)
    return {
        "download_url": f"{settings.api_v1_prefix}/content-grants/{quote(token, safe='')}",
        "expires_at": expires_at,
        "expires_in_seconds": settings.file_grant_minutes * 60,
    }


@router.get("/content-grants/{grant_token}")
def download_with_grant(grant_token: str, db: DbSession):
    try:
        payload = decode_access_token(grant_token)
    except Exception as exc:
        raise HTTPException(401, detail={"code": "INVALID_FILE_GRANT", "message": "The file grant is invalid or expired."}) from exc
    if payload.get("purpose") != "file_download":
        raise HTTPException(401, detail={"code": "INVALID_FILE_GRANT", "message": "The token is not a file download grant."})

    user_id = str(payload.get("sub") or "")
    session_id = str(payload.get("session_id") or "")
    membership_id = str(payload.get("membership_id") or "")
    set_database_scope(db, user_id=user_id)
    actor = db.get(models.User, user_id)
    session = db.get(models.UserSession, session_id)
    membership = db.get(models.Membership, membership_id)
    now = datetime.now(timezone.utc)
    if (
        not actor or not actor.is_active or not session or session.user_id != user_id
        or session.membership_id != membership_id or session.revoked_at is not None
        or session.expires_at.replace(tzinfo=session.expires_at.tzinfo or timezone.utc) <= now
        or not membership or membership.user_id != user_id or not membership.is_active
        or membership.tenant_id != payload.get("tenant_id")
        or membership.brand_id != payload.get("brand_record_id")
    ):
        raise HTTPException(401, detail={"code": "INVALID_FILE_GRANT", "message": "The file grant's user session or workspace membership is no longer active."})

    tenant = db.get(models.Tenant, membership.tenant_id)
    brand = db.get(models.Brand, membership.brand_id)
    if not tenant or not tenant.is_active or not brand or not brand.is_active or brand.external_id != payload.get("brand_id"):
        raise HTTPException(403, detail={"code": "WORKSPACE_UNAVAILABLE", "message": "The grant's workspace is no longer available."})
    set_database_scope(
        db,
        user_id=user_id,
        tenant_id=tenant.id,
        brand_id=brand.external_id,
        brand_record_id=brand.id,
        membership_role=membership.role,
    )
    version = db.get(models.ContentVersion, str(payload.get("version_id") or ""))
    if not version:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Content version not found."})
    submission = db.get(models.Submission, version.submission_id)
    if not submission or submission.tenant_id != tenant.id or submission.brand_id != brand.external_id:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Content version not found."})
    return _original_file_response(version)

@router.get("/reviews/{review_id}")
def get_review(review_id: str, user: CurrentUser, db: DbSession):
    review=db.get(models.ReviewRun,review_id)
    if not review:
        # UI routes may start from the submission ID; resolve its current immutable version.
        submission=db.get(models.Submission,review_id)
        if submission and submission.current_version_id:
            _ensure_submission_access(user, submission)
            review=db.scalar(select(models.ReviewRun).where(models.ReviewRun.content_version_id==submission.current_version_id).order_by(models.ReviewRun.created_at.desc()))
    if not review: raise HTTPException(404,detail={"code":"NOT_FOUND","message":"Review not found."})
    submission=db.get(models.Submission,review.submission_id)
    if not submission:
        raise HTTPException(404,detail={"code":"NOT_FOUND","message":"Review not found."})
    _ensure_submission_access(user, submission)
    version=db.get(models.ContentVersion,review.content_version_id)
    return serialize_review(db,submission,version,review)


@router.post("/reviews/{review_id}/findings/{finding_id}/resolve")
def resolve_finding(review_id: str, finding_id: str, reason: str = Form(...), user=Depends(require_roles(Role.REVIEWER,Role.BRAND_OWNER,Role.ADMINISTRATOR)), db: DbSession=None):
    if len(reason.strip()) < 4:
        raise HTTPException(422, detail={"code":"RESOLUTION_REASON_REQUIRED", "message":"Provide a short resolution note."})
    review=db.get(models.ReviewRun,review_id)
    finding=db.get(models.Finding,finding_id)
    if not review or not finding or finding.review_id != review.id:
        raise HTTPException(404, detail={"code":"NOT_FOUND", "message":"Finding not found."})
    submission=db.get(models.Submission,review.submission_id)
    _ensure_submission_access(user, submission)
    from datetime import datetime
    finding.status="RESOLVED"
    finding.resolution_note=reason.strip()
    finding.resolved_by=user.id
    finding.resolved_at=datetime.now(timezone.utc)
    audit(db,user.tenant_id,user.id,"FINDING_RESOLVED","finding",finding.id,{"review_id":review.id,"reason":finding.resolution_note}, brand_id=user.brand_id)
    db.commit()
    return {"id":finding.id,"status":finding.status,"resolution_note":finding.resolution_note}

@router.post("/reviews/{review_id}/decisions")
def record_decision(review_id: str, payload: DecisionRequest, user=Depends(require_roles(Role.REVIEWER,Role.BRAND_OWNER,Role.ADMINISTRATOR)), db: DbSession=None):
    action=payload.action.upper()
    if action not in {"APPROVE","REQUEST_CHANGES","REJECT","OVERRIDE"}: raise HTTPException(422,detail={"code":"INVALID_DECISION","message":"Unsupported decision action."})
    if action in {"REJECT","REQUEST_CHANGES","OVERRIDE"} and not (payload.reason or "").strip(): raise HTTPException(422,detail={"code":"REASON_REQUIRED","message":"A reason is required for this decision."})
    review=db.get(models.ReviewRun,review_id)
    if not review: raise HTTPException(404,detail={"code":"NOT_FOUND","message":"Review not found."})
    submission=db.get(models.Submission,review.submission_id)
    if not submission:
        raise HTTPException(404, detail={"code":"NOT_FOUND", "message":"Review not found."})
    _ensure_submission_access(user, submission)
    version=db.get(models.ContentVersion,review.content_version_id)
    if submission.current_version_id != version.id: raise HTTPException(409,detail={"code":"STALE_VERSION","message":"This review does not belong to the current content version. Re-review the latest version."})
    findings=db.scalars(select(models.Finding).where(models.Finding.review_id==review.id)).all()
    blockers=[f for f in findings if f.severity in {"blocking","review_required"} and f.verdict not in {"SUPPORTED","INFORMATIONAL"} and f.status!="RESOLVED"]
    if action=="APPROVE" and blockers: raise HTTPException(409,detail={"code":"OPEN_BLOCKING_FINDINGS","message":"Approval is blocked while blocking findings remain unresolved.","finding_ids":[f.id for f in blockers]})
    if action=="OVERRIDE" and user.role not in {Role.BRAND_OWNER.value,Role.ADMINISTRATOR.value}: raise HTTPException(403,detail={"code":"OVERRIDE_NOT_ALLOWED","message":"Only a brand owner or administrator can override."})
    new=models.Decision(review_id=review.id,submission_id=submission.id,content_hash=version.sha256,action=action,reason=payload.reason,reviewer_id=user.id)
    db.add(new)
    submission.status={"APPROVE":"APPROVED","REQUEST_CHANGES":"CHANGES_REQUESTED","REJECT":"REJECTED","OVERRIDE":"APPROVED"}[action]
    audit(db,user.tenant_id,user.id,"REVIEW_DECISION_RECORDED","review",review.id,{"action":action,"content_hash":version.sha256,"reason":payload.reason}, brand_id=user.brand_id)
    db.commit()
    return {"decision_id":new.id,"action":action,"submission_status":submission.status,"content_hash":version.sha256,"review_id":review.id}

@router.post("/reviews/{review_id}/patches")
def propose_patch(review_id: str, payload: PatchRequest, user: CurrentUser, db: DbSession):
    review=db.get(models.ReviewRun,review_id)
    if not review: raise HTTPException(404,detail={"code":"NOT_FOUND","message":"Review not found."})
    submission=db.get(models.Submission,review.submission_id)
    if not submission:
        raise HTTPException(404, detail={"code":"NOT_FOUND", "message":"Review not found."})
    _ensure_submission_access(user, submission)
    version=db.get(models.ContentVersion,review.content_version_id)
    finding=db.get(models.Finding,payload.finding_id)
    if not finding or finding.review_id!=review.id or finding.content_start is None or finding.content_end is None: raise HTTPException(422,detail={"code":"PATCH_NOT_LOCAL","message":"This finding does not have a safe text span for local patching."})
    if version.sha256!=review.content_hash: raise HTTPException(409,detail={"code":"STALE_VERSION","message":"Patch base hash is stale."})
    patch=models.Patch(review_id=review.id,finding_id=finding.id,base_content_hash=version.sha256,start_offset=finding.content_start,end_offset=finding.content_end,replacement=payload.replacement,rationale=payload.rationale,status="PROPOSED",created_by=user.id)
    db.add(patch); db.flush(); audit(db,user.tenant_id,user.id,"PATCH_PROPOSED","patch",patch.id,{"finding_id":finding.id,"base_hash":version.sha256}, brand_id=user.brand_id)
    db.commit()
    return {"id":patch.id,"status":patch.status,"base_content_hash":patch.base_content_hash,"original":version.extracted_text[patch.start_offset:patch.end_offset],"replacement":patch.replacement,"rationale":patch.rationale}

@router.post("/patches/{patch_id}/accept")
def accept_patch(patch_id: str, user: CurrentUser, db: DbSession):
    patch=db.get(models.Patch,patch_id)
    if not patch: raise HTTPException(404,detail={"code":"NOT_FOUND","message":"Patch not found."})
    review=db.get(models.ReviewRun,patch.review_id)
    if not review:
        raise HTTPException(404,detail={"code":"NOT_FOUND","message":"Patch not found."})
    submission=db.get(models.Submission,review.submission_id)
    if not submission:
        raise HTTPException(404,detail={"code":"NOT_FOUND","message":"Patch not found."})
    _ensure_submission_access(user, submission)
    version=db.get(models.ContentVersion,review.content_version_id)
    if version.sha256!=patch.base_content_hash or submission.current_version_id!=version.id: raise HTTPException(409,detail={"code":"STALE_VERSION","message":"The source changed after this patch was proposed. Create a new patch against the latest review."})
    if Path(version.filename).suffix.lower()!=".txt": raise HTTPException(422,detail={"code":"FORMAT_REQUIRES_EXTERNAL_EDIT","message":"This patch is a text replacement instruction. Edit the source document in its native editor and upload it as a new version; Sigillum will not claim to edit a flattened PDF or image."})
    text=version.extracted_text
    if text[patch.start_offset:patch.end_offset] != db.get(models.Finding,patch.finding_id).content_quote:
        raise HTTPException(409,detail={"code":"PATCH_SPAN_MISMATCH","message":"The patch span no longer matches the finding quote."})
    revised=text[:patch.start_offset]+patch.replacement+text[patch.end_offset:]
    data=revised.encode("utf-8")
    service=ReviewService(db,_active_pack(user),get_storage(settings))
    try:
        new_version=service.create_version(submission,version.filename,version.mime_type,data,user)
        new_review, findings=service.run_review(submission,new_version)
    except StorageUnavailable as exc:
        db.rollback()
        raise HTTPException(503, detail={"code": "STORAGE_UNAVAILABLE", "message": "Secure content storage is temporarily unavailable."}) from exc
    patch.status="ACCEPTED"
    audit(db,user.tenant_id,user.id,"PATCH_ACCEPTED_NEW_VERSION_CREATED","content_version",new_version.id,{"previous_version_id":version.id,"patch_id":patch.id,"sha256":new_version.sha256,"review_id":new_review.id}, brand_id=user.brand_id)
    db.commit()
    return serialize_review(db,submission,new_version,new_review)

@router.post("/submissions/{submission_id}/revisions/upload")
async def upload_revision(
    submission_id: str,
    user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
    change_summary: str = Form(""),
):
    """Upload a new immutable source file version and create a fresh review context."""
    submission = db.get(models.Submission, submission_id)
    if not submission:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Submission not found."})
    _ensure_submission_access(user, submission)
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, detail={"code": "UPLOAD_TOO_LARGE", "message": "Revision exceeds the configured upload limit."})
    try:
        mime = sniff_file(file.filename or "revision.txt", data)
    except ValueError as exc:
        raise HTTPException(415, detail={"code": "INVALID_UPLOAD", "message": str(exc)}) from exc
    previous = db.get(models.ContentVersion, submission.current_version_id) if submission.current_version_id else None
    service = ReviewService(db, _active_pack(user), get_storage(settings))
    try:
        version = service.create_version(submission, file.filename or "revision.txt", mime, data, user)
        review, findings = service.run_review(submission, version)
    except StorageUnavailable as exc:
        db.rollback()
        raise HTTPException(
            503,
            detail={"code": "STORAGE_UNAVAILABLE", "message": "Secure content storage is temporarily unavailable. The prior version remains preserved."},
        ) from exc
    except Exception as exc:
        submission.status = "PARSE_FAILED"
        audit(db, user.tenant_id, user.id, "REVISION_PARSE_FAILED", "submission", submission.id, {"error_type": type(exc).__name__}, brand_id=user.brand_id)
        db.commit()
        raise HTTPException(422, detail={"code": "PARSE_FAILED", "message": "The revised file could not be safely parsed. The prior version remains preserved."}) from exc
    audit(
        db,
        user.tenant_id,
        user.id,
        "REVISION_UPLOADED_NEW_VERSION_CREATED",
        "content_version",
        version.id,
        {
            "previous_version_id": previous.id if previous else None,
            "change_summary": change_summary[:500],
            "sha256": version.sha256,
            "review_id": review.id,
            "finding_count": len(findings),
        },
        brand_id=user.brand_id,
    )
    db.commit()
    return serialize_review(db, submission, version, review)


@router.post("/submissions/{submission_id}/revisions")
def create_revision(submission_id: str, payload: RevisionRequest, user: CurrentUser, db: DbSession):
    submission=db.get(models.Submission,submission_id)
    if not submission:
        raise HTTPException(404, detail={"code":"NOT_FOUND", "message":"Submission not found."})
    _ensure_submission_access(user, submission)
    prior=db.get(models.ContentVersion,submission.current_version_id)
    data=payload.content.encode("utf-8")
    from sigillum.modules.content.extraction import extract, sniff_file
    mime=sniff_file("revision.txt",data)
    service=ReviewService(db,_active_pack(user),get_storage(settings))
    try:
        version=service.create_version(submission,"revision.txt",mime,data,user)
        review, findings=service.run_review(submission,version)
    except StorageUnavailable as exc:
        db.rollback()
        raise HTTPException(503, detail={"code": "STORAGE_UNAVAILABLE", "message": "Secure content storage is temporarily unavailable."}) from exc
    audit(db,user.tenant_id,user.id,"CONTENT_REVISION_CREATED","content_version",version.id,{"previous_version_id":prior.id if prior else None,"change_summary":payload.change_summary,"sha256":version.sha256,"review_id":review.id}, brand_id=user.brand_id)
    db.commit()
    return serialize_review(db,submission,version,review)

@router.get("/audit")
def audit_log(user: CurrentUser, db: DbSession):
    audit_query = select(models.AuditEvent).where(models.AuditEvent.tenant_id == user.tenant_id, models.AuditEvent.brand_id == user.brand_id)
    if user.role in {Role.CREATOR.value, Role.AGENCY.value}:
        audit_query = audit_query.where(models.AuditEvent.actor_id == user.id)
    rows=db.scalars(audit_query.order_by(models.AuditEvent.created_at.desc()).limit(100)).all()
    return [{"id":r.id,"event_type":r.event_type,"entity_type":r.entity_type,"entity_id":r.entity_id,"actor_id":r.actor_id,"details":r.details,"created_at":r.created_at} for r in rows]

def serialize_review(db,submission,version,review):
    if not review: return {"id":submission.id,"title":submission.title,"status":submission.status}
    findings=db.scalars(select(models.Finding).where(models.Finding.review_id==review.id).order_by(models.Finding.created_at)).all()
    decisions=db.scalars(select(models.Decision).where(models.Decision.review_id==review.id).order_by(models.Decision.created_at.desc())).all()
    return {"submission":{"id":submission.id,"title":submission.title,"status":submission.status,"channel":submission.channel,"locale":submission.locale,"geography":submission.geography,"audience":submission.audience,"offer_id":submission.offer_id,"intended_use":submission.intended_use,"publication_at":submission.publication_at},"content_version":{"id":version.id,"version_number":version.version_number,"filename":version.filename,"mime_type":version.mime_type,"sha256":version.sha256,"size_bytes":version.size_bytes,"text":version.extracted_text,"extraction_confidence":version.extraction_confidence,"extraction_status":version.extraction_status,"warnings":version.extraction_warnings,"regions":version.regions},"review":{"id":review.id,"status":review.status,"content_hash":review.content_hash,"brand_pack_version":review.brand_pack_version,"knowledge_pack_hash":review.knowledge_pack_hash,"analysis_config_version":review.analysis_config_version,"created_at":review.created_at},"findings":[{"id":f.id,"code":f.code,"category":f.category,"severity":f.severity,"verdict":f.verdict,"title":f.title,"explanation":f.explanation,"reason_code":f.reason_code,"evidence_sufficiency":f.evidence_sufficiency,"confidence":f.confidence,"extraction_confidence":f.extraction_confidence,"content_start":f.content_start,"content_end":f.content_end,"content_quote":f.content_quote,"region":f.region,"evidence":f.evidence,"status":f.status,"resolution_note":f.resolution_note,"suggestions":f.suggestions} for f in findings],"decisions":[{"id":d.id,"action":d.action,"reason":d.reason,"content_hash":d.content_hash,"reviewer_id":d.reviewer_id,"created_at":d.created_at} for d in decisions]}
