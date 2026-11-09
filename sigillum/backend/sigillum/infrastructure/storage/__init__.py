"""Private local and S3-compatible object storage adapters.

Original content is stored under opaque keys. The API never receives or exposes
an object-store URL; all reads pass through the authenticated application route.
"""
from __future__ import annotations

import os
import tempfile
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


class StorageUnavailable(RuntimeError):
    """The configured storage service could not complete an operation."""


class ObjectStorage(Protocol):
    @property
    def driver_name(self) -> str: ...

    def put_bytes(self, key: str, data: bytes, content_type: str | None = None) -> None: ...

    def put_bytes_immutable(self, key: str, data: bytes, content_type: str | None = None) -> None: ...

    def get_bytes(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def delete_bytes(self, key: str) -> None: ...

    def health_check(self) -> bool: ...


def validate_object_key(key: str) -> str:
    """Reject absolute paths, traversal, Windows separators and empty segments."""
    if not isinstance(key, str) or not key or "\x00" in key:
        raise ValueError("Storage key must be a non-empty relative path")
    if key.startswith("/") or "\\" in key or ":" in key:
        raise ValueError("Storage key must use relative POSIX path components")
    parts = key.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Storage key contains an unsafe path component")
    parsed = PurePosixPath(key)
    if parsed.is_absolute() or parsed.as_posix() != key:
        raise ValueError("Storage key is not canonical")
    return key


class LocalFilesystemStorage:
    """Atomic, private local object storage for development and offline demos."""

    def __init__(self, root: Path | str):
        self.root = Path(root).expanduser().resolve()

    @property
    def driver_name(self) -> str:
        return "local_filesystem"

    def _path(self, key: str, *, create_parent: bool) -> Path:
        key = validate_object_key(key)
        target = self.root.joinpath(*key.split("/"))
        if create_parent:
            try:
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                os.chmod(target.parent, 0o700)
            except OSError as exc:
                raise StorageUnavailable("Local object storage directory could not be secured.") from exc
        resolved_parent = target.parent.resolve(strict=False)
        resolved_target = resolved_parent / target.name
        if not resolved_parent.is_relative_to(self.root) or not resolved_target.is_relative_to(self.root):
            raise ValueError("Storage key escapes the configured storage root")
        if target.is_symlink():
            raise ValueError("Storage target must not be a symbolic link")
        return target

    def put_bytes(self, key: str, data: bytes, content_type: str | None = None) -> None:
        del content_type  # Local files do not need a content-type sidecar.
        if not isinstance(data, bytes):
            raise TypeError("Storage payload must be bytes")
        target = self._path(key, create_parent=True)
        temp_path: Path | None = None
        try:
            descriptor, temp_name = tempfile.mkstemp(
                prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
            )
            temp_path = Path(temp_name)
            os.chmod(temp_path, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, target)
        except OSError as exc:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            raise StorageUnavailable("Local object storage could not write the content.") from exc

    def put_bytes_immutable(self, key: str, data: bytes, content_type: str | None = None) -> None:
        """Atomically create a new object and refuse to replace an existing key."""
        del content_type
        if not isinstance(data, bytes):
            raise TypeError("Storage payload must be bytes")
        target = self._path(key, create_parent=True)
        temp_path: Path | None = None
        try:
            descriptor, temp_name = tempfile.mkstemp(
                prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
            )
            temp_path = Path(temp_name)
            os.chmod(temp_path, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            # A hard-link create is atomic and does not replace an existing target.
            os.link(temp_path, target)
            temp_path.unlink(missing_ok=True)
        except FileExistsError:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            raise
        except OSError as exc:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            raise StorageUnavailable("Local object storage could not create the immutable content.") from exc

    def get_bytes(self, key: str) -> bytes:
        target = self._path(key, create_parent=False)
        try:
            return target.read_bytes()
        except FileNotFoundError:
            raise FileNotFoundError(key) from None
        except OSError as exc:
            raise StorageUnavailable("Local object storage could not read the content.") from exc

    def exists(self, key: str) -> bool:
        target = self._path(key, create_parent=False)
        return target.is_file()

    def delete_bytes(self, key: str) -> None:
        """Idempotently delete one object from the private local store."""
        target = self._path(key, create_parent=False)
        try:
            target.unlink(missing_ok=True)
        except OSError as exc:
            raise StorageUnavailable("Local object storage could not delete the content.") from exc

    def health_check(self) -> bool:
        try:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(self.root, 0o700)
            descriptor, temp_name = tempfile.mkstemp(prefix=".sigillum-health-", dir=self.root)
            os.close(descriptor)
            Path(temp_name).unlink(missing_ok=True)
            return True
        except OSError as exc:
            raise StorageUnavailable("Local object storage is not writable.") from exc


class S3CompatibleStorage:
    """S3 API adapter suitable for MinIO and AWS S3-compatible endpoints."""

    def __init__(
        self,
        bucket: str,
        *,
        endpoint_url: str | None = None,
        region: str = "us-east-1",
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        verify_ssl: bool = True,
        client=None,
    ):
        if not bucket or len(bucket) > 63:
            raise ValueError("S3 bucket name must contain between 1 and 63 characters")
        self.bucket = bucket
        self.region = region
        self.client = client or boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            region_name=region,
            aws_access_key_id=access_key_id or None,
            aws_secret_access_key=secret_access_key or None,
            verify=verify_ssl,
            config=Config(
                s3={"addressing_style": "path"},
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=5,
                read_timeout=20,
                max_pool_connections=20,
            ),
        )

    @property
    def driver_name(self) -> str:
        return "s3_compatible"

    @staticmethod
    def _missing(exc: ClientError) -> bool:
        response = exc.response or {}
        error = response.get("Error", {})
        metadata = response.get("ResponseMetadata", {})
        code = str(error.get("Code", ""))
        status = metadata.get("HTTPStatusCode")
        return code in {"NoSuchKey", "NoSuchBucket", "NotFound", "404"} or status == 404

    def ensure_bucket(self) -> None:
        """Create the bucket for local development; production buckets are provisioned externally."""
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return
        except ClientError as exc:
            if not self._missing(exc):
                raise StorageUnavailable("Configured object-storage bucket is unavailable.") from exc
        except BotoCoreError as exc:
            raise StorageUnavailable("Configured object-storage bucket could not be inspected.") from exc
        try:
            create_args = {"Bucket": self.bucket}
            if self.region not in {None, "us-east-1"}:
                create_args["CreateBucketConfiguration"] = {
                    "LocationConstraint": self.region
                }
            self.client.create_bucket(**create_args)
        except (ClientError, BotoCoreError) as exc:
            raise StorageUnavailable("Configured object-storage bucket could not be created.") from exc

    def put_bytes(self, key: str, data: bytes, content_type: str | None = None) -> None:
        key = validate_object_key(key)
        if not isinstance(data, bytes):
            raise TypeError("Storage payload must be bytes")
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType=content_type or "application/octet-stream",
            )
        except (ClientError, BotoCoreError) as exc:
            raise StorageUnavailable("Configured object storage could not write the content.") from exc

    def put_bytes_immutable(self, key: str, data: bytes, content_type: str | None = None) -> None:
        """Create a new S3 object only when the key does not already exist."""
        key = validate_object_key(key)
        if not isinstance(data, bytes):
            raise TypeError("Storage payload must be bytes")
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType=content_type or "application/octet-stream",
                IfNoneMatch="*",
            )
        except ClientError as exc:
            code = str((exc.response or {}).get("Error", {}).get("Code", ""))
            status = (exc.response or {}).get("ResponseMetadata", {}).get("HTTPStatusCode")
            if code in {"PreconditionFailed", "ConditionalRequestConflict", "412"} or status == 412:
                raise FileExistsError(key) from None
            raise StorageUnavailable("Configured object storage could not create immutable content.") from exc
        except (BotoCoreError, TypeError) as exc:
            raise StorageUnavailable("Configured object storage could not create immutable content.") from exc

    def get_bytes(self, key: str) -> bytes:
        key = validate_object_key(key)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            body = response["Body"]
            try:
                return body.read()
            finally:
                body.close()
        except ClientError as exc:
            if self._missing(exc):
                raise FileNotFoundError(key) from None
            raise StorageUnavailable("Configured object storage could not read the content.") from exc
        except (BotoCoreError, KeyError, OSError) as exc:
            raise StorageUnavailable("Configured object storage returned an invalid response.") from exc

    def exists(self, key: str) -> bool:
        key = validate_object_key(key)
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            if self._missing(exc):
                return False
            raise StorageUnavailable("Configured object storage could not inspect the content.") from exc
        except BotoCoreError as exc:
            raise StorageUnavailable("Configured object storage could not inspect the content.") from exc

    def delete_bytes(self, key: str) -> None:
        """Delete a private S3-compatible object; missing keys are treated as success."""
        key = validate_object_key(key)
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except (ClientError, BotoCoreError) as exc:
            raise StorageUnavailable("Configured object storage could not delete the content.") from exc

    def health_check(self) -> bool:
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return True
        except (ClientError, BotoCoreError) as exc:
            raise StorageUnavailable("Configured object-storage bucket is not reachable.") from exc


@lru_cache(maxsize=8)
def _cached_storage(
    backend: str,
    storage_root: str,
    endpoint_url: str | None,
    bucket: str,
    region: str,
    access_key_id: str | None,
    secret_access_key: str | None,
    verify_ssl: bool,
) -> ObjectStorage:
    if backend == "local":
        return LocalFilesystemStorage(storage_root)
    if backend == "s3":
        return S3CompatibleStorage(
            bucket,
            endpoint_url=endpoint_url,
            region=region,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            verify_ssl=verify_ssl,
        )
    raise ValueError("STORAGE_BACKEND must be either 'local' or 's3'")


def get_storage(settings=None) -> ObjectStorage:
    """Return the process-wide storage adapter for the validated application settings."""
    if settings is None:
        from sigillum.config import get_settings

        settings = get_settings()
    return _cached_storage(
        backend=settings.storage_backend,
        storage_root=str(settings.storage_root),
        endpoint_url=settings.s3_endpoint_url,
        bucket=settings.s3_bucket,
        region=settings.s3_region,
        access_key_id=settings.s3_access_key_id,
        secret_access_key=settings.s3_secret_access_key,
        verify_ssl=settings.s3_verify_ssl,
    )
