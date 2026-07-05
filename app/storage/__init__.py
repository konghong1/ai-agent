"""
Storage Backend — Abstract layer for media asset storage.

Supports multiple backends via strategy pattern:
- MinIO/S3 (recommended for production)
- Local filesystem (for development)

All backends expose the same interface:
- put(file_bytes, object_key, mime_type) → {url, etag}
- get(object_key) → bytes | None
- delete(object_key) → bool
- exists(object_key) → bool
- presigned_url(object_key, expires_in) → str | None
"""
from __future__ import annotations

import logging
import mimetypes
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote

logger = logging.getLogger(__name__)


class StorageInfo(Protocol):
    """Return type for put() operations."""

    url: str
    etag: str


class StorageBackend(ABC):
    """Abstract storage backend — all implementations inherit this."""

    @abstractmethod
    def put(
        self,
        file_bytes: bytes,
        object_key: str,
        mime_type: str | None = None,
        **kwargs: Any,
    ) -> StorageInfo:
        """Upload bytes to storage. Returns URL and ETag."""

    @abstractmethod
    def get(self, object_key: str) -> bytes | None:
        """Download bytes from storage. Returns None if not found."""

    @abstractmethod
    def delete(self, object_key: str) -> bool:
        """Delete an object. Returns True if deleted, False if not found."""

    @abstractmethod
    def exists(self, object_key: str) -> bool:
        """Check if object exists."""

    @abstractmethod
    def presigned_url(self, object_key: str, expires_in: int = 3600) -> str | None:
        """Generate a signed/temporary URL for direct access.
        Returns None if backend doesn't support presigned URLs."""


# ───────────────────────────────────────────────────────────────────
# Concrete Backends
# ───────────────────────────────────────────────────────────────────


class MinIOStorageBackend(StorageBackend):
    """MinIO / AWS S3 compatible storage backend.
    
    Uses the S3 SDK for presigned URLs and efficient streaming.
    """

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str = "",
        use_ssl: bool = True,
        public_url: str | None = None,
    ):
        self.endpoint = endpoint.rstrip("/")
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket = bucket
        self.region = region or ("s3.amazonaws.com" if "amazonaws" in endpoint else "")
        self.use_ssl = use_ssl
        self.public_url = public_url or f"https://{bucket}.{endpoint.lstrip('http://').lstrip('https://')}"

    def _client(self):
        """Lazy import to avoid hard dependency on boto3."""
        try:
            import boto3
            from botocore.config import Config
            import botocore

            s3_config = Config(
                signature_version="s3v4",
                max_pool_connections=50,
                retries={"max_attempts": 3, "mode": "adaptive"},
            )
            client = boto3.client(
                "s3",
                endpoint_url=f"{'https' if self.use_ssl else 'http'}://{self.endpoint}",
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                config=s3_config,
                region_name=self.region,
                aws_signature_version="v4",
            )
            return client, boto3, botocore
        except ImportError:
            logger.error("boto3 not installed. Install with: pip install boto3")
            raise

    def _ensure_bucket(self):
        """Create bucket if it doesn't exist."""
        try:
            client, _, _ = self._client()
            client.head_bucket(Bucket=self.bucket)
        except Exception:
            client, _, _ = self._client()
            kwargs = {"Bucket": self.bucket}
            if self.region and self.region != "us-east-1":
                kwargs["CreateBucketConfiguration"] = {"LocationConstraint": self.region}
            client.create_bucket(**kwargs)

    def put(
        self,
        file_bytes: bytes,
        object_key: str,
        mime_type: str | None = None,
        **kwargs: Any,
    ) -> StorageInfo:
        self._ensure_bucket()
        try:
            client, boto3, botocore = self._client()
            content_type = mime_type or mimetypes.guess_type(object_key)[0] or "application/octet-stream"
            
            extra_args = {
                "ContentType": content_type,
                "ACL": "public-read",
            }
            extra_args.update(kwargs.get("extra_args", {}))

            client.put_object(
                Bucket=self.bucket,
                Key=object_key,
                Body=file_bytes,
                ContentType=content_type,
                ACL="public-read",
            )
            
            # Return presigned URL as fallback, or construct public URL
            try:
                url = client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.bucket, "Key": object_key},
                    ExpiresIn=0,  # 0 means permanent/public access
                )
                # Clean up the presigned URL to be a direct access URL
                url = url.split("?")[0] if "?" in url else url
            except Exception:
                url = f"{self.public_url}/{object_key}"

            return {"url": url, "etag": ""}
        except botocore.exceptions.ClientError as e:
            logger.error("MinIO put failed: %s", e)
            raise
        except Exception as e:
            logger.error("MinIO put failed: %s", e)
            raise

    def get(self, object_key: str) -> bytes | None:
        try:
            client, _, botocore = self._client()
            obj = client.get_object(Bucket=self.bucket, Key=object_key)
            return obj["Body"].read()
        except botocore.exceptions.ClientError:
            return None

    def delete(self, object_key: str) -> bool:
        try:
            client, _, botocore = self._client()
            client.delete_object(Bucket=self.bucket, Key=object_key)
            return True
        except botocore.exceptions.ClientError:
            return False

    def exists(self, object_key: str) -> bool:
        try:
            client, _, _ = self._client()
            client.head_object(Bucket=self.bucket, Key=object_key)
            return True
        except Exception:
            return False

    def presigned_url(self, object_key: str, expires_in: int = 3600) -> str | None:
        try:
            client, _, botocore = self._client()
            return client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": object_key},
                ExpiresIn=expires_in,
            )
        except Exception:
            return None


class LocalStorageBackend(StorageBackend):
    """Local filesystem storage backend.
    
    Useful for development and debugging.
    Stores files on disk with optional subdirectory organization.
    """

    def __init__(self, storage_dir: str = "./media", base_url: str = "/media"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.base_url = base_url

    def put(
        self,
        file_bytes: bytes,
        object_key: str,
        mime_type: str | None = None,
        **kwargs: Any,
    ) -> StorageInfo:
        file_path = self.storage_dir / object_key
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(file_bytes)
        
        # URL encode the object_key for the path
        url_path = quote(object_key, safe="/")
        url = f"{self.base_url}/{url_path}"
        
        return {"url": url, "etag": ""}

    def get(self, object_key: str) -> bytes | None:
        file_path = self.storage_dir / object_key
        if file_path.exists():
            return file_path.read_bytes()
        return None

    def delete(self, object_key: str) -> bool:
        file_path = self.storage_dir / object_key
        if file_path.exists():
            file_path.unlink()
            return True
        return False

    def exists(self, object_key: str) -> bool:
        return (self.storage_dir / object_key).exists()

    def presigned_url(self, object_key: str, expires_in: int = 3600) -> str | None:
        """Local storage doesn't need signed URLs."""
        url_path = quote(object_key, safe="/")
        return f"{self.base_url}/{url_path}"


# ───────────────────────────────────────────────────────────────────
# Factory — create storage backend from config
# ───────────────────────────────────────────────────────────────────


def create_storage_backend(
    backend_type: str = "minio",
    **kwargs: Any,
) -> StorageBackend:
    """Factory function to create the appropriate storage backend.
    
    Args:
        backend_type: "minio" or "local"
        **kwargs: Backend-specific configuration
    
    Returns:
        StorageBackend instance
    """
    if backend_type == "minio":
        return MinIOStorageBackend(
            endpoint=kwargs.get("endpoint", "localhost:9000"),
            access_key=kwargs.get("access_key", "minioadmin"),
            secret_key=kwargs.get("secret_key", "minioadmin"),
            bucket=kwargs.get("bucket", "media-assets"),
            region=kwargs.get("region", ""),
            use_ssl=kwargs.get("use_ssl", False),
            public_url=kwargs.get("public_url"),
        )
    elif backend_type == "local":
        return LocalStorageBackend(
            storage_dir=kwargs.get("storage_dir", "./media"),
            base_url=kwargs.get("base_url", "/media"),
        )
    else:
        raise ValueError(f"Unknown storage backend: {backend_type}")
