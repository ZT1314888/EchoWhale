from __future__ import annotations

import asyncio
from io import BytesIO
from statistics import pstdev

import httpx
from PIL import Image
from PIL import UnidentifiedImageError

from api.common.exceptions import ModelProviderError
from api.common.exceptions import UnsupportedSceneImageError
from api.modules.scene_engine.schema import SceneAnalysisInput


UNSUPPORTED_IMAGE_MESSAGE = "Unsupported scene image"


class SceneImageQualityGate:
    def __init__(
        self,
        *,
        timeout_seconds: int = 10,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """记录图片筛查所需的超时和可选传输层配置。"""
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def screen(self, payload: SceneAnalysisInput) -> None:
        """在进入视觉模型前先拦截明显不可读或无训练价值的图片。"""
        content, content_type = await self._fetch_image(payload.media_url)
        grayscale_data = await asyncio.to_thread(_load_grayscale_pixels, content)
        if grayscale_data is None:
            if content_type.startswith("image/"):
                raise UnsupportedSceneImageError(
                    UNSUPPORTED_IMAGE_MESSAGE,
                    data={"reason": "image_unreadable", "retryable": False},
                )
            return

        grayscale_values, width, height = grayscale_data
        self._assert_image_quality(grayscale_values, width=width, height=height)

    async def _fetch_image(self, media_url: str) -> tuple[bytes, str]:
        """拉取图片原始内容，并在协议层就拒绝非图片响应。"""
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                follow_redirects=True,
                transport=self.transport,
            ) as client:
                response = await client.get(media_url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ModelProviderError("Failed to fetch image for screening") from exc

        content_type = response.headers.get("Content-Type", "").lower()
        if content_type and not content_type.startswith("image/"):
            raise ModelProviderError("Scene image fetch did not return an image")
        return (response.content, content_type)

    def _assert_image_quality(
        self,
        grayscale_values: list[int],
        *,
        width: int,
        height: int,
    ) -> None:
        """用简单统计特征拦截纯色图、损坏图和细节极低的图片。"""
        if not grayscale_values:
            raise UnsupportedSceneImageError(
                UNSUPPORTED_IMAGE_MESSAGE,
                data={"reason": "image_unreadable", "retryable": False},
            )

        dynamic_range = max(grayscale_values) - min(grayscale_values)
        stddev = pstdev(grayscale_values)
        if dynamic_range <= 4 and stddev <= 2:
            raise UnsupportedSceneImageError(
                UNSUPPORTED_IMAGE_MESSAGE,
                data={"reason": "image_too_uniform", "retryable": False},
            )

        if _mean_adjacent_difference(grayscale_values, width=width, height=height) < 6:
            raise UnsupportedSceneImageError(
                UNSUPPORTED_IMAGE_MESSAGE,
                data={"reason": "image_unreadable", "retryable": False},
            )


def _load_grayscale_pixels(content: bytes) -> tuple[list[int], int, int] | None:
    """尽量把图片解码成灰度像素矩阵，失败时返回空供上层判定。"""
    try:
        with Image.open(BytesIO(content)) as image:
            normalized = image.convert("L")
            width, height = normalized.size
            pixels = normalized.load()
            if pixels is None:
                return None
            grayscale_values = [
                pixels[column, row]
                for row in range(height)
                for column in range(width)
            ]
            return (grayscale_values, width, height)
    except (UnidentifiedImageError, OSError):
        return None


def _mean_adjacent_difference(
    grayscale_values: list[int],
    *,
    width: int,
    height: int,
) -> float:
    """计算相邻像素平均差异，用于估计图像纹理强度。"""
    if len(grayscale_values) < 2:
        return 0.0

    total = 0
    count = 0
    for row in range(height):
        for column in range(width):
            index = (row * width) + column
            if column + 1 < width:
                total += abs(grayscale_values[index] - grayscale_values[index + 1])
                count += 1
            if row + 1 < height:
                total += abs(grayscale_values[index] - grayscale_values[index + width])
                count += 1
    return total / max(count, 1)
