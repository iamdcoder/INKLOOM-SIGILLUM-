from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
from sqlalchemy.orm import Session
from sigillum.infrastructure.database import models
from sigillum.modules.content.extraction import extract
from sigillum.modules.knowledge.brand_pack import BrandPack
from sigillum.modules.verification.engine import VerificationEngine

class ReviewService:
    def __init__(self, db: Session, pack: BrandPack, storage_root: Path):
        self.db=db; self.pack=pack; self.storage_root=storage_root; self.engine=VerificationEngine(pack)

    def create_version(self, submission: models.Submission, filename: str, mime_type: str, data: bytes, actor: models.User):
        result=extract(filename, data)
        digest=sha256(data).hexdigest()
        version_number=len(submission.versions)+1
        storage_key=f"{submission.id}/{version_number}/{uuid4().hex}{Path(filename).suffix.lower()}"
        target=self.storage_root/storage_key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        version=models.ContentVersion(submission_id=submission.id,version_number=version_number,filename=Path(filename).name,mime_type=mime_type,storage_key=storage_key,sha256=digest,size_bytes=len(data),extracted_text=result.text,extraction_confidence=result.confidence,extraction_status=result.status,extraction_warnings=result.warnings,regions=result.regions,created_by=actor.id)
        self.db.add(version); self.db.flush()
        submission.current_version_id=version.id
        return version

    def run_review(self, submission: models.Submission, version: models.ContentVersion):
        review=models.ReviewRun(
            submission_id=submission.id,
            content_version_id=version.id,
            content_hash=version.sha256,
            brand_pack_version=self.pack.version(),
            knowledge_pack_hash=self.pack.fingerprint(),
            knowledge_pack_snapshot=self.pack.snapshot(),
            analysis_config_version="deterministic-rules-v1",
            status="COMPLETED",
        )
        self.db.add(review); self.db.flush()
        context={"offer_id":submission.offer_id,"geography":submission.geography,"channel":submission.channel,"locale":submission.locale,"audience":submission.audience}
        publication_at = datetime.fromisoformat(submission.publication_at.replace("Z", "+00:00"))
        findings=self.engine.analyse(version.extracted_text,context,publication_at,version.extraction_confidence,version.regions)
        if version.mime_type in {"image/png", "image/jpeg"}:
            # Honest manual-review gates: OCR is available, but brand-mark identity and
            # standards-grade contrast measurement are not automated in this build.
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
                {
                    "code": "CONTRAST_MANUAL_REVIEW",
                    "category": "accessibility",
                    "severity": "review_required",
                    "verdict": "NEEDS_MANUAL_REVIEW",
                    "title": "Text contrast requires visual measurement",
                    "explanation": "OCR regions are available, but this build does not calculate a standards-grade contrast ratio for each text/background pair. Measure important text and disclaimers in the original creative before approval.",
                    "reason_code": "CONTRAST_MEASUREMENT_NOT_AUTOMATED",
                    "evidence_sufficiency": "INSUFFICIENT",
                    "confidence": 0.0,
                    "extraction_confidence": version.extraction_confidence,
                    "content_start": None,
                    "content_end": None,
                    "content_quote": None,
                    "region": None,
                    "evidence": [],
                    "suggestions": [],
                },
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

def audit(db: Session, tenant_id: str, actor_id: str | None, event_type: str, entity_type: str, entity_id: str, details: dict | None=None):
    db.add(models.AuditEvent(tenant_id=tenant_id,actor_id=actor_id,event_type=event_type,entity_type=entity_type,entity_id=entity_id,details=details or {}))
