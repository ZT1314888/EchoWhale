from pathlib import Path
from uuid import uuid4

from api.core.config import settings


class R2StorageService:
    def generate_public_url(self, filename: str) -> str:
        safe_name = Path(filename).name
        return f"{settings.r2_public_base_url.rstrip('/')}/{uuid4().hex}-{safe_name}"
