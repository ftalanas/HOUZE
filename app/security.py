from __future__ import annotations
import os
from itsdangerous import URLSafeSerializer, BadSignature
from passlib.hash import argon2
from typing import Any, Optional

SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret-change-me")
SESSION_SECURE = os.getenv("SESSION_SECURE", "false").lower() == "true"
SESSION_SECURE = False  # in produzione: True (HTTPS)

serializer = URLSafeSerializer(SESSION_SECRET, salt="session")


def hash_password(raw: str) -> str:
    return argon2.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return argon2.verify(raw, hashed)
    except Exception:
        return False


def encode_session(payload: dict[str, Any]) -> str:
    return serializer.dumps(payload)


def decode_session(token: str) -> Optional[dict[str, Any]]:
    try:
        return serializer.loads(token)
    except BadSignature:
        return None
