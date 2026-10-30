"""Private object storage. Files are never served from a public URL; downloads go through
an authenticated endpoint. Local storage encrypts each object with the app's Fernet key."""
from __future__ import annotations

import os
from pathlib import Path

from flask import current_app

from app.security.encryption import decrypt_bytes, encrypt_bytes


class StorageBackend:
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...


class LocalStorage(StorageBackend):
    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("Invalid storage key")
        return path

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(encrypt_bytes(data))
        os.replace(tmp, path)

    def get(self, key: str) -> bytes:
        return decrypt_bytes(self._path(key).read_bytes())

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink()
        except FileNotFoundError:
            pass

    def exists(self, key: str) -> bool:
        return self._path(key).exists()


class S3Storage(StorageBackend):
    """S3-compatible storage (AWS S3, MinIO, R2). Objects are written with server-side encryption
    and additionally encrypted client-side with the app key."""

    def __init__(self, cfg):
        import boto3

        self.bucket = cfg["STORAGE_BUCKET"]
        self.client = boto3.client(
            "s3",
            endpoint_url=cfg.get("STORAGE_ENDPOINT") or None,
            aws_access_key_id=cfg.get("STORAGE_ACCESS_KEY") or None,
            aws_secret_access_key=cfg.get("STORAGE_SECRET_KEY") or None,
            region_name=cfg.get("STORAGE_REGION") or None,
        )

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=encrypt_bytes(data),
                               ContentType="application/octet-stream", ServerSideEncryption="AES256")

    def get(self, key: str) -> bytes:
        obj = self.client.get_object(Bucket=self.bucket, Key=key)
        return decrypt_bytes(obj["Body"].read())

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:  # noqa: BLE001 - botocore raises ClientError for 404
            return False


_backend: StorageBackend | None = None


def storage() -> StorageBackend:
    global _backend
    cfg = current_app.config
    if _backend is None or getattr(_backend, "_cfg_id", None) != id(cfg):
        if cfg["STORAGE_TYPE"] == "s3":
            _backend = S3Storage(cfg)
        else:
            _backend = LocalStorage(cfg["STORAGE_LOCAL_PATH"])
        _backend._cfg_id = id(cfg)  # type: ignore[attr-defined]
    return _backend
