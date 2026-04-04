from __future__ import annotations

from pathlib import Path

from api.core.config import Settings


def test_settings_accept_csv_lists_from_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173",
                "MEDIA_ALLOWED_CONTENT_TYPES=image/jpeg,image/png,image/webp",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.allowed_origins == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    assert settings.media_allowed_content_types == [
        "image/jpeg",
        "image/png",
        "image/webp",
    ]


def test_settings_support_signed_url_ttl_override(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("R2_SIGNED_URL_TTL_SECONDS=1200", encoding="utf-8")

    settings = Settings(_env_file=env_file)

    assert settings.r2_signed_url_ttl_seconds == 1200
