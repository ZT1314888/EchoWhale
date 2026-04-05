from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from api.common.exceptions import AuthenticationError


PASSWORD_HASH_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_HASH_ITERATIONS,
    )
    return (
        "pbkdf2_sha256"
        f"${PASSWORD_HASH_ITERATIONS}"
        f"${salt}"
        f"${base64.urlsafe_b64encode(digest).decode('utf-8')}"
    )


def verify_password(password: str, stored_hash: str) -> bool:
    algorithm, iterations, salt, encoded_hash = stored_hash.split("$", maxsplit=3)
    if algorithm != "pbkdf2_sha256":
        return False

    calculated = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        int(iterations),
    )
    expected = base64.urlsafe_b64decode(encoded_hash.encode("utf-8"))
    return secrets.compare_digest(calculated, expected)


def create_access_token(
    *,
    subject: str,
    secret: str,
    expires_in_seconds: int,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "typ": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in_seconds)).timestamp()),
    }
    return _encode_jwt(payload, secret)


def decode_access_token(token: str, *, secret: str) -> dict[str, Any]:
    payload = _decode_jwt(token, secret)
    if payload.get("typ") != "access":
        raise AuthenticationError("Authentication required")
    return payload


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(refresh_token: str) -> str:
    return hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()


def generate_visitor_id() -> str:
    return f"visitor_{secrets.token_urlsafe(16)}"


def _encode_jwt(payload: dict[str, Any], secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    encoded_header = _base64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    encoded_payload = _base64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{encoded_header}.{encoded_payload}".encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{encoded_header}.{encoded_payload}.{_base64url_encode(signature)}"


def _decode_jwt(token: str, secret: str) -> dict[str, Any]:
    try:
        encoded_header, encoded_payload, encoded_signature = token.split(".", maxsplit=2)
    except ValueError as error:
        raise AuthenticationError("Authentication required") from error

    signing_input = f"{encoded_header}.{encoded_payload}".encode("utf-8")
    expected_signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    actual_signature = _base64url_decode(encoded_signature)
    if not hmac.compare_digest(expected_signature, actual_signature):
        raise AuthenticationError("Authentication required")

    payload = json.loads(_base64url_decode(encoded_payload))
    if int(payload.get("exp", 0)) <= int(datetime.now(timezone.utc).timestamp()):
        raise AuthenticationError("Authentication required")
    return payload


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("utf-8")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("utf-8"))
