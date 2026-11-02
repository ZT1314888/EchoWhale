from __future__ import annotations

import json
import re
from typing import Any

_FENCED_LANG_TAG = re.compile(r"^[A-Za-z0-9_-]+\s")


def parse_llm_json(raw: str) -> dict[str, Any]:
    """解析模型返回的 JSON，兼容被 Markdown 代码围栏包裹的输出。

    只剥离围栏与可选语言标签，不改动 JSON 正文，
    避免误删字符串内出现的反引号。
    """
    normalized = raw.strip()
    if normalized.startswith("```"):
        normalized = _strip_code_fence(normalized)
    return json.loads(normalized)


def _strip_code_fence(text: str) -> str:
    body = text.strip()
    if body.startswith("```"):
        body = body[3:].lstrip()
        # 去掉行内语言标签（如 ```json），正文以 JSON 起始符开头时不受影响。
        if _FENCED_LANG_TAG.match(body):
            body = body.split(None, 1)[1] if len(body.split(None, 1)) > 1 else ""
    body = body.removesuffix("```")
    return body.strip()
