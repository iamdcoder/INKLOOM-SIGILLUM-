from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class LoginRequest(BaseModel):
    email: str
    password: str
class UserOut(BaseModel):
    id: str; email: str; display_name: str; role: str
    model_config=ConfigDict(from_attributes=True)
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
class DecisionRequest(BaseModel):
    action: str
    reason: str | None = None
class PatchRequest(BaseModel):
    finding_id: str
    replacement: str = Field(min_length=1, max_length=2000)
    rationale: str = Field(min_length=4, max_length=1000)
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
