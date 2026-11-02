from __future__ import annotations

import asyncio
import struct
import zlib
from io import BytesIO

import httpx
import pytest
from PIL import Image

from api.common.exceptions import UnsupportedSceneImageError
from api.modules.scene_engine.schema import SceneAnalysisInput
from api.modules.scene_engine.tools.image_quality import SceneImageQualityGate


def _make_png_bytes(color: int | None = None) -> bytes:
    pixels: list[list[int]] = []
    for y in range(8):
        row: list[int] = []
        for x in range(8):
            row.append(color if color is not None else (x * 24) + (y * 3))
        pixels.append(row)

    raw = b"".join(bytes([0, *row]) for row in pixels)
    ihdr = struct.pack(">IIBBBBB", 8, 8, 8, 0, 0, 0, 0)
    idat = zlib.compress(raw)

    def chunk(chunk_type: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + chunk_type
            + data
            + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
        )

    return b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            chunk(b"IHDR", ihdr),
            chunk(b"IDAT", idat),
            chunk(b"IEND", b""),
        ]
    )


def _make_raster_bytes(*, format: str, color: int | None = None) -> bytes:
    image = Image.new("L", (8, 8))
    if color is None:
        for x in range(8):
            for y in range(8):
                image.putpixel((x, y), (x * 24) + (y * 3))
    else:
        image.paste(color, (0, 0, 8, 8))

    buffer = BytesIO()
    save_kwargs = {"format": format}
    if format.upper() == "JPEG":
        save_kwargs["quality"] = 100
    image.save(buffer, **save_kwargs)
    return buffer.getvalue()


def test_quality_gate_rejects_uniform_black_image() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "image/png"},
            content=_make_png_bytes(color=0),
        )
    )
    gate = SceneImageQualityGate(transport=transport)

    with pytest.raises(UnsupportedSceneImageError) as exc_info:
        asyncio.run(
            gate.screen(
                SceneAnalysisInput(
                    filename="black.png",
                    media_url="https://signed.test/media/demo-user/black.png",
                )
            )
        )

    assert exc_info.value.data == {
        "reason": "image_too_uniform",
        "retryable": False,
    }


def test_quality_gate_allows_non_uniform_image() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "image/png"},
            content=_make_png_bytes(),
        )
    )
    gate = SceneImageQualityGate(transport=transport)

    asyncio.run(
        gate.screen(
            SceneAnalysisInput(
                filename="scene.png",
                media_url="https://signed.test/media/demo-user/scene.png",
            )
        )
    )


def test_quality_gate_rejects_uniform_black_jpeg_image() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "image/jpeg"},
            content=_make_raster_bytes(format="JPEG", color=0),
        )
    )
    gate = SceneImageQualityGate(transport=transport)

    with pytest.raises(UnsupportedSceneImageError) as exc_info:
        asyncio.run(
            gate.screen(
                SceneAnalysisInput(
                    filename="black.jpg",
                    media_url="https://signed.test/media/demo-user/black.jpg",
                )
            )
        )

    assert exc_info.value.data == {
        "reason": "image_too_uniform",
        "retryable": False,
    }


def test_quality_gate_allows_non_uniform_webp_image() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "image/webp"},
            content=_make_raster_bytes(format="WEBP"),
        )
    )
    gate = SceneImageQualityGate(transport=transport)

    asyncio.run(
        gate.screen(
            SceneAnalysisInput(
                filename="scene.webp",
                media_url="https://signed.test/media/demo-user/scene.webp",
            )
        )
    )


def test_quality_gate_rejects_unreadable_webp_payload() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "image/webp"},
            content=b"not-a-real-webp",
        )
    )
    gate = SceneImageQualityGate(transport=transport)

    with pytest.raises(UnsupportedSceneImageError) as exc_info:
        asyncio.run(
            gate.screen(
                SceneAnalysisInput(
                    filename="broken.webp",
                    media_url="https://signed.test/media/demo-user/broken.webp",
                )
            )
        )

    assert exc_info.value.data == {
        "reason": "image_unreadable",
        "retryable": False,
    }
