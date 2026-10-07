from __future__ import annotations

import asyncio
import os
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

from api.common.enums import MediaUploadStatus
from api.db.database import create_all_tables, create_session_factory
from api.db.media_db import SqlAlchemyMediaRepository
from api.integrations.storage.r2 import R2StorageService
from api.services.media_service import MediaService
from tests.support.engine import build_dialect_sync_engine

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
    engine = build_dialect_sync_engine(tmp_path, "r2-media")
    create_all_tables(engine)
    repository = SqlAlchemyMediaRepository(create_session_factory(engine))
    storage = R2StorageService()
    service = MediaService(storage=storage, repository=repository)

    # 真实磁盘文件走 upload_fileobj：对齐生产链路（磁盘 spool → boto3 直传）。
    upload_file = tmp_path / "r2-smoke.png"
    upload_file.write_bytes(PNG_BYTES)

    with upload_file.open("rb") as fileobj:
        media = asyncio.run(
            service.upload_media(
                user_id="demo-user",
                filename="r2-smoke.png",
                content_type="image/png",
                fileobj=fileobj,
            )
        )
    access = asyncio.run(service.create_media_access_url(media.id))

    try:
        assert media.upload_status == MediaUploadStatus.uploaded
        assert media.file_size == len(PNG_BYTES)
        request = Request(access.read_url, method="GET")
        with urlopen(request, timeout=15) as response:
            assert response.status == 200
            assert response.read() == PNG_BYTES
    finally:
        storage.delete_object(media.storage_key)
