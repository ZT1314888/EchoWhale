"""MediaService 流式校验回归：超限即断、魔法字节头校验、seek(0) 交接。"""

from __future__ import annotations

import asyncio
import io
from datetime import UTC, datetime, timedelta
from typing import BinaryIO

import pytest

from api.common.exceptions import FileTooLargeError, NotFoundError, ValidationError
from api.models.media_model import Media
from api.services.media_service import UPLOAD_CHUNK_SIZE, MediaService

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde"
    b"\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\x0f\x00\x01\x01\x01\x00"
    b"\x18\xdd\x8d\xb1"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


class TrackingBytesIO(io.BytesIO):
    """记录累计读出字节数的 BytesIO：断言超限后服务确实停止消费剩余输入。"""

    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.bytes_served = 0

    def read(self, size: int = -1) -> bytes:
        chunk = super().read(size)
        self.bytes_served += len(chunk)
        return chunk


class FakeStorageService:
    """fileobj 契约替身：记录调用次数、调用时指针位置与实际收到的内容。"""

    def __init__(self) -> None:
        self.upload_calls = 0
        self.position_at_call: int | None = None
        self.uploaded: dict[str, bytes] = {}

    async def async_upload_fileobj(self, *, key: str, fileobj: BinaryIO, content_type: str) -> None:
        self.upload_calls += 1
        self.position_at_call = fileobj.tell()
        self.uploaded[key] = fileobj.read()

    async def async_create_signed_read_url(
        self, key: str, *, expires_in: int
    ) -> tuple[str, datetime]:
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        return (f"https://signed.test/{key}", expires_at)


class FakeMediaRepository:
    def __init__(self) -> None:
        self.media: dict[str, Media] = {}

    async def save_media(self, media: Media) -> Media:
        self.media[media.id] = media
        return media

    async def get_media(self, media_id: str) -> Media:
        if media_id not in self.media:
            raise NotFoundError(f"Media {media_id} not found")
        return self.media[media_id]


def make_service(
    storage: FakeStorageService,
    repository: FakeMediaRepository,
    *,
    max_file_size: int = 10 * 1024 * 1024,
) -> MediaService:
    return MediaService(
        storage=storage,
        repository=repository,
        max_file_size=max_file_size,
    )


def test_upload_over_limit_aborts_without_storage_call_and_stops_consuming() -> None:
    """超限立即中止：storage 零调用，剩余输入不再消费（读取停在超限块边界）。"""
    storage = FakeStorageService()
    repository = FakeMediaRepository()
    service = make_service(storage, repository, max_file_size=70_000)

    # ~128KB 合法 PNG：64KB 首块 + 64KB 次块后累计 131072 > 70000，应在次块中止。
    payload = b"\x89PNG\r\n\x1a\n" + b"a" * (2 * UPLOAD_CHUNK_SIZE)
    fileobj = TrackingBytesIO(payload)

    with pytest.raises(FileTooLargeError, match="70000"):
        asyncio.run(
            service.upload_media(
                user_id="user_1",
                filename="big.png",
                content_type="image/png",
                fileobj=fileobj,
            )
        )

    assert storage.upload_calls == 0, "超限后不得触达 storage"
    assert not repository.media, "超限后不得落库"
    # 读取停在第二个 chunk 结束点，尾部数据不再消费；
    # 超限路径不 seek(0)，指针位置即读取停止点。
    assert fileobj.bytes_served == 2 * UPLOAD_CHUNK_SIZE
    assert fileobj.tell() == 2 * UPLOAD_CHUNK_SIZE
    assert fileobj.tell() < len(payload)


@pytest.mark.parametrize(
    ("content_type", "payload"),
    [
        ("image/jpeg", b"\xff\xd8\xff\xe0" + b"jpeg-body" * 8),
        ("image/png", PNG_BYTES),
        ("image/webp", b"RIFF\x24\x08\x00\x00WEBPVP8 body"),
    ],
    ids=["jpeg", "png", "webp"],
)
def test_upload_valid_headers_pass_and_hand_full_file_to_storage(
    content_type: str, payload: bytes
) -> None:
    """三格式前 12 字节头校验通过；storage 收到的是 seek(0) 后的完整文件。"""
    storage = FakeStorageService()
    repository = FakeMediaRepository()
    service = make_service(storage, repository)

    fileobj = io.BytesIO(payload)
    result = asyncio.run(
        service.upload_media(
            user_id="user_1",
            filename="photo.img",
            content_type=content_type,
            fileobj=fileobj,
        )
    )

    assert storage.upload_calls == 1
    ((uploaded_key, uploaded_content),) = storage.uploaded.items()
    assert uploaded_content == payload, "storage 必须收到完整内容（seek(0) 已生效）"
    assert result.media.file_size == len(payload)
    assert result.media.content_type == content_type
    # user_id 未带 owner 前缀时原样进入存储路径（路由层传入的 owner_id 带 user:/visitor: 前缀）。
    assert uploaded_key.startswith("media/user_1/")
    # 成功路径：storage 被调用时指针已在文件开头（seek(0) 交接生效）。
    assert storage.position_at_call == 0


@pytest.mark.parametrize(
    ("content_type", "payload"),
    [
        ("image/jpeg", b"\x89PNG\r\n\x1a\n" + b"not really jpeg"),
        ("image/png", b"GIF89a-not-a-png!"),
        ("image/webp", b"RIFF\x24\x08\x00\x00WEBQbad fourcc"),
        ("image/png", b""),  # 空 body：头校验必然失败，与旧 bytes 路径语义一致
    ],
    ids=["png-bytes-as-jpeg", "gif-as-png", "bad-webp-fourcc", "empty-body"],
)
def test_upload_rejects_mismatched_magic_bytes_without_storage_call(
    content_type: str, payload: bytes
) -> None:
    storage = FakeStorageService()
    repository = FakeMediaRepository()
    service = make_service(storage, repository)

    with pytest.raises(ValidationError, match="Invalid image content"):
        asyncio.run(
            service.upload_media(
                user_id="user_1",
                filename="forged.img",
                content_type=content_type,
                fileobj=io.BytesIO(payload),
            )
        )

    assert storage.upload_calls == 0
    assert not repository.media
