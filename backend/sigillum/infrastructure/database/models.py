from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, JSON, UniqueConstraint
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
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    extraction_confidence: Mapped[float] = mapped_column(default=1.0)
    extraction_status: Mapped[str] = mapped_column(String(40), default="COMPLETED")
    extraction_warnings: Mapped[list] = mapped_column(JSON, default=list)
    regions: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    submission: Mapped[Submission] = relationship(back_populates="versions")

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
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(80), index=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
