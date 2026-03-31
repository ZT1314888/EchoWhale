from api.common.exceptions import NotFoundError
from api.models.media_model import Media


_media_store: dict[str, Media] = {}


def save_media(media: Media) -> Media:
    _media_store[media.id] = media
    return media


def get_media(media_id: str) -> Media:
    media = _media_store.get(media_id)
    if not media:
        raise NotFoundError(f"Media {media_id} not found")
    return media
