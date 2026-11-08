from functools import lru_cache
from pathlib import Path
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    app_env: str = "development"
    app_name: str = "Inkloom Sigillum"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./data/sigillum.db"
    storage_root: Path = Path("./data/private_uploads")
    brand_pack_path: Path = Path("./fixtures/brand_pack/v1")
    max_upload_bytes: int = 10 * 1024 * 1024
    jwt_secret_key: str = "local-development-secret-change-before-deployment"
    access_token_minutes: int = 480
    sigillum_demo_password: str = "ChangeMe-Local-Only"
    cors_origins: str = "http://localhost:3000"
    tesseract_cmd: str = "tesseract"

    @field_validator("max_upload_bytes")
    @classmethod
    def valid_upload_limit(cls, value: int) -> int:
        if value < 1024 or value > 50 * 1024 * 1024:
            raise ValueError("MAX_UPLOAD_BYTES must be between 1 KB and 50 MB")
        return value

    def validate_security(self) -> None:
        if self.app_env.lower() == "production":
            if len(self.jwt_secret_key) < 32 or self.jwt_secret_key.startswith("local-"):
                raise ValueError("Production requires a strong JWT_SECRET_KEY of at least 32 characters")
            if self.sigillum_demo_password == "ChangeMe-Local-Only":
                raise ValueError("Change the demo password before production deployment")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_security()
    return settings
