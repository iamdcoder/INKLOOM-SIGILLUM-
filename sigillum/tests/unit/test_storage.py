from __future__ import annotations

import io
import os

import pytest
from botocore.exceptions import ClientError
from botocore.response import StreamingBody

from sigillum.infrastructure.storage import (
    LocalFilesystemStorage,
    S3CompatibleStorage,
    StorageUnavailable,
    validate_object_key,
)


def test_local_storage_round_trip_and_private_permissions(tmp_path):
    storage = LocalFilesystemStorage(tmp_path / "private")
    payload = b"Confidential campaign content"

    storage.put_bytes("submission-a/1/original.txt", payload, "text/plain")

    assert storage.get_bytes("submission-a/1/original.txt") == payload
    assert storage.exists("submission-a/1/original.txt")
    assert storage.health_check() is True
    if os.name != "nt":
        assert (tmp_path / "private").stat().st_mode & 0o777 == 0o700
        assert (tmp_path / "private/submission-a/1").stat().st_mode & 0o777 == 0o700
        assert (tmp_path / "private/submission-a/1/original.txt").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "key",
    [
        "",
        "/absolute.txt",
        "../escape.txt",
        "one/../escape.txt",
        "one//empty.txt",
        "one\\\\windows.txt",
        "C:/drive.txt",
        "one/./dot.txt",
        "one/zero\\x00byte.txt",
    ],
)
def test_storage_rejects_unsafe_object_keys(key):
    with pytest.raises(ValueError):
        validate_object_key(key)


def test_local_storage_does_not_follow_symlink_outside_root(tmp_path):
    root = tmp_path / "private"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    try:
        (root / "escape").symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("Symlink creation is not available for this account or platform.")
    storage = LocalFilesystemStorage(root)

    with pytest.raises(ValueError):
        storage.put_bytes("escape/secret.txt", b"secret")


class FakeS3Client:
    def __init__(self):
        self.objects = {}
        self.bucket_exists = True

    def put_object(self, **kwargs):
        key = kwargs["Key"]
        if kwargs.get("IfNoneMatch") == "*" and key in self.objects:
            raise ClientError(
                {"Error": {"Code": "PreconditionFailed"}, "ResponseMetadata": {"HTTPStatusCode": 412}},
                "PutObject",
            )
        self.objects[key] = {
            "Body": kwargs["Body"],
            "ContentType": kwargs["ContentType"],
        }
        return {}

    def get_object(self, **kwargs):
        item = self.objects.get(kwargs["Key"])
        if item is None:
            raise ClientError(
                {"Error": {"Code": "NoSuchKey"}, "ResponseMetadata": {"HTTPStatusCode": 404}},
                "GetObject",
            )
        body = item["Body"]
        return {"Body": StreamingBody(io.BytesIO(body), len(body))}

    def head_object(self, **kwargs):
        if kwargs["Key"] not in self.objects:
            raise ClientError(
                {"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}},
                "HeadObject",
            )
        return {}

    def head_bucket(self, **kwargs):
        if not self.bucket_exists:
            raise ClientError(
                {"Error": {"Code": "NoSuchBucket"}, "ResponseMetadata": {"HTTPStatusCode": 404}},
                "HeadBucket",
            )
        return {}

    def create_bucket(self, **kwargs):
        self.bucket_exists = True
        return {}


def test_s3_adapter_round_trip_and_missing_key():
    client = FakeS3Client()
    storage = S3CompatibleStorage("sigillum-test", client=client)
    payload = b"private object bytes"

    storage.put_bytes("tenant/brand/file.txt", payload, "text/plain")

    assert storage.get_bytes("tenant/brand/file.txt") == payload
    assert storage.exists("tenant/brand/file.txt") is True
    assert storage.exists("tenant/brand/missing.txt") is False
    with pytest.raises(FileNotFoundError):
        storage.get_bytes("tenant/brand/missing.txt")
    assert storage.health_check() is True
    assert storage.driver_name == "s3_compatible"


def test_s3_adapter_can_bootstrap_missing_development_bucket():
    client = FakeS3Client()
    client.bucket_exists = False
    storage = S3CompatibleStorage("sigillum-test", client=client)

    storage.ensure_bucket()

    assert storage.health_check() is True


def test_s3_adapter_maps_provider_failure_to_storage_unavailable():
    class BrokenClient(FakeS3Client):
        def put_object(self, **kwargs):
            raise ClientError(
                {"Error": {"Code": "AccessDenied"}, "ResponseMetadata": {"HTTPStatusCode": 403}},
                "PutObject",
            )

    storage = S3CompatibleStorage("sigillum-test", client=BrokenClient())
    with pytest.raises(StorageUnavailable):
        storage.put_bytes("tenant/file.txt", b"data")


def test_local_storage_delete_is_idempotent(tmp_path):
    storage = LocalFilesystemStorage(tmp_path / "objects")
    storage.put_bytes("tenant/brand/file.bin", b"private")
    assert storage.exists("tenant/brand/file.bin") is True
    storage.delete_bytes("tenant/brand/file.bin")
    storage.delete_bytes("tenant/brand/file.bin")
    assert storage.exists("tenant/brand/file.bin") is False


def test_local_storage_immutable_put_refuses_to_replace_existing_object(tmp_path):
    storage = LocalFilesystemStorage(tmp_path / "private")
    storage.put_bytes_immutable("tenant/brand/original.txt", b"first", "text/plain")
    with pytest.raises(FileExistsError):
        storage.put_bytes_immutable("tenant/brand/original.txt", b"second", "text/plain")
    assert storage.get_bytes("tenant/brand/original.txt") == b"first"


def test_s3_immutable_put_uses_conditional_create():
    client = FakeS3Client()
    storage = S3CompatibleStorage("sigillum-test", client=client)
    storage.put_bytes_immutable("tenant/brand/original.txt", b"first", "text/plain")
    with pytest.raises(FileExistsError):
        storage.put_bytes_immutable("tenant/brand/original.txt", b"second", "text/plain")
    assert storage.get_bytes("tenant/brand/original.txt") == b"first"
