"""Rate limiter with Redis sliding-window backing and in-process fallback."""

import logging
import os
import time
import uuid
from collections import defaultdict, deque
from typing import Deque, DefaultDict, Optional

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

_requests: DefaultDict[str, Deque[float]] = defaultdict(deque)

_redis_client = None


def _get_redis_client():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return None
    try:
        from redis import Redis
        client = Redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
        client.ping()
        _redis_client = client
        logger.info("Redis rate limiter initialized")
        return client
    except Exception as exc:
        logger.warning("Redis rate limiter unavailable, falling back to in-memory: %s", exc)
        return None


def _limit_config(name: str, default_count: int, default_window: int) -> tuple[int, int]:
    count = int(os.getenv(f"RATE_LIMIT_{name}_COUNT", str(default_count)))
    window = int(os.getenv(f"RATE_LIMIT_{name}_WINDOW_SECONDS", str(default_window)))
    return max(1, count), max(1, window)


def _in_memory_rate_limit(key: str, count: int, window: int) -> None:
    now = time.monotonic()
    bucket = _requests[key]
    while bucket and now - bucket[0] > window:
        bucket.popleft()
    if len(bucket) >= count:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again later.",
        )
    bucket.append(now)


def _redis_rate_limit(redis_client, key: str, count: int, window: int) -> None:
    now = time.time()
    member = f"{now}:{uuid.uuid4().hex}"
    try:
        pipe = redis_client.pipeline()
        pipe.zremrangebyscore(key, 0, now - window)
        pipe.zadd(key, {member: now})
        pipe.zcard(key)
        pipe.expire(key, window + 1)
        _, _, current_count, _ = pipe.execute()
        if current_count > count:
            redis_client.zrem(key, member)
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Try again later.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Redis rate limit error, falling back to in-memory: %s", exc)
        _in_memory_rate_limit(key, count, window)


def rate_limit(request: Request, user_id: Optional[str], name: str, default_count: int, default_window: int) -> None:
    count, window = _limit_config(name, default_count, default_window)
    client_host = request.client.host if request.client else "unknown"
    identity = user_id or client_host
    key = f"ratelimit:{name}:{identity}"

    redis_client = _get_redis_client()
    if redis_client:
        _redis_rate_limit(redis_client, key, count, window)
    else:
        _in_memory_rate_limit(key, count, window)


def reset_rate_limits() -> None:
    _requests.clear()
    global _redis_client
    if _redis_client:
        try:
            keys = list(_redis_client.scan_iter(match="ratelimit:*", count=1000))
            if keys:
                _redis_client.delete(*keys)
        except Exception:
            pass
        _redis_client = None
