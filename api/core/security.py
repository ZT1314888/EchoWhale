from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
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
    now = datetime.now(UTC)
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


def create_service_token(
    *,
    subject: str,
    token_type: str,
    secret: str,
    expires_in_seconds: int,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "typ": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in_seconds)).timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return _encode_jwt(payload, secret)


def decode_service_token(
    token: str,
    *,
    secret: str,
    expected_type: str,
) -> dict[str, Any]:
    payload = _decode_jwt(token, secret)
    if payload.get("typ") != expected_type:
        raise AuthenticationError("Authentication required")
    return payload


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(refresh_token: str) -> str:
    return hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()


def generate_action_token() -> str:
    return secrets.token_urlsafe(48)


def hash_action_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_visitor_id() -> str:
    return f"visitor_{secrets.token_urlsafe(16)}"


def sign_value(value: str, *, secret: str) -> str:
    """给任意字符串值追加 HMAC-SHA256 签名，返回 "<value>.<十六进制签名>"。

    匿名访客 Cookie 采用此格式：签名覆盖原文且密钥不出网，
    服务端即可认证 Cookie 确由本服务签发，客户端无法伪造任意
    visitor_id 去撑爆限流键或超长打爆存储列。

    session_engine/agent.py 的历史分页 cursor 签名（_sign_cursor_payload）
    与本函数同构，本次不迁移以控制 diff 扩散，后续可统一收敛到这里。
    """
    signature = hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{value}.{signature}"


def verify_signed_value(signed: str | None, *, secret: str) -> str | None:
    """验签 "<value>.<签名>"，返回原始 value；任何失败一律返回 None。

    失败必须静默而非抛错：伪造/畸形/旧版未签名 Cookie 的正确处置是
    当作"没有访客身份"重新签发（fail-closed），绝不能把原始值交给调用方。
    按最后一个 "." 拆分，value 原文里即使出现 "." 也不影响验签。
    """
    if not signed:
        return None
    value, separator, signature = signed.rpartition(".")
    if not separator or not value or not signature:
        return None
    expected = hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()
    # 恒时比较，避免逐字节泄露签名信息。
    if not hmac.compare_digest(signature, expected):
        return None
    return value


def _encode_jwt(payload: dict[str, Any], secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    encoded_header = _base64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    encoded_payload = _base64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{encoded_header}.{encoded_payload}".encode()
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{encoded_header}.{encoded_payload}.{_base64url_encode(signature)}"


def _decode_jwt(token: str, secret: str) -> dict[str, Any]:
    try:
        encoded_header, encoded_payload, encoded_signature = token.split(".", maxsplit=2)
    except ValueError as error:
        raise AuthenticationError("Authentication required") from error

    signing_input = f"{encoded_header}.{encoded_payload}".encode()
    expected_signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    actual_signature = _base64url_decode(encoded_signature)
    if not hmac.compare_digest(expected_signature, actual_signature):
        raise AuthenticationError("Authentication required")

    payload = json.loads(_base64url_decode(encoded_payload))
    if int(payload.get("exp", 0)) <= int(datetime.now(UTC).timestamp()):
        raise AuthenticationError("Authentication required")
    return payload


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("utf-8")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode())
