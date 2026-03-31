def enqueue_session_summary(session_id: str) -> dict[str, str]:
    return {"session_id": session_id, "status": "queued"}
