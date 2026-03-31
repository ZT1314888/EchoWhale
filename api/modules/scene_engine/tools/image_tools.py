from pathlib import Path


def infer_tags_from_filename(filename: str) -> list[str]:
    stem = Path(filename).stem.lower()
    tokens = [token for token in stem.replace("-", "_").split("_") if token]
    return tokens[:4]
