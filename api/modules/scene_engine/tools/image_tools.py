from pathlib import Path


def infer_tags_from_filename(filename: str) -> list[str]:
    """从文件名提取少量弱提示标签，避免对模型造成过强引导。"""
    stem = Path(filename).stem.lower()
    tokens = [token for token in stem.replace("-", "_").split("_") if token]
    return tokens[:4]
