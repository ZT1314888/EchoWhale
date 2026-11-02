from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from re import sub
from typing import BinaryIO, Protocol
from uuid import uuid4

from api.common.enums import MediaUploadStatus
from api.common.exceptions import (
    FileTooLargeError,
    NotFoundError,
    UnsupportedMediaTypeError,
    ValidationError,
)
from api.common.ownership import owner_to_storage_path
from api.db.media_db import MediaRepository
from api.models.media_model import Media, MediaAccessGrant, MediaUploadResult

# 分块读取的块大小：校验期间内存占用恒定（64KB），不随文件大小增长。
UPLOAD_CHUNK_SIZE = 64 * 1024


class StorageService(Protocol):
    async def async_upload_fileobj(
        self, *, key: str, fileobj: BinaryIO, content_type: str
    ) -> None: ...

    async def async_create_signed_read_url(
        self, key: str, *, expires_in: int
    ) -> tuple[str, datetime]: ...


class MediaService:
    def __init__(
        self,
        storage: StorageService,
        repository: MediaRepository,
        *,
        max_file_size: int = 10 * 1024 * 1024,
        signed_url_ttl_seconds: int = 900,
        allowed_content_types: tuple[str, ...] = (
            "image/jpeg",
            "image/png",
            "image/webp",
        ),
    ) -> None:
        self.storage = storage
        self.repository = repository
        self.max_file_size = max_file_size
        self.signed_url_ttl_seconds = signed_url_ttl_seconds
        self.allowed_content_types = set(allowed_content_types)

    async def upload_media(
        self,
        *,
        user_id: str,
        filename: str,
        content_type: str,
        fileobj: BinaryIO,
    ) -> MediaUploadResult:
        self._validate_content_type(content_type)
        # 分块校验放线程池执行：大文件时的 64KB 循环不应阻塞事件循环
        # （任务 prd R2 / design 第 3 节）。超限在 to_thread 内立即抛错中止。
        file_size = await asyncio.to_thread(self._validate_and_measure, content_type, fileobj)

        media_id = f"med_{uuid4().hex[:12]}"
        storage_key = self._build_storage_key(user_id=user_id, media_id=media_id, filename=filename)

        await self.storage.async_upload_fileobj(
            key=storage_key,
            fileobj=fileobj,
            content_type=content_type,
        )

        media = Media(
            id=media_id,
            user_id=user_id,
            filename=Path(filename).name,
            content_type=content_type,
            file_size=file_size,
            storage_key=storage_key,
            upload_status=MediaUploadStatus.uploaded,
        )
        saved_media = await self.repository.save_media(media)
        preview_url, expires_at = await self.storage.async_create_signed_read_url(
            storage_key,
            expires_in=self.signed_url_ttl_seconds,
        )
        return MediaUploadResult(
            media=saved_media,
            preview_url=preview_url,
            preview_url_expires_at=expires_at,
        )

    async def get_media(self, media_id: str, *, owner_id: str | None = None) -> Media:
        media = await self.repository.get_media(media_id)
        self._ensure_owner(media, owner_id)
        return media

    async def create_media_access_url(
        self, media_id: str, *, owner_id: str | None = None
    ) -> MediaAccessGrant:
        media = await self.repository.get_media(media_id)
        self._ensure_owner(media, owner_id)
        read_url, expires_at = await self.storage.async_create_signed_read_url(
            media.storage_key,
            expires_in=self.signed_url_ttl_seconds,
        )
        return MediaAccessGrant(
            media_id=media.id,
            read_url=read_url,
            expires_at=expires_at,
        )

    def _validate_and_measure(self, content_type: str, fileobj: BinaryIO) -> int:
        """流式分块校验：返回文件字节数；成功路径把指针 seek(0) 还给调用方。

        - 首块只取前 12 字节做魔法字节校验（JPEG/PNG/WEBP 均可判定），
          不必为签名校验把整个文件读进内存；
        - 计数超过 max_file_size 立即抛错并停止读取：剩余输入不再消费，
          磁盘 spool 里的数据交由 Starlette 的 UploadFile 生命周期清理
          （任务 design 第 3 节）。超限路径不 seek，让调用方能从指针位置
          感知到读取确实提前停止。
        - 空 body 与旧 bytes 路径语义一致：魔法字节校验必然失败，拒绝上传。
        """
        total = 0
        while True:
            chunk = fileobj.read(UPLOAD_CHUNK_SIZE)
            if not chunk:
                break
            if total == 0:
                self._validate_file_signature(content_type, chunk[:12])
            total += len(chunk)
            if total > self.max_file_size:
                raise FileTooLargeError(f"File exceeds size limit of {self.max_file_size} bytes")
        if total == 0:
            self._validate_file_signature(content_type, b"")
        fileobj.seek(0)
        return total

    def _validate_content_type(self, content_type: str) -> None:
        if content_type not in self.allowed_content_types:
            raise UnsupportedMediaTypeError(f"Unsupported media type: {content_type}")

    def _validate_file_signature(self, content_type: str, content: bytes) -> None:
        """按内容类型校验魔法字节；content 只需前 12 字节即可判定。"""
        validators = {
            "image/jpeg": lambda payload: payload.startswith(b"\xff\xd8\xff"),
            "image/png": lambda payload: payload.startswith(b"\x89PNG\r\n\x1a\n"),
            "image/webp": self._is_webp,
        }
        validator = validators.get(content_type)
        if validator is None:
            return
        if not validator(content):
            raise ValidationError(f"Invalid image content for {content_type}")

    def _build_storage_key(self, *, user_id: str, media_id: str, filename: str) -> str:
        safe_name = self._sanitize_filename(filename)
        today = datetime.now(UTC)
        return f"media/{owner_to_storage_path(user_id)}/{today:%Y/%m/%d}/{media_id}-{safe_name}"

    def _sanitize_filename(self, filename: str) -> str:
        safe_name = Path(filename).name.strip() or "upload"
        return sub(r"[^A-Za-z0-9._-]+", "-", safe_name).strip("-") or "upload"

    def _is_webp(self, content: bytes) -> bool:
        return len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP"

    def _ensure_owner(self, media: Media, owner_id: str | None) -> None:
        if owner_id is None or media.user_id == owner_id:
            return
        raise NotFoundError(f"Media {media.id} not found")
