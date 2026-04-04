from __future__ import annotations

import os
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

from api.common.enums import MediaUploadStatus
from api.db.database import create_all_tables, create_database_engine, create_session_factory
from api.db.media_db import SqlAlchemyMediaRepository
from api.integrations.storage.r2 import R2StorageService
from api.services.media_service import MediaService


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde"
    b"\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\x0f\x00\x01\x01\x01\x00"
    b"\x18\xdd\x8d\xb1"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_R2_INTEGRATION") != "1",
    reason="Set RUN_R2_INTEGRATION=1 to run against real Cloudflare R2.",
)


def test_uploads_media_to_real_r2_and_serves_signed_access_url(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'r2-media.db'}"
    engine = create_database_engine(database_url)
    create_all_tables(engine)
    repository = SqlAlchemyMediaRepository(create_session_factory(engine))
    storage = R2StorageService()
    service = MediaService(storage=storage, repository=repository)

    media = service.upload_media(
        user_id="demo-user",
        filename="r2-smoke.png",
        content_type="image/png",
        content=PNG_BYTES,
    )
    access = service.create_media_access_url(media.id)

    try:
        assert media.upload_status == MediaUploadStatus.uploaded
        request = Request(access.read_url, method="GET")
        with urlopen(request, timeout=15) as response:  # noqa: S310
            assert response.status == 200
            assert response.read() == PNG_BYTES
    finally:
        storage.delete_object(media.storage_key)
