from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import struct
import time


def hash_password(password: str, salt: bytes | None = None) -> str:
    if len(password) < 12:
        raise ValueError("password must be at least 12 characters")
    salt = salt or os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(digest, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False


def new_token(size: int = 32) -> str:
    return secrets.token_urlsafe(size)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def normalize_totp_secret(secret: str) -> str:
    return "".join(secret.upper().split()).rstrip("=")


def totp_code(secret: str, at: int | None = None, step: int = 30) -> str:
    key = base64.b32decode(normalize_totp_secret(secret) + "=" * ((8 - len(normalize_totp_secret(secret)) % 8) % 8))
    counter = int((at if at is not None else time.time()) // step)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{number:06d}"


def verify_totp(secret: str, code: str, at: int | None = None) -> bool:
    if not secret:
        return True
    now = int(at if at is not None else time.time())
    return any(hmac.compare_digest(totp_code(secret, now + drift * 30), code.strip()) for drift in (-1, 0, 1))
