from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, JSON, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sigillum.infrastructure.database.session import Base

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(40), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    tenant_id: Mapped[str] = mapped_column(String(80), default="tenant_demo")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Brand(Base):
    __tablename__ = "brands"
    __table_args__ = (UniqueConstraint("tenant_id", "external_id", name="uq_brand_tenant_external_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(80), ForeignKey("tenants.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(160))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "brand_id", name="uq_membership_user_brand"),
        Index("ix_memberships_user_active", "user_id", "is_active"),
        Index("ix_memberships_tenant_brand", "tenant_id", "brand_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    tenant_id: Mapped[str] = mapped_column(String(80), ForeignKey("tenants.id"), index=True)
    brand_id: Mapped[str] = mapped_column(String(36), ForeignKey("brands.id"), index=True)
    role: Mapped[str] = mapped_column(String(40), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserSession(Base):
    __tablename__ = "user_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # JWT jti
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    membership_id: Mapped[str] = mapped_column(String(36), ForeignKey("memberships.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Submission(Base):
    __tablename__ = "submissions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(80), index=True)
    brand_id: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(240))
    channel: Mapped[str] = mapped_column(String(40))
    locale: Mapped[str] = mapped_column(String(20))
    geography: Mapped[str] = mapped_column(String(20))
    audience: Mapped[str] = mapped_column(String(80), default="consumer")
    offer_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    intended_use: Mapped[str] = mapped_column(String(40), default="general", nullable=False)
    product_scope: Mapped[str | None] = mapped_column(String(160), nullable=True)
    campaign_scope: Mapped[str | None] = mapped_column(String(160), nullable=True)
    context_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    publication_at: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(40), default="SUBMITTED", index=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    current_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    versions: Mapped[list["ContentVersion"]] = relationship(back_populates="submission", cascade="all, delete-orphan", order_by="ContentVersion.version_number")

class ContentVersion(Base):
    __tablename__ = "content_versions"
    __table_args__ = (
        UniqueConstraint("submission_id", "version_number", name="uq_content_version_number"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    submission_id: Mapped[str] = mapped_column(String(36), ForeignKey("submissions.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(120))
    storage_key: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    parent_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    scan_status: Mapped[str] = mapped_column(String(24), default="CLEAN", nullable=False)
    scan_engine: Mapped[str | None] = mapped_column(String(80), nullable=True)
    scan_scanned_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    scan_signature: Mapped[str | None] = mapped_column(String(255), nullable=True)
    retention_policy: Mapped[str] = mapped_column(String(80), default="MANUAL", nullable=False)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    extraction_confidence: Mapped[float] = mapped_column(default=1.0)
    extraction_status: Mapped[str] = mapped_column(String(40), default="COMPLETED")
    extraction_warnings: Mapped[list] = mapped_column(JSON, default=list)
    regions: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    submission: Mapped[Submission] = relationship(back_populates="versions")


class SubmissionUploadRequest(Base):
    """Idempotency reservation for a single upload attempt within a workspace."""

    __tablename__ = "submission_upload_requests"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "brand_id", "actor_id", "idempotency_key",
            name="uq_submission_upload_idempotency",
        ),
        Index("ix_submission_upload_scope_status", "tenant_id", "brand_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(80), index=True)
    brand_id: Mapped[str] = mapped_column(String(80), index=True)
    actor_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    payload_sha256: Mapped[str] = mapped_column(String(64))
    submission_id: Mapped[str] = mapped_column(String(36), ForeignKey("submissions.id"), index=True)
    content_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    review_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="PROCESSING", index=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ReviewJob(Base):
    """Durable review-job outbox row created with each immutable content version.

    Phase 05 records the job transactionally and executes it inline. Phase 11
    can move execution to a leased worker without changing the intake contract.
    """

    __tablename__ = "review_jobs"
    __table_args__ = (
        UniqueConstraint("content_version_id", "job_type", name="uq_review_job_version_type"),
        Index("ix_review_jobs_scope_status", "tenant_id", "brand_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(80), index=True)
    brand_id: Mapped[str] = mapped_column(String(80), index=True)
    submission_id: Mapped[str] = mapped_column(String(36), ForeignKey("submissions.id"), index=True)
    content_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("content_versions.id"), index=True)
    job_type: Mapped[str] = mapped_column(String(40), default="BRAND_ASSURANCE_REVIEW")
    status: Mapped[str] = mapped_column(String(24), default="QUEUED", index=True)
    context_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReviewRun(Base):
    __tablename__ = "review_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    submission_id: Mapped[str] = mapped_column(String(36), ForeignKey("submissions.id"), index=True)
    content_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("content_versions.id"), index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    brand_pack_version: Mapped[str] = mapped_column(String(80))
    knowledge_pack_hash: Mapped[str] = mapped_column(String(64), default="")
    knowledge_pack_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    analysis_config_version: Mapped[str] = mapped_column(String(80), default="rules-v1")
    status: Mapped[str] = mapped_column(String(40), default="COMPLETED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    findings: Mapped[list["Finding"]] = relationship(back_populates="review", cascade="all, delete-orphan", order_by="Finding.created_at")

class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    review_id: Mapped[str] = mapped_column(String(36), ForeignKey("review_runs.id"), index=True)
    code: Mapped[str] = mapped_column(String(80), index=True)
    category: Mapped[str] = mapped_column(String(60))
    severity: Mapped[str] = mapped_column(String(40))
    verdict: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(240))
    explanation: Mapped[str] = mapped_column(Text)
    reason_code: Mapped[str] = mapped_column(String(80))
    evidence_sufficiency: Mapped[str] = mapped_column(String(40))
    confidence: Mapped[float] = mapped_column(default=1.0)
    extraction_confidence: Mapped[float] = mapped_column(default=1.0)
    content_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    region: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(40), default="OPEN")
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suggestions: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    review: Mapped[ReviewRun] = relationship(back_populates="findings")

class Patch(Base):
    __tablename__ = "patches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    review_id: Mapped[str] = mapped_column(String(36), ForeignKey("review_runs.id"), index=True)
    finding_id: Mapped[str] = mapped_column(String(36), ForeignKey("findings.id"), index=True)
    base_content_hash: Mapped[str] = mapped_column(String(64))
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)
    replacement: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="PROPOSED")
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class Decision(Base):
    __tablename__ = "decisions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    review_id: Mapped[str] = mapped_column(String(36), ForeignKey("review_runs.id"), index=True)
    submission_id: Mapped[str] = mapped_column(String(36), ForeignKey("submissions.id"), index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(80), index=True)
    brand_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(80), index=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BrandKnowledgePackHead(Base):
    """Transactional active-version pointer for one tenant/brand Knowledge Pack."""

    __tablename__ = "brand_knowledge_pack_heads"
    __table_args__ = (
        UniqueConstraint("tenant_id", "brand_id", name="uq_brand_knowledge_pack_head_scope"),
        Index("ix_brand_pack_head_scope", "tenant_id", "brand_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(80), index=True)
    brand_id: Mapped[str] = mapped_column(String(100), index=True)
    pack_id: Mapped[str] = mapped_column(String(100))
    active_version_id: Mapped[str] = mapped_column(String(40))
    active_fingerprint: Mapped[str] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class BrandKnowledgePackVersion(Base):
    """Immutable JSON snapshot and provenance for a published pack version."""

    __tablename__ = "brand_knowledge_pack_versions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "brand_id", "version_id", name="uq_brand_pack_version_scope"),
        Index("ix_brand_pack_version_history", "tenant_id", "brand_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(80), index=True)
    brand_id: Mapped[str] = mapped_column(String(100), index=True)
    pack_id: Mapped[str] = mapped_column(String(100))
    version_id: Mapped[str] = mapped_column(String(40))
    pack_version: Mapped[str] = mapped_column(String(80))
    fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(40), default="PUBLISHED")
    base_version_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BrandKnowledgePackDraft(Base):
    """Mutable, optimistic-concurrency-protected draft for a single brand."""

    __tablename__ = "brand_knowledge_pack_drafts"
    __table_args__ = (
        Index("ix_brand_pack_draft_scope", "tenant_id", "brand_id", "status"),
        Index("ix_brand_pack_draft_updated", "tenant_id", "brand_id", "updated_at"),
    )

    draft_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(80), index=True)
    brand_id: Mapped[str] = mapped_column(String(100), index=True)
    pack_id: Mapped[str] = mapped_column(String(100))
    base_version_id: Mapped[str] = mapped_column(String(40))
    base_fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(40), default="DRAFT", index=True)
    snapshot: Mapped[dict] = mapped_column(JSON)
    validation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    published_version_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    published_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by: Mapped[str] = mapped_column(String(120))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    updated_by: Mapped[str] = mapped_column(String(120))


class BrandKnowledgePackDecision(Base):
    """Append-only owner decision history for an individual draft record."""

    __tablename__ = "brand_knowledge_pack_decisions"
    __table_args__ = (
        Index("ix_brand_pack_decision_record", "tenant_id", "brand_id", "record_type", "record_id"),
        Index("ix_brand_pack_decision_draft", "draft_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(80), index=True)
    brand_id: Mapped[str] = mapped_column(String(100), index=True)
    draft_id: Mapped[str] = mapped_column(String(36), index=True)
    record_type: Mapped[str] = mapped_column(String(40))
    record_id: Mapped[str] = mapped_column(String(120))
    decision_status: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
