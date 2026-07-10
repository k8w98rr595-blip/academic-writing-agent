from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Protocol

import boto3
from botocore.client import BaseClient

from .config import get_settings


def validate_object_key(key: str) -> str:
    if "\\" in key:
        raise ValueError("Invalid object key")
    normalized = key.replace("\\", "/")
    if not normalized or normalized.startswith("/") or ".." in Path(normalized).parts:
        raise ValueError("Invalid object key")
    return normalized


class ObjectStorage(Protocol):
    def put(self, key: str, content: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete_prefix(self, prefix: str) -> None: ...


class LocalObjectStorage:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or get_settings().object_storage_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _safe(self, key: str) -> Path:
        target = (self.root / validate_object_key(key)).resolve()
        if self.root not in target.parents and target != self.root:
            raise ValueError("Object path escapes storage root")
        return target

    def put(self, key: str, content: bytes) -> None:
        target = self._safe(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_bytes(content)
        os.replace(temporary, target)

    def get(self, key: str) -> bytes:
        return self._safe(key).read_bytes()

    def delete_prefix(self, prefix: str) -> None:
        target = self._safe(prefix)
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()


class S3ObjectStorage:
    def __init__(self, client: BaseClient | None = None) -> None:
        settings = get_settings()
        if not settings.s3_endpoint_url or not settings.s3_access_key_id or not settings.s3_secret_access_key:
            raise RuntimeError("S3-compatible object storage is not configured")
        self.bucket = settings.s3_bucket
        self.client = client or boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            region_name=settings.s3_region,
        )

    def put(self, key: str, content: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=validate_object_key(key), Body=content)

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=validate_object_key(key))["Body"].read()

    def delete_prefix(self, prefix: str) -> None:
        safe_prefix = validate_object_key(prefix).rstrip("/") + "/"
        continuation: str | None = None
        while True:
            options = {"Bucket": self.bucket, "Prefix": safe_prefix}
            if continuation:
                options["ContinuationToken"] = continuation
            response = self.client.list_objects_v2(**options)
            objects = [{"Key": row["Key"]} for row in response.get("Contents", [])]
            if objects:
                self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": objects, "Quiet": True})
            if not response.get("IsTruncated"):
                break
            continuation = response.get("NextContinuationToken")


def get_object_storage() -> ObjectStorage:
    settings = get_settings()
    if settings.object_storage_mode == "local":
        return LocalObjectStorage()
    if settings.object_storage_mode in {"s3", "minio"}:
        return S3ObjectStorage()
    raise RuntimeError("Unsupported object storage mode")
