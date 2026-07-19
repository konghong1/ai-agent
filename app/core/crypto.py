"""用户密钥信封加密：基于 settings.secret_key 派生的 Fernet 密钥。

- 明文 → 密文落库；读取时解密。
- 空值/None 直接返回空串，避免存储/泄露无意义密文。
- 用于 McpServer.api_key / headers、Hook.secret_env 等敏感字段。
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging

from cryptography.fernet import Fernet

from app.settings import get_settings

logger = logging.getLogger(__name__)


def _fernet() -> Fernet:
    settings = get_settings()
    raw = (settings.secret_key or "change-me-in-production").encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    token = base64.urlsafe_b64encode(digest)
    return Fernet(token)


def encrypt_secret(plain: str | None) -> str:
    if plain is None or plain == "":
        return ""
    try:
        return _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")
    except Exception as e:  # pragma: no cover - 加密失败兜底
        logger.error("encrypt_secret failed: %s", e)
        return ""


def decrypt_secret(token: str | None) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except Exception:
        # 密钥不匹配/数据损坏：返回空而非明文，避免泄露
        return ""


def encrypt_json(obj) -> str:
    if obj is None or obj == {}:
        return ""
    try:
        return encrypt_secret(json.dumps(obj, ensure_ascii=False))
    except Exception:
        return ""


def decrypt_json(token: str | None) -> dict:
    s = decrypt_secret(token)
    if not s:
        return {}
    try:
        return json.loads(s)
    except Exception:
        return {}
