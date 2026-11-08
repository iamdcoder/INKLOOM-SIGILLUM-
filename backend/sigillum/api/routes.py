from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from sigillum.config import get_settings
from sigillum.api.dependencies import CurrentUser, DbSession, require_roles
from sigillum.infrastructure.database.session import get_db
from sigillum.api.schemas import LoginRequest, TokenResponse, DecisionRequest, PatchRequest, RevisionRequest, KnowledgePackSectionUpdate
from sigillum.domain.enums import Role
from sigillum.infrastructure.database import models
from sigillum.infrastructure.security import verify_password, create_access_token
from sigillum.modules.content.extraction import sniff_file
from sigillum.modules.knowledge.brand_pack import BrandPack
from sigillum.modules.knowledge.store import KnowledgePackStore
from sigillum.application.services.review_service import ReviewService, audit

router=APIRouter()
settings=get_settings()
pack_store=KnowledgePackStore(settings.brand_pack_path, settings.storage_root.parent / "brand_packs")

def _active_pack(user: models.User) -> BrandPack:
    try:
        return pack_store.active_pack(user.tenant_id)
    except (ValueError, OSError, RuntimeError, KeyError) as exc:
        raise HTTPException(503, detail={"code": "BRAND_PACK_UNAVAILABLE", "message": "The active Brand Knowledge Pack could not be loaded."}) from exc

def _ensure_submission_access(user: models.User, submission: models.Submission) -> None:
    """Tenant boundary plus creator ownership; reviewer roles can inspect assigned workspace data."""
    if submission.tenant_id != user.tenant_id:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Resource not found."})
    if user.role == Role.CREATOR.value and submission.created_by != user.id:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Resource not found."})

@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: DbSession):
    user=db.scalar(select(models.User).where(models.User.email==payload.email.lower().strip()))
    if not user or not user.is_active or not verify_password(payload.password,user.password_hash):
        raise HTTPException(401,detail={"code":"INVALID_CREDENTIALS","message":"Email or password is incorrect."})
    return {"access_token":create_access_token(user.id,user.role,user.tenant_id),"user":user}

@router.get("/auth/me")
def me(user: CurrentUser):
    return {"id":user.id,"email":user.email,"display_name":user.display_name,"role":user.role}

@router.get("/brands/current")
def current_brand(user: CurrentUser):
    active_pack = _active_pack(user)
    metadata = pack_store.active_metadata(user.tenant_id)
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
    metadata = pack_store.active_metadata(user.tenant_id)
    return {
        "brand": active_pack.brand,
        "snapshot": active_pack.snapshot(),
        "active_version": metadata,
        "versions": pack_store.list_versions(user.tenant_id),
        "can_edit": user.role == Role.BRAND_OWNER.value,
    }


@router.get("/brands/current/versions")
def brand_versions(user=Depends(require_roles(Role.BRAND_OWNER, Role.REVIEWER, Role.ADMINISTRATOR))):
    return {"versions": pack_store.list_versions(user.tenant_id)}


@router.post("/brands/current/drafts")
def create_brand_draft(user=Depends(require_roles(Role.BRAND_OWNER)), db: Session = Depends(get_db)):
    draft = pack_store.create_draft(user.tenant_id, user.id)
    audit(db, user.tenant_id, user.id, "BRAND_KNOWLEDGE_DRAFT_CREATED", "brand_knowledge_draft", draft["draft_id"], {"base_version_id": draft["base_version_id"]})
    db.commit()
    return {"draft_id": draft["draft_id"], "base_version_id": draft["base_version_id"], "status": draft["status"], "snapshot": draft["snapshot"]}


@router.get("/brands/current/drafts/{draft_id}")
def get_brand_draft(draft_id: str, user=Depends(require_roles(Role.BRAND_OWNER))):
    try:
        draft = pack_store.get_draft(user.tenant_id, draft_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, detail={"code": "DRAFT_NOT_FOUND", "message": "Knowledge Pack draft not found."})
    return draft


@router.put("/brands/current/drafts/{draft_id}/section")
def update_brand_draft_section(draft_id: str, payload: KnowledgePackSectionUpdate, user=Depends(require_roles(Role.BRAND_OWNER)), db: Session = Depends(get_db)):
    try:
        draft = pack_store.update_section(user.tenant_id, draft_id, payload.section, payload.content, user.id)
    except FileNotFoundError:
        raise HTTPException(404, detail={"code": "DRAFT_NOT_FOUND", "message": "Knowledge Pack draft not found."})
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "INVALID_DRAFT_UPDATE", "message": str(exc)}) from exc
    audit(db, user.tenant_id, user.id, "BRAND_KNOWLEDGE_DRAFT_SECTION_UPDATED", "brand_knowledge_draft", draft_id, {"section": payload.section})
    db.commit()
    return {"draft_id": draft["draft_id"], "status": draft["status"], "updated_at": draft["updated_at"], "section": payload.section}


@router.post("/brands/current/drafts/{draft_id}/validate")
def validate_brand_draft(draft_id: str, user=Depends(require_roles(Role.BRAND_OWNER)), db: Session = Depends(get_db)):
    try:
        result = pack_store.validate_draft(user.tenant_id, draft_id)
    except FileNotFoundError:
        raise HTTPException(404, detail={"code": "DRAFT_NOT_FOUND", "message": "Knowledge Pack draft not found."})
    audit(db, user.tenant_id, user.id, "BRAND_KNOWLEDGE_DRAFT_VALIDATED", "brand_knowledge_draft", draft_id, {"valid": result["valid"], "error_count": len(result["errors"])})
    db.commit()
    return result


@router.post("/brands/current/drafts/{draft_id}/publish")
def publish_brand_draft(draft_id: str, user=Depends(require_roles(Role.BRAND_OWNER)), db: Session = Depends(get_db)):
    try:
        metadata = pack_store.publish_draft(user.tenant_id, draft_id, user.id)
    except FileNotFoundError:
        raise HTTPException(404, detail={"code": "DRAFT_NOT_FOUND", "message": "Knowledge Pack draft not found."})
    except RuntimeError as exc:
        raise HTTPException(409, detail={"code": "STALE_KNOWLEDGE_DRAFT", "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "KNOWLEDGE_PACK_NOT_PUBLISHABLE", "message": str(exc)}) from exc
    audit(db, user.tenant_id, user.id, "BRAND_KNOWLEDGE_PACK_PUBLISHED", "brand_knowledge_pack", metadata["version_id"], metadata)
    db.commit()
    return metadata

@router.get("/dashboard/summary")
def dashboard(user: CurrentUser, db: DbSession):
    tenant=user.tenant_id
    scope = [models.Submission.tenant_id == tenant]
    if user.role == Role.CREATOR.value:
        scope.append(models.Submission.created_by == user.id)
    total=db.scalar(select(func.count()).select_from(models.Submission).where(*scope)) or 0
    open_reviews=db.scalar(select(func.count()).select_from(models.Submission).where(*scope,models.Submission.status=="NEEDS_REVIEW")) or 0
    approved=db.scalar(select(func.count()).select_from(models.Submission).where(*scope,models.Submission.status=="APPROVED")) or 0
    findings=db.scalar(select(func.count()).select_from(models.Finding).join(models.ReviewRun).join(models.Submission).where(*scope)) or 0
    active_pack = _active_pack(user)
    return {"submissions":total,"needs_review":open_reviews,"approved":approved,"findings":findings,"brand_name":active_pack.brand["brand_name"]}

@router.get("/submissions")
def list_submissions(user: CurrentUser, db: DbSession):
    query = select(models.Submission).where(models.Submission.tenant_id == user.tenant_id)
    if user.role == Role.CREATOR.value:
        query = query.where(models.Submission.created_by == user.id)
    rows=db.scalars(query.order_by(models.Submission.created_at.desc()).limit(100)).all()
    result=[]
    for row in rows:
        version=db.get(models.ContentVersion,row.current_version_id) if row.current_version_id else None
        result.append({"id":row.id,"title":row.title,"status":row.status,"channel":row.channel,"publication_at":row.publication_at,"created_at":row.created_at,"filename":version.filename if version else None,"version":version.version_number if version else None})
    return result

@router.post("/submissions")
async def create_submission(user: CurrentUser, db: DbSession, file: UploadFile=File(...), title: str=Form("Untitled submission"), channel: str=Form("direct_web"), locale: str=Form("en-IN"), geography: str=Form("IN"), audience: str=Form("consumer"), offer_id: str=Form("OFFER-ORBITA-OCT-NOV-2026"), publication_at: str=Form(...)):
    active_pack = _active_pack(user)
    if channel not in active_pack.brand.get("channels",[]): raise HTTPException(422,detail={"code":"INVALID_CHANNEL","message":"Channel is not supported by the current Brand Knowledge Pack."})
    if locale not in active_pack.brand.get("supported_locales",[]): raise HTTPException(422,detail={"code":"INVALID_LOCALE","message":"Locale is not supported by this demo pack."})
    data=await file.read(settings.max_upload_bytes+1)
    if len(data)>settings.max_upload_bytes: raise HTTPException(413,detail={"code":"UPLOAD_TOO_LARGE","message":f"Maximum file size is {settings.max_upload_bytes//1024//1024} MB."})
    try: mime=sniff_file(file.filename or "upload.txt",data)
    except ValueError as exc: raise HTTPException(415,detail={"code":"INVALID_UPLOAD","message":str(exc)}) from exc
    try: when=datetime.fromisoformat(publication_at.replace("Z","+00:00"))
    except ValueError: raise HTTPException(422,detail={"code":"INVALID_PUBLICATION_DATE","message":"Use an ISO-8601 date/time with timezone."})
    if when.tzinfo is None: raise HTTPException(422,detail={"code":"TIMEZONE_REQUIRED","message":"Publication time must include a timezone."})
    submission=models.Submission(tenant_id=user.tenant_id,brand_id=active_pack.brand["brand_id"],title=title.strip()[:240] or "Untitled submission",channel=channel,locale=locale,geography=geography,audience=audience,offer_id=offer_id or None,publication_at=when.isoformat(),created_by=user.id)
    db.add(submission); db.flush()
    service=ReviewService(db,active_pack,settings.storage_root)
    try:
        version=service.create_version(submission,file.filename or "upload.txt",mime,data,user)
        review, findings=service.run_review(submission,version)
    except Exception as exc:
        submission.status="PARSE_FAILED"
        audit(db,user.tenant_id,user.id,"SUBMISSION_PARSE_FAILED","submission",submission.id,{"error_type":type(exc).__name__})
        db.commit()
        raise HTTPException(422,detail={"code":"PARSE_FAILED","message":"The file could not be safely parsed. The failure was recorded and was not treated as approval."}) from exc
    audit(db,user.tenant_id,user.id,"SUBMISSION_CREATED","submission",submission.id,{"content_version_id":version.id,"sha256":version.sha256,"review_id":review.id,"finding_count":len(findings)})
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

@router.get("/content-versions/{version_id}/download")
def download_version(version_id: str, user: CurrentUser, db: DbSession):
    version=db.get(models.ContentVersion,version_id)
    if not version:
        raise HTTPException(404,detail={"code":"NOT_FOUND","message":"Content version not found."})
    submission=db.get(models.Submission,version.submission_id)
    if not submission:
        raise HTTPException(404,detail={"code":"NOT_FOUND","message":"Content version not found."})
    _ensure_submission_access(user, submission)
    target=settings.storage_root/version.storage_key
    if not target.exists():
        raise HTTPException(404,detail={"code":"ARTEFACT_UNAVAILABLE","message":"The original artefact is not available in local storage."})
    from fastapi.responses import FileResponse
    return FileResponse(target,media_type=version.mime_type,filename=version.filename,content_disposition_type="attachment")

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
    audit(db,user.tenant_id,user.id,"FINDING_RESOLVED","finding",finding.id,{"review_id":review.id,"reason":finding.resolution_note})
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
    audit(db,user.tenant_id,user.id,"REVIEW_DECISION_RECORDED","review",review.id,{"action":action,"content_hash":version.sha256,"reason":payload.reason})
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
    db.add(patch); db.flush(); audit(db,user.tenant_id,user.id,"PATCH_PROPOSED","patch",patch.id,{"finding_id":finding.id,"base_hash":version.sha256})
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
    service=ReviewService(db,_active_pack(user),settings.storage_root)
    new_version=service.create_version(submission,version.filename,version.mime_type,data,user)
    new_review, findings=service.run_review(submission,new_version)
    patch.status="ACCEPTED"
    audit(db,user.tenant_id,user.id,"PATCH_ACCEPTED_NEW_VERSION_CREATED","content_version",new_version.id,{"previous_version_id":version.id,"patch_id":patch.id,"sha256":new_version.sha256,"review_id":new_review.id})
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
    service = ReviewService(db, _active_pack(user), settings.storage_root)
    try:
        version = service.create_version(submission, file.filename or "revision.txt", mime, data, user)
        review, findings = service.run_review(submission, version)
    except Exception as exc:
        submission.status = "PARSE_FAILED"
        audit(db, user.tenant_id, user.id, "REVISION_PARSE_FAILED", "submission", submission.id, {"error_type": type(exc).__name__})
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
    from sigillum.modules.content.extraction import sniff_file
    mime=sniff_file("revision.txt",data)
    service=ReviewService(db,_active_pack(user),settings.storage_root)
    version=service.create_version(submission,"revision.txt",mime,data,user)
    review, findings=service.run_review(submission,version)
    audit(db,user.tenant_id,user.id,"CONTENT_REVISION_CREATED","content_version",version.id,{"previous_version_id":prior.id if prior else None,"change_summary":payload.change_summary,"sha256":version.sha256,"review_id":review.id})
    db.commit()
    return serialize_review(db,submission,version,review)

@router.get("/audit")
def audit_log(user: CurrentUser, db: DbSession):
    audit_query = select(models.AuditEvent).where(models.AuditEvent.tenant_id == user.tenant_id)
    if user.role == Role.CREATOR.value:
        audit_query = audit_query.where(models.AuditEvent.actor_id == user.id)
    rows=db.scalars(audit_query.order_by(models.AuditEvent.created_at.desc()).limit(100)).all()
    return [{"id":r.id,"event_type":r.event_type,"entity_type":r.entity_type,"entity_id":r.entity_id,"actor_id":r.actor_id,"details":r.details,"created_at":r.created_at} for r in rows]

def serialize_review(db,submission,version,review):
    if not review: return {"id":submission.id,"title":submission.title,"status":submission.status}
    findings=db.scalars(select(models.Finding).where(models.Finding.review_id==review.id).order_by(models.Finding.created_at)).all()
    decisions=db.scalars(select(models.Decision).where(models.Decision.review_id==review.id).order_by(models.Decision.created_at.desc())).all()
    return {"submission":{"id":submission.id,"title":submission.title,"status":submission.status,"channel":submission.channel,"locale":submission.locale,"geography":submission.geography,"audience":submission.audience,"offer_id":submission.offer_id,"publication_at":submission.publication_at},"content_version":{"id":version.id,"version_number":version.version_number,"filename":version.filename,"mime_type":version.mime_type,"sha256":version.sha256,"size_bytes":version.size_bytes,"text":version.extracted_text,"extraction_confidence":version.extraction_confidence,"extraction_status":version.extraction_status,"warnings":version.extraction_warnings,"regions":version.regions},"review":{"id":review.id,"status":review.status,"content_hash":review.content_hash,"brand_pack_version":review.brand_pack_version,"knowledge_pack_hash":review.knowledge_pack_hash,"analysis_config_version":review.analysis_config_version,"created_at":review.created_at},"findings":[{"id":f.id,"code":f.code,"category":f.category,"severity":f.severity,"verdict":f.verdict,"title":f.title,"explanation":f.explanation,"reason_code":f.reason_code,"evidence_sufficiency":f.evidence_sufficiency,"confidence":f.confidence,"extraction_confidence":f.extraction_confidence,"content_start":f.content_start,"content_end":f.content_end,"content_quote":f.content_quote,"region":f.region,"evidence":f.evidence,"status":f.status,"resolution_note":f.resolution_note,"suggestions":f.suggestions} for f in findings],"decisions":[{"id":d.id,"action":d.action,"reason":d.reason,"content_hash":d.content_hash,"reviewer_id":d.reviewer_id,"created_at":d.created_at} for d in decisions]}
