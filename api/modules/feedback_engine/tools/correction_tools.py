def normalize_sentence(text: str) -> str:
    """把学习者句子整理成最小可展示的英文句式。"""
    text = text.strip()
    if not text:
        return "I need a little more detail."
    return text[0].upper() + text[1:]
