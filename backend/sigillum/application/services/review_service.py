from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
from sqlalchemy.orm import Session
from sigillum.infrastructure.database import models
from sigillum.infrastructure.storage import LocalFilesystemStorage, ObjectStorage
from sigillum.modules.content.extraction import extract
from sigillum.modules.knowledge.brand_pack import BrandPack
from sigillum.modules.verification.engine import VerificationEngine

class ReviewService:
    def __init__(
        self,
        db: Session,
        pack: BrandPack,
        storage: ObjectStorage | Path | str | None = None,
        *,
        storage_root: Path | str | None = None,
    ):
        selected_storage = storage if storage is not None else storage_root
        if selected_storage is None:
            raise ValueError("ReviewService requires an object-storage adapter or storage root.")
        self.db = db
        self.pack = pack
        self.storage = (
            selected_storage
            if hasattr(selected_storage, "put_bytes")
            else LocalFilesystemStorage(selected_storage)
        )
        self.engine = VerificationEngine(pack)

    def _contrast_threshold(self, submission: models.Submission) -> float | None:
        """Resolve only an approved, in-scope threshold from the current demo pack."""
        for policy in self.pack.policies:
            if policy.get("policy_id") != "POL-VIS-001" or policy.get("status") != "approved":
                continue
            scope = policy.get("scope") or {}
            allowed_channels = scope.get("channel")
            if allowed_channels and submission.channel not in allowed_channels:
                continue
            value = policy.get("minimum_contrast_ratio")
            if isinstance(value, (int, float)) and value > 1:
                return float(value)
        return None

    def create_version(self, submission: models.Submission, filename: str, mime_type: str, data: bytes, actor: models.User):
        result=extract(filename, data, contrast_threshold=self._contrast_threshold(submission))
        digest=sha256(data).hexdigest()
        version_number=len(submission.versions)+1
        storage_key=f"{submission.id}/{version_number}/{uuid4().hex}{Path(filename).suffix.lower()}"
        self.storage.put_bytes(storage_key, data, content_type=mime_type)
        version=models.ContentVersion(submission_id=submission.id,version_number=version_number,filename=Path(filename).name,mime_type=mime_type,storage_key=storage_key,sha256=digest,size_bytes=len(data),extracted_text=result.text,extraction_confidence=result.confidence,extraction_status=result.status,extraction_warnings=result.warnings,regions=result.regions,created_by=actor.id)
        self.db.add(version); self.db.flush()
        submission.current_version_id=version.id
        return version

    def _contrast_findings(self, version: models.ContentVersion) -> list[dict]:
        findings: list[dict] = []
        for region in version.regions or []:
            if region.get("kind") != "ocr_line":
                continue
            contrast = region.get("contrast") or {}
            status = contrast.get("status")
            # No applicable approved threshold means the system has no policy basis
            # for raising a contrast issue. Keep the UNMEASURABLE metadata visible.
            if status not in {"FAIL", "UNMEASURABLE"} or contrast.get("reason") == "NO_APPROVED_THRESHOLD":
                continue

            ratio = contrast.get("ratio")
            threshold = contrast.get("threshold")
            failed = status == "FAIL"
            if failed:
                title = "Text may fall below the approved contrast threshold"
                explanation = (
                    f"A local pixel estimate measured {ratio}:1 against the approved {threshold}:1 threshold "
                    "for this OCR line. This is a candidate measurement, not a full accessibility certification; "
                    "inspect the original creative before deciding."
                )
                reason_code = "LOCAL_CONTRAST_BELOW_APPROVED_THRESHOLD"
            else:
                title = "Text contrast could not be measured reliably"
                explanation = (
                    "The local foreground/background segmentation was not reliable enough to report a contrast "
                    "ratio. This is not a pass. Inspect the original creative manually."
                )
                reason_code = str(contrast.get("reason") or "CONTRAST_UNMEASURABLE")

            evidence = [{
                "policy_id": "POL-VIS-001",
                "policy_source": "Approved Brand Knowledge Pack contrast policy",
                "threshold": threshold,
                "measured_ratio": ratio,
                "foreground_color": contrast.get("foreground_color"),
                "background_color": contrast.get("background_color"),
                "measurement_method": contrast.get("method"),
                "measurement_confidence": contrast.get("measurement_confidence"),
                "limitation": contrast.get("limitation") or "No reliable local measurement was available.",
            }]
            findings.append({
                "code": "VISUAL_CONTRAST_REVIEW",
                "category": "accessibility",
                "severity": "review_required",
                "verdict": "NEEDS_MANUAL_REVIEW",
                "title": title,
                "explanation": explanation,
                "reason_code": reason_code,
                "evidence_sufficiency": "INSUFFICIENT",
                "confidence": float(contrast.get("measurement_confidence") or 0.0),
                "extraction_confidence": float(region.get("confidence") or version.extraction_confidence),
                "content_start": region.get("start"),
                "content_end": region.get("end"),
                "content_quote": region.get("text"),
                "region": region,
                "evidence": evidence,
                "suggestions": [],
            })
        return findings

    def _exact_asset_usage_findings(self, submission: models.Submission, version: models.ContentVersion) -> list[dict]:
        """Apply asset usage rules only when uploaded bytes exactly match an approved asset."""
        if not str(version.mime_type or "").startswith("image/"):
            return []
        manifest = self.pack.assets if isinstance(self.pack.assets, dict) else {}
        records = manifest.get("approved_assets", [])
        policies = manifest.get("usage_policies", {})
        if not isinstance(records, list) or not isinstance(policies, dict):
            return []
        matches = [
            asset for asset in records
            if isinstance(asset, dict)
            and asset.get("status") == "approved"
            and str(asset.get("sha256", "")).lower() == str(version.sha256 or "").lower()
        ]
        findings: list[dict] = []
        publication_at = datetime.fromisoformat(submission.publication_at.replace("Z", "+00:00"))
        from sigillum.modules.knowledge.asset_policy import asset_policy_violations

        for asset in matches:
            policy = policies.get(asset.get("kind"))
            if not isinstance(policy, dict):
                continue
            violations = asset_policy_violations(
                asset,
                policy,
                submission.channel,
                getattr(submission, "intended_use", "general") or "general",
                publication_at,
            )
            for violation in violations:
                code = violation["code"]
                stale = "VALIDITY" in code or code == "ASSET_OUTSIDE_VALIDITY"
                findings.append({
                    "code": f"BRAND_ASSET_{code}",
                    "category": "assets",
                    "severity": policy.get("severity", "review_required"),
                    "verdict": "STALE" if stale else "CONTRADICTED",
                    "title": "Approved brand asset is outside its permitted use",
                    "explanation": violation["message"] + " The exact uploaded file hash matches the approved asset record; the restriction is deterministic for this declared channel, use and publication time.",
                    "reason_code": code,
                    "evidence_sufficiency": "SUFFICIENT",
                    "confidence": 1.0,
                    "extraction_confidence": float(version.extraction_confidence or 0.0),
                    "content_start": None,
                    "content_end": None,
                    "content_quote": None,
                    "region": None,
                    "evidence": [{
                        "asset_id": asset.get("asset_id"),
                        "asset_name": asset.get("name"),
                        "asset_kind": asset.get("kind"),
                        "asset_sha256": asset.get("sha256"),
                        "policy": policy,
                        "channel": submission.channel,
                        "intended_use": getattr(submission, "intended_use", "general"),
                        "publication_at": submission.publication_at,
                    }],
                    "suggestions": ["Select an asset approved for this channel/use or request a Brand Owner policy update."],
                })
            clear_space_ratio = float(policy.get("clear_space_ratio", 0) or 0)
            if clear_space_ratio > 0:
                findings.append({
                    "code": "BRAND_ASSET_CLEAR_SPACE_MANUAL_REVIEW",
                    "category": "assets",
                    "severity": "review_required",
                    "verdict": "NEEDS_MANUAL_REVIEW",
                    "title": "Brand asset clear space requires visual confirmation",
                    "explanation": f"The Brand Owner requires {clear_space_ratio:.0%} clear space for this asset. Sigillum has matched the exact approved asset file, but cannot certify the surrounding layout or clear-space geometry automatically.",
                    "reason_code": "CLEAR_SPACE_REQUIRES_HUMAN_INSPECTION",
                    "evidence_sufficiency": "INSUFFICIENT",
                    "confidence": 0.0,
                    "extraction_confidence": float(version.extraction_confidence or 0.0),
                    "content_start": None,
                    "content_end": None,
                    "content_quote": None,
                    "region": None,
                    "evidence": [{"asset_id": asset.get("asset_id"), "required_clear_space_ratio": clear_space_ratio}],
                    "suggestions": ["Inspect the original creative and confirm the required clear space around the mark."],
                })
        return findings

    def run_review(self, submission: models.Submission, version: models.ContentVersion):
        review=models.ReviewRun(
            submission_id=submission.id,
            content_version_id=version.id,
            content_hash=version.sha256,
            brand_pack_version=self.pack.version(),
            knowledge_pack_hash=self.pack.fingerprint(),
            knowledge_pack_snapshot=self.pack.snapshot(),
            analysis_config_version="deterministic-temporal-rrf-v2",
            status="COMPLETED",
        )
        self.db.add(review); self.db.flush()
        context={"brand_id": submission.brand_id, "offer_id":submission.offer_id,"geography":submission.geography,"channel":submission.channel,"locale":submission.locale,"audience":submission.audience}
        publication_at = datetime.fromisoformat(submission.publication_at.replace("Z", "+00:00"))
        # ReviewRun.created_at is the recorded/system-time boundary. The exact pack
        # snapshot is persisted above, so later publication cannot rewrite this run.
        knowledge_as_of = review.created_at or datetime.now(timezone.utc)
        findings=self.engine.analyse(version.extracted_text,context,publication_at,version.extraction_confidence,version.regions,knowledge_as_of=knowledge_as_of)
        findings.extend(self._exact_asset_usage_findings(submission, version))
        if version.mime_type in {"image/png", "image/jpeg"}:
            # Logo identity remains human-confirmed. Contrast estimates are candidate
            # measurements and remain review-required rather than automatic approval.
            findings.extend([
                {
                    "code": "VISUAL_ASSET_MANUAL_REVIEW",
                    "category": "assets",
                    "severity": "review_required",
                    "verdict": "NEEDS_MANUAL_REVIEW",
                    "title": "Approved logo identity needs visual confirmation",
                    "explanation": "Sigillum extracted text from this image, but automated logo identity matching is not enabled. Compare the visible mark with the approved Brand Knowledge Pack asset before approval.",
                    "reason_code": "ASSET_IDENTITY_NOT_AUTOMATED",
                    "evidence_sufficiency": "INSUFFICIENT",
                    "confidence": 0.0,
                    "extraction_confidence": version.extraction_confidence,
                    "content_start": None,
                    "content_end": None,
                    "content_quote": None,
                    "region": None,
                    "evidence": [{"asset_id": asset.get("asset_id"), "name": asset.get("name"), "status": asset.get("status")} for asset in self.pack.assets.get("approved_assets", []) if asset.get("kind") == "logo"],
                    "suggestions": [],
                },
                *self._contrast_findings(version),
            ])
        elif version.mime_type in {
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }:
            findings.append(
                {
                    "code": "DOCUMENT_VISUAL_REVIEW",
                    "category": "assets",
                    "severity": "review_required",
                    "verdict": "NEEDS_MANUAL_REVIEW",
                    "title": "Document visual content needs inspection",
                    "explanation": "Sigillum extracts searchable text and document structure, but this build does not fully analyse embedded images, drawing objects or rendered page layout. Inspect the original document for unextracted claims, logo usage and fine-print contrast before approval.",
                    "reason_code": "DOCUMENT_VISUAL_ANALYSIS_NOT_COMPLETE",
                    "evidence_sufficiency": "INSUFFICIENT",
                    "confidence": 0.0,
                    "extraction_confidence": version.extraction_confidence,
                    "content_start": None,
                    "content_end": None,
                    "content_quote": None,
                    "region": None,
                    "evidence": [],
                    "suggestions": [],
                }
            )
        for item in findings:
            self.db.add(models.Finding(review_id=review.id,**item))
        submission.status="NEEDS_REVIEW" if findings else "ANALYSED"
        return review, findings

def audit(
    db: Session,
    tenant_id: str,
    actor_id: str | None,
    event_type: str,
    entity_type: str,
    entity_id: str,
    details: dict | None = None,
    brand_id: str | None = None,
):
    db.add(
        models.AuditEvent(
            tenant_id=tenant_id,
            brand_id=brand_id,
            actor_id=actor_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details or {},
        )
    )
