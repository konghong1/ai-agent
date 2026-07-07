"""
MinIO / S3 Bucket Lifecycle (ILM) management.

Applies automatic expiry rules so generated media never grows unbounded:

    videos/      -> expire after 30 days   (large, transient by nature)
    images/      -> expire after 180 days  (kept longer for reuse in chat)
    avatars/     -> expire after 365 days  (long-lived user assets)
    thumbnails/  -> expire after 30 days
    temp/        -> expire after 7 days

Run directly (idempotent, safe to call on every API start):
    python -m app.storage.ilm
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Object-key prefix -> expiration in days.
DEFAULT_RULES: dict[str, int] = {
    "videos/": 30,
    "images/": 180,
    "avatars/": 365,
    "thumbnails/": 30,
    "temp/": 7,
}


def build_lifecycle_config(rules: dict[str, int]) -> dict[str, Any]:
    """Build an S3 LifecycleConfiguration document from {prefix: days}."""
    return {
        "Rules": [
            {
                "ID": f"expire-{prefix.strip('/') or 'root'}",
                "Status": "Enabled",
                "Filter": {"Prefix": prefix},
                "Expiration": {"Days": days},
            }
            for prefix, days in rules.items()
        ]
    }


def apply_minio_lifecycle(
    bucket: str | None = None,
    endpoint: str | None = None,
    access_key: str | None = None,
    secret_key: str | None = None,
    use_ssl: bool | None = None,
    rules: dict[str, int] | None = None,
) -> bool:
    """Apply the lifecycle configuration to the bucket.

    Returns True on success, False if MinIO is unreachable (so callers can
    treat it as best-effort and never block API startup).
    """
    bucket = bucket or os.getenv("MINIO_BUCKET", "ai-agent-minio")
    endpoint = endpoint or os.getenv("MINIO_ENDPOINT", "localhost:9000")
    access_key = access_key or os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    secret_key = secret_key or os.getenv("MINIO_SECRET_KEY", "minioadmin")
    if use_ssl is None:
        use_ssl = os.getenv("MINIO_USE_SSL", "false").lower() == "true"
    rules = rules or DEFAULT_RULES

    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        logger.warning("boto3 not installed — skipping MinIO lifecycle setup.")
        return False

    try:
        client = boto3.client(
            "s3",
            endpoint_url=f"{'https' if use_ssl else 'http'}://{endpoint}",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
            region_name="",
        )
        # Ensure the bucket exists before setting lifecycle.
        try:
            client.head_bucket(Bucket=bucket)
        except Exception:
            client.create_bucket(Bucket=bucket)

        config = build_lifecycle_config(rules)
        client.put_bucket_lifecycle_configuration(
            Bucket=bucket, LifecycleConfiguration=config
        )
        logger.info(
            "Applied MinIO lifecycle to bucket '%s' (%d rules)", bucket, len(rules)
        )
        return True
    except Exception as exc:  # pragma: no cover - network dependent
        logger.warning("Failed to apply MinIO lifecycle (bucket=%s): %s", bucket, exc)
        return False


if __name__ == "__main__":
    ok = apply_minio_lifecycle()
    print("MinIO lifecycle applied:" , ok)
