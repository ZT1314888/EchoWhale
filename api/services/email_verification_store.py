from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from threading import Lock
from time import time
from typing import Protocol
from zoneinfo import ZoneInfo

from api.common.exceptions import ConfigurationError, TooManyRequestsError, ValidationError
from api.core.config import settings

try:  # pragma: no cover - exercised through factory fallback
    from redis import Redis
except ImportError:  # pragma: no cover - local dev may not have redis extras installed yet
    Redis = None


RATE_LIMIT_MESSAGE = "请求过于频繁"
INVALID_CODE_MESSAGE = "Verification code is invalid or expired"
_SHANGHAI = ZoneInfo("Asia/Shanghai")


class EmailVerificationStore(Protocol):
    def issue_code(self, *, email: str, ip_address: str) -> str: ...

    def consume_code(self, *, email: str, code: str) -> None: ...


@dataclass(slots=True)
class _StoredCode:
    code_hash: str
    remaining_attempts: int
    created_at: str


class InMemoryEmailVerificationStore:
    def __init__(
        self,
        *,
        code_ttl_seconds: int | None = None,
        cooldown_seconds: int | None = None,
        daily_limit: int | None = None,
        max_attempts: int | None = None,
        now_fn=time,
    ) -> None:
        self._code_ttl_seconds = code_ttl_seconds or settings.auth_email_code_ttl_seconds
        self._cooldown_seconds = cooldown_seconds or settings.auth_email_send_cooldown_seconds
        self._daily_limit = daily_limit or settings.auth_email_send_daily_limit
        self._max_attempts = max_attempts or settings.auth_email_verify_max_attempts
        self._now_fn = now_fn
        self._lock = Lock()
        self._codes: dict[str, tuple[_StoredCode, float]] = {}
        self._cooldowns: dict[str, float] = {}
        self._daily_counts: dict[str, tuple[int, float]] = {}

    def issue_code(self, *, email: str, ip_address: str) -> str:
        now = self._now_fn()
        with self._lock:
            self._prune(now)
            self._ensure_within_limits(
                email=email,
                ip_address=ip_address,
                now=now,
            )
            code = _generate_code()
            self._codes[email] = (
                _StoredCode(
                    code_hash=_hash_code(code),
                    remaining_attempts=self._max_attempts,
                    created_at=datetime.now(_SHANGHAI).isoformat(),
                ),
                now + self._code_ttl_seconds,
            )
            self._cooldowns[_cooldown_key("email", email)] = now + self._cooldown_seconds
            self._cooldowns[_cooldown_key("ip", ip_address)] = now + self._cooldown_seconds
            self._increment_daily_count(_daily_key("email", email, now), now)
            self._increment_daily_count(_daily_key("ip", ip_address, now), now)
            return code

    def consume_code(self, *, email: str, code: str) -> None:
        now = self._now_fn()
        with self._lock:
            self._prune(now)
            stored = self._codes.get(email)
            if stored is None:
                raise ValidationError(INVALID_CODE_MESSAGE)

            payload, expires_at = stored
            if expires_at <= now:
                self._codes.pop(email, None)
                raise ValidationError(INVALID_CODE_MESSAGE)

            if hmac.compare_digest(payload.code_hash, _hash_code(code)):
                self._codes.pop(email, None)
                return

            remaining_attempts = payload.remaining_attempts - 1
            if remaining_attempts <= 0:
                self._codes.pop(email, None)
            else:
                self._codes[email] = (
                    _StoredCode(
                        code_hash=payload.code_hash,
                        remaining_attempts=remaining_attempts,
                        created_at=payload.created_at,
                    ),
                    expires_at,
                )
            raise ValidationError(INVALID_CODE_MESSAGE)

    def _ensure_within_limits(self, *, email: str, ip_address: str, now: float) -> None:
        for key in (
            _cooldown_key("email", email),
            _cooldown_key("ip", ip_address),
        ):
            if key in self._cooldowns:
                raise TooManyRequestsError(RATE_LIMIT_MESSAGE)
        for key in (
            _daily_key("email", email, now),
            _daily_key("ip", ip_address, now),
        ):
            count, _ = self._daily_counts.get(key, (0, 0.0))
            if count >= self._daily_limit:
                raise TooManyRequestsError(RATE_LIMIT_MESSAGE)

    def _increment_daily_count(self, key: str, now: float) -> None:
        count, expires_at = self._daily_counts.get(key, (0, now + _seconds_until_next_shanghai_midnight(now)))
        self._daily_counts[key] = (count + 1, expires_at)

    def _prune(self, now: float) -> None:
        self._codes = {
            email: record
            for email, record in self._codes.items()
            if record[1] > now
        }
        self._cooldowns = {
            key: expires_at
            for key, expires_at in self._cooldowns.items()
            if expires_at > now
        }
        self._daily_counts = {
            key: record
            for key, record in self._daily_counts.items()
            if record[1] > now
        }


class RedisEmailVerificationStore:
    def __init__(
        self,
        client: Redis,
        *,
        code_ttl_seconds: int | None = None,
        cooldown_seconds: int | None = None,
        daily_limit: int | None = None,
        max_attempts: int | None = None,
    ) -> None:
        self._client = client
        self._code_ttl_seconds = code_ttl_seconds or settings.auth_email_code_ttl_seconds
        self._cooldown_seconds = cooldown_seconds or settings.auth_email_send_cooldown_seconds
        self._daily_limit = daily_limit or settings.auth_email_send_daily_limit
        self._max_attempts = max_attempts or settings.auth_email_verify_max_attempts

    def issue_code(self, *, email: str, ip_address: str) -> str:
        self._ensure_within_limits(email=email, ip_address=ip_address)
        code = _generate_code()
        code_key = _redis_code_key(email)
        email_cooldown_key = _redis_cooldown_key("email", email)
        ip_cooldown_key = _redis_cooldown_key("ip", ip_address)
        email_daily_key = _redis_daily_key("email", email, time())
        ip_daily_key = _redis_daily_key("ip", ip_address, time())
        daily_ttl_seconds = _seconds_until_next_shanghai_midnight(time())

        # 发送成功前先占位频控，避免 SMTP 调用前被绕过。
        if not self._client.set(email_cooldown_key, "1", ex=self._cooldown_seconds, nx=True):
            raise TooManyRequestsError(RATE_LIMIT_MESSAGE)
        if not self._client.set(ip_cooldown_key, "1", ex=self._cooldown_seconds, nx=True):
            self._client.delete(email_cooldown_key)
            raise TooManyRequestsError(RATE_LIMIT_MESSAGE)

        current_email_daily = int(self._client.get(email_daily_key) or 0)
        current_ip_daily = int(self._client.get(ip_daily_key) or 0)
        if current_email_daily >= self._daily_limit or current_ip_daily >= self._daily_limit:
            self._client.delete(email_cooldown_key, ip_cooldown_key)
            raise TooManyRequestsError(RATE_LIMIT_MESSAGE)

        payload = json.dumps(
            {
                "code_hash": _hash_code(code),
                "remaining_attempts": self._max_attempts,
                "created_at": datetime.now(_SHANGHAI).isoformat(),
            }
        )
        pipe = self._client.pipeline()
        pipe.set(code_key, payload, ex=self._code_ttl_seconds)
        pipe.incr(email_daily_key)
        pipe.expire(email_daily_key, daily_ttl_seconds)
        pipe.incr(ip_daily_key)
        pipe.expire(ip_daily_key, daily_ttl_seconds)
        pipe.execute()
        return code

    def consume_code(self, *, email: str, code: str) -> None:
        code_key = _redis_code_key(email)
        raw_payload = self._client.get(code_key)
        if raw_payload is None:
            raise ValidationError(INVALID_CODE_MESSAGE)

        payload = _StoredCode(**json.loads(raw_payload))
        if hmac.compare_digest(payload.code_hash, _hash_code(code)):
            self._client.delete(code_key)
            return

        ttl_seconds = self._client.ttl(code_key)
        remaining_attempts = payload.remaining_attempts - 1
        if ttl_seconds <= 0 or remaining_attempts <= 0:
            self._client.delete(code_key)
        else:
            self._client.set(
                code_key,
                json.dumps(
                    {
                        "code_hash": payload.code_hash,
                        "remaining_attempts": remaining_attempts,
                        "created_at": payload.created_at,
                    }
                ),
                ex=ttl_seconds,
            )
        raise ValidationError(INVALID_CODE_MESSAGE)

    def _ensure_within_limits(self, *, email: str, ip_address: str) -> None:
        keys = [
            _redis_cooldown_key("email", email),
            _redis_cooldown_key("ip", ip_address),
            _redis_daily_key("email", email, time()),
            _redis_daily_key("ip", ip_address, time()),
        ]
        email_cooldown, ip_cooldown, email_daily, ip_daily = self._client.mget(keys)
        if email_cooldown or ip_cooldown:
            raise TooManyRequestsError(RATE_LIMIT_MESSAGE)
        if int(email_daily or 0) >= self._daily_limit or int(ip_daily or 0) >= self._daily_limit:
            raise TooManyRequestsError(RATE_LIMIT_MESSAGE)


@lru_cache
def get_email_verification_store() -> EmailVerificationStore:
    if not settings.redis_url.strip():
        return InMemoryEmailVerificationStore()
    if Redis is None:
        raise ConfigurationError("REDIS_URL is configured but redis dependency is not installed")
    return RedisEmailVerificationStore(Redis.from_url(settings.redis_url, decode_responses=True))


def _redis_code_key(email: str) -> str:
    return f"auth:verify_code:{email}"


def _redis_cooldown_key(scope: str, value: str) -> str:
    return f"auth:verify_send:cooldown:{scope}:{value}"


def _redis_daily_key(scope: str, value: str, now_ts: float) -> str:
    now = datetime.fromtimestamp(now_ts, tz=_SHANGHAI)
    return f"auth:verify_send:daily:{scope}:{value}:{now.strftime('%Y%m%d')}"


def _cooldown_key(scope: str, value: str) -> str:
    return f"{scope}:{value}"


def _daily_key(scope: str, value: str, now_ts: float) -> str:
    now = datetime.fromtimestamp(now_ts, tz=_SHANGHAI)
    return f"{scope}:{value}:{now.strftime('%Y%m%d')}"


def _seconds_until_next_shanghai_midnight(now_ts: float) -> int:
    now = datetime.fromtimestamp(now_ts, tz=_SHANGHAI)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(int((tomorrow - now).total_seconds()), 1)


def _generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _hash_code(code: str) -> str:
    return hmac.new(
        settings.auth_jwt_secret.encode("utf-8"),
        code.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
