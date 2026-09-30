from __future__ import annotations

import json

import pytest

from api.integrations.llm.json_utils import parse_llm_json


def test_parses_plain_json() -> None:
    assert parse_llm_json('{"a": 1}') == {"a": 1}


def test_parses_fenced_json_block() -> None:
    raw = "```json\n" + json.dumps({"grammar": "ok", "more_natural": "fine"}) + "\n```"
    assert parse_llm_json(raw) == {"grammar": "ok", "more_natural": "fine"}


def test_parses_fenced_json_without_language_tag() -> None:
    raw = "```\n{\"a\": [1, 2]}\n```"
    assert parse_llm_json(raw) == {"a": [1, 2]}


def test_keeps_backticks_inside_json_strings() -> None:
    # 旧的 strip("`") 会把 JSON 字符串里的反引号也剥掉，这里是回归保护。
    raw = '```json\n{"quote": "uses `backticks` inside"}\n```'
    assert parse_llm_json(raw) == {"quote": "uses `backticks` inside"}


def test_parses_single_line_fenced_json() -> None:
    assert parse_llm_json('```json {"a": 1} ```') == {"a": 1}


def test_invalid_json_raises_json_decode_error() -> None:
    with pytest.raises(json.JSONDecodeError):
        parse_llm_json("```json\nnot-json\n```")
