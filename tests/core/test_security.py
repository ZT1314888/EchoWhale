"""sign_value / verify_signed_value 单测：访客 Cookie 签名化的核心契约。

伪造、篡改、截断、错误密钥一律返回 None（fail-closed 重新签发），
任何情况下都不能让未通过验签的原文溜出去。
"""

from __future__ import annotations

import pytest

from api.core.security import sign_value, verify_signed_value

SECRET = "unit-test-secret"
OTHER_SECRET = "another-secret"


def test_sign_value_appends_hex_signature() -> None:
    signed = sign_value("visitor_abc", secret=SECRET)

    assert signed.startswith("visitor_abc.")
    signature = signed.removeprefix("visitor_abc.")
    # SHA-256 十六进制摘要固定 64 位。
    assert len(signature) == 64
    assert all(character in "0123456789abcdef" for character in signature)


def test_verify_signed_value_round_trips_original_value() -> None:
    signed = sign_value("visitor_abc", secret=SECRET)

    assert verify_signed_value(signed, secret=SECRET) == "visitor_abc"


def test_verify_signed_value_rejects_tampered_value() -> None:
    signed = sign_value("visitor_abc", secret=SECRET)
    tampered = signed.replace("visitor_abc", "visitor_hack", 1)

    assert verify_signed_value(tampered, secret=SECRET) is None


def test_verify_signed_value_rejects_wrong_secret() -> None:
    signed = sign_value("visitor_abc", secret=SECRET)

    assert verify_signed_value(signed, secret=OTHER_SECRET) is None


def test_verify_signed_value_rejects_truncated_signature() -> None:
    signed = sign_value("visitor_abc", secret=SECRET)
    truncated = signed[: -8]

    assert verify_signed_value(truncated, secret=SECRET) is None


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "no_signature_at_all",
        ".only_signature",
        "only_value.",
    ],
)
def test_verify_signed_value_rejects_malformed_input(raw: str | None) -> None:
    assert verify_signed_value(raw, secret=SECRET) is None


def test_verify_signed_value_supports_dots_inside_value() -> None:
    # 按最后一个 "." 拆分：value 原文包含 "." 不影响验签。
    value = "visitor_with.dots"
    signed = sign_value(value, secret=SECRET)

    assert verify_signed_value(signed, secret=SECRET) == value
