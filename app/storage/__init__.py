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

import base64
import logging
import mimetypes
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote, urlparse, parse_qs

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
                region_name=self.region or None,
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

            try:
                client.put_object(
                    Bucket=self.bucket,
                    Key=object_key,
                    Body=file_bytes,
                    ContentType=content_type,
                    ACL="public-read",
                )
            except botocore.exceptions.ClientError as acl_err:
                # Some MinIO deployments reject canned ACLs when no bucket
                # policy allows anonymous access. Retry without ACL — the
                # object is still served through our authenticated proxy.
                logger.warning("MinIO ACL rejected, retrying without ACL: %s", acl_err)
                client.put_object(
                    Bucket=self.bucket,
                    Key=object_key,
                    Body=file_bytes,
                    ContentType=content_type,
                )

            # Return presigned URL as fallback, or construct public URL
            try:
                url = client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.bucket, "Key": object_key},
                    ExpiresIn=3600,
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
            bucket=kwargs.get("bucket", "ai-agent-minio"),
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


# ───────────────────────────────────────────────────────────────────
# Singleton accessor (configured from environment)
# ───────────────────────────────────────────────────────────────────

_storage_backend: StorageBackend | None = None


def get_storage_backend() -> StorageBackend:
    """Get or create the global storage backend singleton.

    Defaults to the MinIO/S3 backend (bucket ``ai-agent-minio``) because the
    platform is designed to re-host generated images/videos in object storage.
    Set ``STORAGE_BACKEND=local`` to fall back to the local filesystem (dev).
    """
    global _storage_backend
    if _storage_backend is None:
        backend_type = os.getenv("STORAGE_BACKEND", "minio")
        _storage_backend = create_storage_backend(
            backend_type=backend_type,
            endpoint=os.getenv("MINIO_ENDPOINT", "localhost:9000"),
            access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
            secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
            bucket=os.getenv("MINIO_BUCKET", "ai-agent-minio"),
            public_url=os.getenv("MINIO_PUBLIC_URL", "http://localhost:9000/ai-agent-minio"),
            use_ssl=os.getenv("MINIO_USE_SSL", "false").lower() == "true",
        )
    return _storage_backend


def reset_storage_backend() -> None:
    """Drop the cached singleton (useful for tests / config reloads)."""
    global _storage_backend
    _storage_backend = None


# Per-bucket backend cache (so chat uploads can live in a separate bucket
# from generated media without reconstructing clients on every call).
_bucket_backends: dict[str, StorageBackend] = {}


def get_storage_backend_for_bucket(bucket: str | None = None) -> StorageBackend:
    """Return a storage backend scoped to ``bucket``.

    ``None`` (or the configured default) returns the global singleton, which
    keeps the generated-media bucket (``ai-agent-minio``) as the default.
    Other buckets (e.g. ``chat-uploads``) get their own cached backend so
    uploaded chat images never mix with generated assets.
    """
    if not bucket:
        return get_storage_backend()
    if bucket not in _bucket_backends:
        _bucket_backends[bucket] = create_storage_backend(
            backend_type=os.getenv("STORAGE_BACKEND", "minio"),
            endpoint=os.getenv("MINIO_ENDPOINT", "localhost:9000"),
            access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
            secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
            bucket=bucket,
            public_url=os.getenv("MINIO_PUBLIC_URL", f"http://localhost:9000/{bucket}"),
            use_ssl=os.getenv("MINIO_USE_SSL", "false").lower() == "true",
        )
    return _bucket_backends[bucket]


def _downscale_image_bytes(raw: bytes, max_side: int = 1280, quality: int = 85) -> bytes:
    """Shrink an image so its longest side is at most ``max_side`` and re-encode
    as JPEG for a compact payload.

    Why: reference images uploaded from phones are often 3000x4000+; inlined as
    base64 they blow up the provider request body and the upstream image model
    hangs / fails (``do_request_failed`` / read timeout). Downscaling before
    inlining keeps the payload small and the upstream happy.

    Fail-safe: returns ``raw`` unchanged if Pillow is missing or the bytes are
    not a decodable image, so inlining never breaks on a bad/unsupported file.
    """
    try:
        from PIL import Image
        import io as _io
        img = Image.open(_io.BytesIO(raw))
        needs_shrink = max(img.size) > max_side
        # A small, already-JPEG reference is left untouched to preserve quality.
        if not needs_shrink and img.format == "JPEG":
            return raw
        if needs_shrink:
            img.thumbnail((max_side, max_side))
        img = img.convert("RGB")  # drop alpha channel (JPEG has none)
        out = _io.BytesIO()
        img.save(out, "JPEG", quality=quality)
        return out.getvalue()
    except Exception:
        return raw


def inline_reference_image(ref: str) -> str | None:
    """Turn a reference-image reference into an inline base64 ``data:`` URL.

    Returns the original string when it cannot / should not be inlined:

    - ``data:`` URL            -> downscaled + re-encoded if large, else as-is.
    - Internal by-key proxy URL (``/api/media/assets/by-key/<key>?bucket=``)
      -> downloaded from object storage, downscaled, and inlined as base64,
      because the downstream model cannot reach our private proxy / local MinIO.
    - Other ``http(s)`` URL    -> returned as-is (provider fetches directly).

    This is the single source of truth for "local address -> base64" so both
    the chat path and the image/video generation path behave identically.
    Reference images are downscaled here so an oversized upload never produces
    an upstream failure.
    """
    if not ref or not isinstance(ref, str):
        return None
    if ref.startswith("data:"):
        # Frontend may hand us an already-inlined (and possibly large) data URL.
        try:
            _, b64 = ref.split(",", 1)
            raw = base64.b64decode(b64)
            shrunk = _downscale_image_bytes(raw)
            if shrunk is not raw:
                return f"data:image/jpeg;base64,{base64.b64encode(shrunk).decode()}"
        except Exception:
            pass
        return ref
    if "/api/media/assets/by-key/" in ref:
        try:
            key = ref.split("/api/media/assets/by-key/", 1)[1].split("?")[0]
            qs = parse_qs(urlparse(ref).query)
            bucket = qs.get("bucket", [None])[0]
            backend = get_storage_backend_for_bucket(bucket)
            raw = backend.get(key)
            if raw:
                shrunk = _downscale_image_bytes(raw)
                mime = "image/jpeg" if shrunk is not raw else (mimetypes.guess_type(key)[0] or "image/png")
                return f"data:{mime};base64,{base64.b64encode(shrunk).decode()}"
        except Exception as exc:  # pragma: no cover - network/storage edge cases
            logger.warning("Failed to inline by-key reference %s: %s", ref, exc)
    return None
