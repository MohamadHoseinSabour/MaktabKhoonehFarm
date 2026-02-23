import base64
import hashlib

from cryptography.fernet import Fernet

from app.core.config import settings


def _build_fernet() -> Fernet:
    digest = hashlib.sha256(settings.secret_key.encode('utf-8')).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    f = _build_fernet()
    return f.encrypt(value.encode('utf-8')).decode('utf-8')


def decrypt_secret(value: str) -> str:
    f = _build_fernet()
    return f.decrypt(value.encode('utf-8')).decode('utf-8')