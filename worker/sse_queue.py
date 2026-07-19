import os
import json
import redis
from typing import Generator

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")


def push_event(job_id: str, event: dict) -> None:
    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    key = f"job:{job_id}:events"
    r.rpush(key, json.dumps(event))


def event_stream(job_id: str) -> Generator[str, None, None]:
    raise NotImplementedError("Worker no usa event_stream")