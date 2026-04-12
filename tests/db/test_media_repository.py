from __future__ import annotations

import asyncio
from pathlib import Path

from api.common.enums import MediaUploadStatus
from api.db.database import create_all_tables, create_database_engine, create_session_factory
from api.db.media_db import SqlAlchemyMediaRepository
from api.models.media_model import Media


def test_sqlalchemy_media_repository_persists_media_records(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'media.db'}"
    engine = create_database_engine(database_url)
    create_all_tables(engine)
    repository = SqlAlchemyMediaRepository(create_session_factory(engine))

    media = Media(
        id="med_123",
        user_id="demo-user",
        filename="coffee-shop.png",
        content_type="image/png",
        file_size=128,
        storage_key="media/demo-user/2026/04/01/med_123-coffee-shop.png",
        upload_status=MediaUploadStatus.uploaded,
    )

    asyncio.run(repository.save_media(media))

    loaded = asyncio.run(repository.get_media("med_123"))

    assert loaded.id == "med_123"
    assert loaded.storage_key == media.storage_key
    assert loaded.upload_status == MediaUploadStatus.uploaded
