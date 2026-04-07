from __future__ import annotations


LOW_VALUE_VOCAB = {"table", "chair", "furniture", "room"}

ANCHOR_SYNONYMS: dict[str, set[str]] = {
    "glass wall": {"glass wall", "glass partition", "glass walls"},
    "counter": {"counter", "service counter"},
    "menu board": {"menu board", "menu", "menu stand"},
    "platform sign": {"platform sign", "platform"},
    "dining table": {"dining table", "table"},
}

SCENE_VOCAB_EXPECTATIONS: dict[str, set[str]] = {
    "coffee_shop": {"latte", "order", "size", "barista", "drink"},
    "office": {"meeting", "reception", "visitor", "deadline", "update"},
    "restaurant": {"order", "dish", "recommendation", "menu", "server"},
    "travel": {"ticket", "platform", "direction", "train", "guide"},
}


def match_expected_keywords(expected_keywords: list[str], actual_values: list[str]) -> bool:
    if not expected_keywords:
        return True

    normalized_actual = {value.lower() for value in actual_values}
    for keyword in expected_keywords:
        accepted = ANCHOR_SYNONYMS.get(keyword.lower(), {keyword.lower()})
        if not (accepted & normalized_actual):
            return False
    return True


def vocab_candidates_are_valuable(scene: str, vocab_candidates: list[str]) -> bool:
    normalized = {value.lower() for value in vocab_candidates}
    if not normalized:
        return False
    if normalized & LOW_VALUE_VOCAB:
        return False

    expected = SCENE_VOCAB_EXPECTATIONS.get(scene, set())
    return bool(expected & normalized) if expected else True
