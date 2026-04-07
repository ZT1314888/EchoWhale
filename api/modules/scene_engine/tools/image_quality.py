from __future__ import annotations

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
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def screen(self, payload: SceneAnalysisInput) -> None:
        content, content_type = self._fetch_image(payload.media_url)
        grayscale_data = _load_grayscale_pixels(content)
        if grayscale_data is None:
            if content_type.startswith("image/"):
                raise UnsupportedSceneImageError(
                    UNSUPPORTED_IMAGE_MESSAGE,
                    data={"reason": "image_unreadable", "retryable": False},
                )
            return

        grayscale_values, width, height = grayscale_data
        self._assert_image_quality(grayscale_values, width=width, height=height)

    def _fetch_image(self, media_url: str) -> tuple[bytes, str]:
        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                follow_redirects=True,
                transport=self.transport,
            ) as client:
                response = client.get(media_url)
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
