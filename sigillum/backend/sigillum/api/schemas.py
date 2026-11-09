from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=256)
    brand_id: str | None = Field(default=None, max_length=80)


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str
    role: str
    tenant_id: str
    tenant_name: str
    brand_id: str
    brand_record_id: str
    brand_name: str


class WorkspaceOut(BaseModel):
    membership_id: str
    tenant_id: str
    tenant_name: str
    brand_record_id: str
    brand_id: str
    brand_name: str
    role: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
    workspaces: list[WorkspaceOut] = Field(default_factory=list)


class WorkspaceSwitchRequest(BaseModel):
    brand_id: str = Field(min_length=1, max_length=80)


class MembershipCreateRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    role: str


class MembershipUpdateRequest(BaseModel):
    role: str | None = None
    is_active: bool | None = None
class DecisionRequest(BaseModel):
    action: str
    reason: str | None = None
class PatchRequest(BaseModel):
    finding_id: str
    replacement: str = Field(min_length=1, max_length=2000)
    rationale: str = Field(min_length=4, max_length=1000)
class SubmissionDraftCreate(BaseModel):
    title: str = Field(default="Untitled submission", min_length=1, max_length=240)
    channel: str = Field(default="direct_web", min_length=1, max_length=40)
    locale: str = Field(default="en-IN", min_length=2, max_length=20)
    geography: str = Field(default="IN", min_length=2, max_length=20)
    audience: str = Field(default="consumer", min_length=1, max_length=80)
    offer_id: str | None = Field(default=None, max_length=120)
    intended_use: str = Field(default="general", min_length=1, max_length=40)
    product_scope: str | None = Field(default=None, max_length=160)
    campaign_scope: str | None = Field(default=None, max_length=160)
    context_note: str | None = Field(default=None, max_length=2000)
    publication_at: str = Field(min_length=10, max_length=50)


class DuplicateCheckRequest(BaseModel):
    sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")


class RevisionRequest(BaseModel):
    content: str = Field(min_length=1, max_length=1_000_000)
    change_summary: str = Field(min_length=3, max_length=500)
class HealthResponse(BaseModel):
    status: str
    database: str
    brand_pack: str


class KnowledgePackSectionUpdate(BaseModel):
    section: str
    content: object


class FileGrantResponse(BaseModel):
    download_url: str
    expires_at: datetime
    expires_in_seconds: int


class KnowledgeSourceCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=240)
    source_type: str = Field(default="reference_text", min_length=2, max_length=60)
    version: int = Field(default=1, ge=1, le=100000)
    reference_text: str | None = Field(default=None, max_length=20000)
    source_uri: str | None = Field(default=None, max_length=2048)
    valid_from: str | None = Field(default=None, max_length=50)
    valid_until: str | None = Field(default=None, max_length=50)


class KnowledgeRecordDecisionRequest(BaseModel):
    status: str = Field(pattern="^(approved|draft|not_approved|rejected)$")
    reason: str | None = Field(default=None, max_length=1000)
