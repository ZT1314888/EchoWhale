def normalize_sentence(text: str) -> str:
    text = text.strip()
    if not text:
        return "I need a little more detail."
    return text[0].upper() + text[1:]
