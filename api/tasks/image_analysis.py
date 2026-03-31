def enqueue_image_analysis(media_id: str) -> dict[str, str]:
    return {"media_id": media_id, "status": "queued"}
