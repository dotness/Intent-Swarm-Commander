"""MinIO / S3 object store client for partitioned Parquet telemetry and tactical snapshots."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)

_SAFE_KEY_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._/=-]*$")


class MinioUnavailableError(RuntimeError):
    """Raised when MinIO / S3 object storage is unreachable or fails."""


class ObjectNotFoundError(FileNotFoundError):
    """Raised when a requested S3/MinIO object key does not exist."""


def validate_object_key(key: str) -> str:
    """Validate and sanitize an S3/MinIO object key against path traversal."""
    if not key or not isinstance(key, str):
        raise ValueError("Object key must be a non-empty string")
    if key.startswith("/") or "\\" in key or ".." in key or "\x00" in key:
        raise ValueError(f"Unsafe object key rejected: {key!r}")
    normalized = key.lstrip("./")
    if not normalized or ".." in normalized.split("/") or not _SAFE_KEY_RE.match(key):
        raise ValueError(f"Invalid object key format: {key!r}")
    return key


class MinioStore:
    """S3-compatible object store adapter backed by boto3."""

    PARQUET_BUCKET = "tactical-telemetry"
    SNAPSHOT_BUCKET = "tactical-snapshots"

    def __init__(
        self,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        s3_client: Any = None,
        timeout_s: float = 5.0,
    ) -> None:
        self.endpoint_url = endpoint_url or os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
        self.access_key = (
            access_key
            or os.getenv("MINIO_ACCESS_KEY")
            or os.getenv("MINIO_ROOT_USER")
            or os.getenv("AWS_ACCESS_KEY_ID")
            or ""
        )
        self.secret_key = (
            secret_key
            or os.getenv("MINIO_SECRET_KEY")
            or os.getenv("MINIO_ROOT_PASSWORD")
            or os.getenv("AWS_SECRET_ACCESS_KEY")
            or ""
        )
        self.timeout_s = timeout_s
        self._client = s3_client

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self.access_key or not self.secret_key:
            raise MinioUnavailableError(
                "MinIO credentials are not configured (set MINIO_ACCESS_KEY and MINIO_SECRET_KEY)."
            )
        try:
            self._client = boto3.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name="us-east-1",
                config=Config(
                    signature_version="s3v4",
                    s3={"addressing_style": "path"},
                    connect_timeout=self.timeout_s,
                    read_timeout=self.timeout_s,
                    retries={"max_attempts": 1},
                ),
            )
            return self._client
        except Exception as exc:
            raise MinioUnavailableError(f"Failed to initialize MinIO client: {exc}") from exc

    async def ensure_buckets(
        self,
        buckets: tuple[str, ...] = (PARQUET_BUCKET, SNAPSHOT_BUCKET),
    ) -> None:
        """Ensure required buckets exist in MinIO."""
        client = self._get_client()

        def _ensure() -> None:
            try:
                existing = {b["Name"] for b in client.list_buckets().get("Buckets", [])}
                for bucket in buckets:
                    if bucket not in existing:
                        client.create_bucket(Bucket=bucket)
            except (BotoCoreError, ClientError, OSError) as exc:
                raise MinioUnavailableError(f"Failed to ensure MinIO buckets: {exc}") from exc

        await asyncio.to_thread(_ensure)

    async def put_object(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload raw bytes to an S3/MinIO bucket after validating the key."""
        safe_key = validate_object_key(key)
        client = self._get_client()

        def _put() -> None:
            try:
                client.put_object(
                    Bucket=bucket,
                    Key=safe_key,
                    Body=data,
                    ContentType=content_type,
                )
            except (BotoCoreError, ClientError, OSError) as exc:
                raise MinioUnavailableError(f"MinIO put_object failed for {bucket}/{safe_key}: {exc}") from exc

        await asyncio.to_thread(_put)
        return safe_key

    async def get_object(self, bucket: str, key: str) -> bytes:
        """Download raw bytes from an S3/MinIO bucket."""
        safe_key = validate_object_key(key)
        client = self._get_client()

        def _get() -> bytes:
            try:
                resp = client.get_object(Bucket=bucket, Key=safe_key)
                body = resp["Body"]
                return body.read() if hasattr(body, "read") else bytes(body)
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code", "")
                if code in {"NoSuchKey", "404", "NotFound"}:
                    raise ObjectNotFoundError(f"Object not found: {bucket}/{safe_key}") from exc
                raise MinioUnavailableError(f"MinIO get_object failed: {exc}") from exc
            except ObjectNotFoundError:
                raise
            except FileNotFoundError as exc:
                raise ObjectNotFoundError(f"Object not found: {bucket}/{safe_key}") from exc
            except (BotoCoreError, OSError) as exc:
                raise MinioUnavailableError(f"MinIO get_object unavailable: {exc}") from exc

        return await asyncio.to_thread(_get)

    async def list_objects(self, bucket: str, prefix: str = "") -> list[str]:
        """List all object keys inside a bucket matching prefix."""
        if prefix:
            validate_object_key(prefix.rstrip("/") or prefix)
        client = self._get_client()

        def _list() -> list[str]:
            try:
                keys: list[str] = []
                continuation: str | None = None
                while True:
                    kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
                    if continuation:
                        kwargs["ContinuationToken"] = continuation
                    resp = client.list_objects_v2(**kwargs)
                    for item in resp.get("Contents", []):
                        keys.append(item["Key"])
                    if not resp.get("IsTruncated"):
                        break
                    continuation = resp.get("NextContinuationToken")
                return keys
            except (BotoCoreError, ClientError, OSError) as exc:
                raise MinioUnavailableError(f"MinIO list_objects failed: {exc}") from exc

        return await asyncio.to_thread(_list)
