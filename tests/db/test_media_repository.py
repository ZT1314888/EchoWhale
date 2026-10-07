from __future__ import annotations

import pytest

from api.common.enums import MediaUploadStatus
from api.db.database import create_all_tables_async, create_async_session_factory
from api.db.media_db import SqlAlchemyMediaRepository
from api.models.media_model import Media


@pytest.mark.anyio
async def test_sqlalchemy_media_repository_persists_media_records(dialect_async_engine) -> None:
    engine = dialect_async_engine
    await create_all_tables_async(engine)
    repository = SqlAlchemyMediaRepository(create_async_session_factory(engine))

    media = Media(
        id="med_123",
        user_id="demo-user",
        filename="coffee-shop.png",
        content_type="image/png",
        file_size=128,
        storage_key="media/demo-user/2026/04/01/med_123-coffee-shop.png",
        upload_status=MediaUploadStatus.uploaded,
    )

    await repository.save_media(media)

    loaded = await repository.get_media("med_123")

    assert loaded.id == "med_123"
    assert loaded.storage_key == media.storage_key
    assert loaded.upload_status == MediaUploadStatus.uploaded
