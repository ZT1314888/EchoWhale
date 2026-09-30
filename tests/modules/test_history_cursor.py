from __future__ import annotations

from datetime import datetime, timezone

import pytest

from api.common.exceptions import ValidationError as AppValidationError
from api.modules.session_engine.agent import _decode_history_cursor, _encode_history_cursor


def test_history_cursor_round_trip() -> None:
    value = (datetime(2026, 4, 4, 12, 0, tzinfo=timezone.utc), "sess_123")

    encoded = _encode_history_cursor(value)
    decoded = _decode_history_cursor(encoded)

    assert decoded is not None
    decoded_at, decoded_session_id = decoded
    assert decoded_at == value[0]
    assert decoded_session_id == "sess_123"


def test_history_cursor_rejects_unsigned_legacy_cursor() -> None:
    with pytest.raises(AppValidationError):
        _decode_history_cursor("2026-04-04T12:00:00+00:00|sess_123")


def test_history_cursor_rejects_forged_signature() -> None:
    signed = _encode_history_cursor(
        (datetime(2026, 4, 4, 12, 0, tzinfo=timezone.utc), "sess_123")
    )
    forged = signed.replace("sess_123", "sess_999")

    with pytest.raises(AppValidationError):
        _decode_history_cursor(forged)


def test_history_cursor_rejects_garbage() -> None:
    with pytest.raises(AppValidationError):
        _decode_history_cursor("not-a-cursor")

    with pytest.raises(AppValidationError):
        _decode_history_cursor("bad-time|sess_123|deadbeef")


def test_history_cursor_none_passes_through() -> None:
    assert _decode_history_cursor(None) is None
