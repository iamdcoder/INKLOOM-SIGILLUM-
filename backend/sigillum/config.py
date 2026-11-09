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
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_pool_timeout_seconds: int = 30
    database_connect_timeout_seconds: int = 5
    storage_root: Path = Path("./data/private_uploads")
    storage_backend: str = "local"
    s3_endpoint_url: str | None = None
    s3_bucket: str = "sigillum-private"
    s3_region: str = "us-east-1"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_verify_ssl: bool = True
    brand_pack_path: Path = Path("./fixtures/brand_pack/v1")
    max_upload_bytes: int = 10 * 1024 * 1024
    jwt_secret_key: str = "local-development-secret-change-before-deployment"
    access_token_minutes: int = 480
    file_grant_minutes: int = 5
    sigillum_demo_password: str = "ChangeMe-Local-Only"
    cors_origins: str = "http://localhost:3000"
    tesseract_cmd: str = "tesseract"
    clamav_host: str = "127.0.0.1"
    clamav_port: int = 3310
    clamav_timeout_seconds: int = 30

    @field_validator("database_pool_size")
    @classmethod
    def valid_database_pool_size(cls, value: int) -> int:
        if value < 1 or value > 50:
            raise ValueError("DATABASE_POOL_SIZE must be between 1 and 50")
        return value

    @field_validator("database_max_overflow")
    @classmethod
    def valid_database_max_overflow(cls, value: int) -> int:
        if value < 0 or value > 100:
            raise ValueError("DATABASE_MAX_OVERFLOW must be between 0 and 100")
        return value

    @field_validator("database_pool_timeout_seconds", "database_connect_timeout_seconds")
    @classmethod
    def valid_database_timeouts(cls, value: int) -> int:
        if value < 1 or value > 300:
            raise ValueError("Database timeouts must be between 1 and 300 seconds")
        return value

    @field_validator("clamav_port")
    @classmethod
    def valid_clamav_port(cls, value: int) -> int:
        if value < 1 or value > 65535:
            raise ValueError("CLAMAV_PORT must be between 1 and 65535")
        return value

    @field_validator("clamav_timeout_seconds")
    @classmethod
    def valid_clamav_timeout(cls, value: int) -> int:
        if value < 1 or value > 300:
            raise ValueError("CLAMAV_TIMEOUT_SECONDS must be between 1 and 300")
        return value

    @field_validator("file_grant_minutes")
    @classmethod
    def valid_file_grant_minutes(cls, value: int) -> int:
        if value < 1 or value > 15:
            raise ValueError("FILE_GRANT_MINUTES must be between 1 and 15")
        return value

    @field_validator("storage_backend")
    @classmethod
    def valid_storage_backend(cls, value: str) -> str:
        backend = value.strip().lower()
        if backend not in {"local", "s3"}:
            raise ValueError("STORAGE_BACKEND must be either 'local' or 's3'")
        return backend

    @field_validator("s3_endpoint_url")
    @classmethod
    def valid_s3_endpoint(cls, value: str | None) -> str | None:
        if value is not None:
            endpoint = value.strip()
            if not endpoint.startswith(("http://", "https://")):
                raise ValueError("S3_ENDPOINT_URL must start with http:// or https://")
            return endpoint.rstrip("/")
        return None

    @field_validator("s3_bucket")
    @classmethod
    def valid_s3_bucket(cls, value: str) -> str:
        bucket = value.strip()
        if not bucket or len(bucket) > 63 or "/" in bucket or "\\" in bucket:
            raise ValueError("S3_BUCKET must be a valid non-empty bucket name")
        return bucket

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
