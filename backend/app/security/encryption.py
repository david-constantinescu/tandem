"""Symmetric encryption for sensitive data at rest (OAuth tokens, document text, stored files).

Uses Fernet (AES-128-CBC + HMAC-SHA256). The key comes from ENCRYPTION_KEY; in
development it is derived from SECRET_KEY so the app runs without extra setup.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from flask import current_app
from sqlalchemy import LargeBinary, Text
from sqlalchemy.types import TypeDecorator


def _derive_dev_key(secret: str) -> bytes:
    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"tandem-dev-encryption", info=b"fernet")
    return base64.urlsafe_b64encode(hkdf.derive(secret.encode()))


@lru_cache(maxsize=8)
def _fernet_for(encryption_key: str, secret_key: str) -> MultiFernet:
    keys = [k.strip() for k in encryption_key.split(",") if k.strip()] if encryption_key else []
    fernets = [Fernet(k.encode()) for k in keys] or [Fernet(_derive_dev_key(secret_key))]
    return MultiFernet(fernets)


def fernet() -> MultiFernet:
    cfg = current_app.config
    return _fernet_for(cfg.get("ENCRYPTION_KEY", ""), cfg["SECRET_KEY"])


def encrypt_bytes(data: bytes) -> bytes:
    return fernet().encrypt(data)


def decrypt_bytes(token: bytes) -> bytes:
    return fernet().decrypt(token)


def encrypt_str(value: str) -> str:
    return encrypt_bytes(value.encode()).decode()


def decrypt_str(token: str) -> str:
    return decrypt_bytes(token.encode()).decode()


def generate_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """Stable keyed hash for looking up opaque tokens (session ids) without storing them."""
    key = current_app.config["SECRET_KEY"].encode()
    return hmac.new(key, token.encode(), hashlib.sha256).hexdigest()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class EncryptedText(TypeDecorator):
    """Text column transparently encrypted with Fernet."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return encrypt_str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            return decrypt_str(value)
        except InvalidToken:
            return None


class EncryptedJSON(TypeDecorator):
    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return encrypt_bytes(json.dumps(value).encode())

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            return json.loads(decrypt_bytes(bytes(value)))
        except InvalidToken:
            return None
