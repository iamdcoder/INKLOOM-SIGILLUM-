from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sigillum.config import get_settings
from sigillum.infrastructure.database import models
from sigillum.infrastructure.storage import LocalFilesystemStorage, ObjectStorage
from sigillum.modules.content.extraction import extract, perceptual_hash_distance
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

    def _palette_policy(self, submission: models.Submission) -> dict | None:
        """Resolve only an owner-configured palette rule relevant to declared use."""
        kind_by_use = {
            "brand_lockup": "logo",
            "product_detail": "product_image",
            "campaign": "campaign_image",
            "social_ad": "campaign_image",
            "email_banner": "campaign_image",
            "website_hero": "campaign_image",
            "packaging": "product_image",
        }
        kind = kind_by_use.get(str(getattr(submission, "intended_use", "general") or "general"))
        if not kind:
            return None
        assets = self.pack.assets if isinstance(self.pack.assets, dict) else {}
        policies = assets.get("usage_policies", {}) if isinstance(assets, dict) else {}
        policy = policies.get(kind) if isinstance(policies, dict) else None
        if not isinstance(policy, dict) or not policy.get("palette_hex"):
            return None
        allowed_channels = policy.get("allowed_channels") or []
        if allowed_channels and submission.channel not in allowed_channels:
            return None
        return policy

    def create_version(
        self,
        submission: models.Submission,
        filename: str,
        mime_type: str,
        data: bytes,
        actor: models.User,
        *,
        parent_version_id: str | None = None,
        scan_metadata: dict | None = None,
    ):
        result = extract(filename, data, contrast_threshold=self._contrast_threshold(submission), palette_policy=self._palette_policy(submission))
        digest = sha256(data).hexdigest()
        # Serialize version-number allocation on databases that support row locks.
        self.db.execute(
            select(models.Submission.id)
            .where(models.Submission.id == submission.id)
            .with_for_update()
        )
        latest_number = self.db.scalar(
            select(func.max(models.ContentVersion.version_number)).where(
                models.ContentVersion.submission_id == submission.id
            )
        ) or 0
        version_number = int(latest_number) + 1
        suffix = Path(filename).suffix.lower()
        storage_key = (
            f"submissions/{submission.tenant_id}/{submission.brand_id}/"
            f"{submission.id}/{uuid4().hex}{suffix}"
        )
        if hasattr(self.storage, "put_bytes_immutable"):
            self.storage.put_bytes_immutable(storage_key, data, content_type=mime_type)
        else:
            self.storage.put_bytes(storage_key, data, content_type=mime_type)
        scan_metadata = scan_metadata or {}
        safe_filename = Path(filename.replace("\\", "/")).name[:255] or "upload"
        retention_days = get_settings().content_retention_days
        retention_until = (
            datetime.now(timezone.utc) + timedelta(days=retention_days)
            if retention_days > 0
            else None
        )
        retention_policy = f"CONFIGURED_{retention_days}_DAYS" if retention_days > 0 else "MANUAL"
        version = models.ContentVersion(
            submission_id=submission.id,
            version_number=version_number,
            filename=safe_filename,
            mime_type=mime_type,
            storage_key=storage_key,
            sha256=digest,
            size_bytes=len(data),
            parent_version_id=parent_version_id,
            scan_status=str(scan_metadata.get("status") or "CLEAN").upper(),
            scan_engine=scan_metadata.get("engine"),
            scan_scanned_at=scan_metadata.get("scanned_at"),
            scan_signature=scan_metadata.get("signature"),
            retention_policy=retention_policy,
            retention_until=retention_until,
            extracted_text=result.text,
            extraction_confidence=result.confidence,
            extraction_status=result.status,
            extraction_warnings=result.warnings,
            regions=result.regions,
            created_by=actor.id,
        )
        self.db.add(version)
        self.db.flush()
        submission.current_version_id = version.id
        return version

    def _contrast_findings(self, version: models.ContentVersion) -> list[dict]:
        findings: list[dict] = []
        for region in version.regions or []:
            if region.get("kind") not in {"ocr_line", "pdf_ocr_line"}:
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

    def _image_visual_findings(self, submission: models.Submission, version: models.ContentVersion) -> list[dict]:
        """Add conservative palette and perceptual-hash review candidates for raster uploads."""
        if not str(version.mime_type or "").startswith("image/"):
            return []
        metadata = next(
            (item for item in (version.regions or []) if isinstance(item, dict) and item.get("kind") == "image_metadata"),
            None,
        )
        if not metadata:
            return []
        findings: list[dict] = []
        palette = metadata.get("palette_comparison") or {}
        palette_status = str(palette.get("status", "UNMEASURABLE")).upper()
        if palette_status in {"FAIL", "UNMEASURABLE"} and palette.get("reason") != "NO_APPROVED_PALETTE_POLICY":
            reason = str(palette.get("reason") or "PALETTE_UNMEASURABLE")
            findings.append({
                "code": "VISUAL_PALETTE_REVIEW",
                "category": "assets",
                "severity": "review_required",
                "verdict": "NEEDS_MANUAL_REVIEW",
                "title": "Brand palette comparison needs human confirmation" if palette_status == "FAIL" else "Brand palette could not be measured reliably",
                "explanation": (
                    f"The sampled dominant palette matched {float(palette.get('score') or 0):.0%} of the approved tolerance; "
                    f"the configured minimum is {float(palette.get('threshold') or 0):.0%}. This bounded RGB estimate is a review candidate, not brand identity certification."
                    if palette_status == "FAIL" else
                    "An owner-configured palette rule exists for this declared use, but a reliable comparison was not available. Inspect the original creative manually; this is not a pass."
                ),
                "reason_code": "APPROVED_PALETTE_TOLERANCE_NOT_MET" if palette_status == "FAIL" else reason,
                "evidence_sufficiency": "INSUFFICIENT",
                "confidence": 0.0,
                "extraction_confidence": float(version.extraction_confidence or 0.0),
                "content_start": None,
                "content_end": None,
                "content_quote": None,
                "region": metadata,
                "evidence": [{
                    "policy": "Brand Owner approved asset usage palette policy",
                    "score": palette.get("score"),
                    "minimum_match_ratio": palette.get("threshold"),
                    "rgb_tolerance": palette.get("tolerance_rgb_distance"),
                    "allowed_palette": palette.get("allowed_palette"),
                    "limitation": palette.get("limitation") or "No reliable palette comparison was available.",
                }],
                "suggestions": ["Inspect the original creative and confirm whether its colours comply with the approved brand palette."],
            })

        # Perceptual hashes only nominate possible duplicates. They never prove logo
        # identity and are not used to apply deterministic asset-use restrictions.
        observed_hash = str(metadata.get("perceptual_hash") or "")
        asset_manifest = self.pack.assets if isinstance(self.pack.assets, dict) else {}
        approved_assets = asset_manifest.get("approved_assets", []) if isinstance(asset_manifest, dict) else []
        candidates = []
        if observed_hash and isinstance(approved_assets, list):
            for asset in approved_assets:
                if not isinstance(asset, dict) or asset.get("status") != "approved":
                    continue
                if str(asset.get("sha256", "")).lower() == str(version.sha256 or "").lower():
                    continue
                candidate_hash = str(asset.get("perceptual_hash") or "")
                distance = perceptual_hash_distance(observed_hash, candidate_hash)
                if distance is not None and distance <= 8:
                    candidates.append((distance, asset))
        for distance, asset in sorted(candidates, key=lambda item: item[0])[:3]:
            findings.append({
                "code": "VISUAL_ASSET_SIMILARITY_CANDIDATE",
                "category": "assets",
                "severity": "review_required",
                "verdict": "NEEDS_MANUAL_REVIEW",
                "title": "Uploaded creative resembles an approved brand asset",
                "explanation": "A perceptual hash nominated this approved asset as a possible visual match. Resizing, compression and similar layouts can produce false positives; a reviewer must inspect the original and confirm identity.",
                "reason_code": "PERCEPTUAL_HASH_CANDIDATE_ONLY",
                "evidence_sufficiency": "INSUFFICIENT",
                "confidence": 0.0,
                "extraction_confidence": float(version.extraction_confidence or 0.0),
                "content_start": None,
                "content_end": None,
                "content_quote": None,
                "region": metadata,
                "evidence": [{
                    "asset_id": asset.get("asset_id"),
                    "asset_name": asset.get("name"),
                    "asset_sha256": asset.get("sha256"),
                    "hamming_distance": distance,
                    "algorithm": "dhash-64-v1",
                }],
                "suggestions": ["Compare the uploaded creative with the approved asset before confirming its identity or permitted use."],
            })
        return findings

    def create_review_context(self, submission: models.Submission, version: models.ContentVersion):
        """Create the immutable review context before work starts, inside the upload transaction."""
        review = models.ReviewRun(
            submission_id=submission.id,
            content_version_id=version.id,
            content_hash=version.sha256,
            brand_pack_version=self.pack.version(),
            knowledge_pack_hash=self.pack.fingerprint(),
            knowledge_pack_snapshot=self.pack.snapshot(),
            analysis_config_version="deterministic-temporal-rrf-v2",
            status="QUEUED",
        )
        self.db.add(review)
        self.db.flush()
        return review

    def run_review(
        self,
        submission: models.Submission,
        version: models.ContentVersion,
        *,
        review_context: models.ReviewRun | None = None,
    ):
        review = review_context or self.create_review_context(submission, version)
        if review.submission_id != submission.id or review.content_version_id != version.id:
            raise ValueError("Review context does not match the immutable submission version")
        review.status = "RUNNING"
        self.db.flush()
        context={"brand_id": submission.brand_id, "offer_id":submission.offer_id,"geography":submission.geography,"channel":submission.channel,"locale":submission.locale,"audience":submission.audience}
        publication_at = datetime.fromisoformat(submission.publication_at.replace("Z", "+00:00"))
        # ReviewRun.created_at is the recorded/system-time boundary. The exact pack
        # snapshot is persisted above, so later publication cannot rewrite this run.
        knowledge_as_of = review.created_at or datetime.now(timezone.utc)
        findings=self.engine.analyse(version.extracted_text,context,publication_at,version.extraction_confidence,version.regions,knowledge_as_of=knowledge_as_of)
        findings.extend(self._exact_asset_usage_findings(submission, version))
        findings.extend(self._image_visual_findings(submission, version))
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
            if version.mime_type == "application/pdf":
                findings.extend(self._contrast_findings(version))
                visual_limitations = (
                    "Searchable page text and scanned-page OCR are mapped to rendered page regions. "
                    "Independently placed images/logos, complex figure semantics and full-document accessibility still require human inspection."
                )
            else:
                visual_limitations = (
                    "Paragraphs, runs, table cells and header/footer text are mapped to logical offsets. "
                    "Rendered page geometry and OCR of embedded images/drawing objects are not available in this build; inspect them manually."
                )
            findings.append(
                {
                    "code": "DOCUMENT_VISUAL_REVIEW",
                    "category": "assets",
                    "severity": "review_required",
                    "verdict": "NEEDS_MANUAL_REVIEW",
                    "title": "Document visual content needs inspection",
                    "explanation": "Sigillum has extracted source-mapped content, but it does not certify all visual and accessibility characteristics. " + visual_limitations,
                    "reason_code": "DOCUMENT_VISUAL_ANALYSIS_NOT_COMPLETE",
                    "evidence_sufficiency": "INSUFFICIENT",
                    "confidence": 0.0,
                    "extraction_confidence": version.extraction_confidence,
                    "content_start": None,
                    "content_end": None,
                    "content_quote": None,
                    "region": None,
                    "evidence": [],
                    "suggestions": ["Inspect all original page visuals, logos, fine print and embedded images before approval."],
                }
            )
        for item in findings:
            self.db.add(models.Finding(review_id=review.id,**item))
        review.status = "COMPLETED"
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
