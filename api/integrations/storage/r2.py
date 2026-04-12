from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi.concurrency import run_in_threadpool

from api.common.exceptions import StorageError
from api.core.config import settings


class R2StorageService:
    def __init__(self) -> None:
        self._client: Any | None = None

    def upload_bytes(self, *, key: str, content: bytes, content_type: str) -> None:
        try:
            client = self._get_client()
            client.put_object(
                Bucket=settings.r2_bucket,
                Key=key,
                Body=content,
                ContentType=content_type,
            )
        except StorageError:
            raise
        except Exception as exc:  # pragma: no cover - network call
            raise StorageError("Failed to upload media to object storage") from exc

    async def async_upload_bytes(self, *, key: str, content: bytes, content_type: str) -> None:
        await run_in_threadpool(self.upload_bytes, key=key, content=content, content_type=content_type)

    def create_signed_read_url(self, key: str, *, expires_in: int) -> tuple[str, datetime]:
        try:
            client = self._get_client()
            url = client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": settings.r2_bucket,
                    "Key": key,
                },
                ExpiresIn=expires_in,
            )
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            return (url, expires_at)
        except StorageError:
            raise
        except Exception as exc:  # pragma: no cover - network call
            raise StorageError("Failed to create signed media access URL") from exc

    async def async_create_signed_read_url(self, key: str, *, expires_in: int) -> tuple[str, datetime]:
        return await run_in_threadpool(self.create_signed_read_url, key=key, expires_in=expires_in)

    def delete_object(self, key: str) -> None:
        try:
            client = self._get_client()
            client.delete_object(
                Bucket=settings.r2_bucket,
                Key=key,
            )
        except StorageError:
            raise
        except Exception as exc:  # pragma: no cover - network call
            raise StorageError("Failed to delete media from object storage") from exc

    async def async_delete_object(self, key: str) -> None:
        await run_in_threadpool(self.delete_object, key=key)

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        if not settings.r2_endpoint:
            raise StorageError("R2 endpoint is not configured")
        if not settings.r2_access_key_id or not settings.r2_secret_access_key:
            raise StorageError("R2 credentials are not configured")

        try:
            import boto3
        except ModuleNotFoundError as exc:  # pragma: no cover - depends on env
            raise StorageError(
                "boto3 is required for R2 uploads. Install project dependencies first."
            ) from exc

        self._client = boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            region_name="auto",
        )
        return self._client
