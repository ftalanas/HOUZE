from __future__ import annotations
import os
from itsdangerous import URLSafeSerializer, BadSignature
from passlib.hash import argon2

SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret-change-me")
SESSION_SECURE = os.getenv("SESSION_SECURE", "false").lower() == "true"

serializer = URLSafeSerializer(SESSION_SECRET, salt="session")


def hash_password(pw: str):
    return argon2.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return argon2.verify(pw, hashed)
    except Exception:
        return False


def encode_session(data: dict) -> str:
    return serializer.dumps(data)


def decode_session(token: str) -> dict | None:
    try:
        return serializer.loads(token)
    except BadSignature:
        return None
