class RedisQueue:
    def enqueue(self, task_name: str, payload: dict) -> dict:
        return {"task_name": task_name, "payload": payload, "status": "queued"}
