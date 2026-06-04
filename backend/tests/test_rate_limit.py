import pytest
from fastapi import HTTPException, Request
from unittest.mock import MagicMock

from core.rate_limit import (
    rate_limit,
    reset_rate_limits,
    _in_memory_rate_limit,
    _redis_rate_limit,
)
import core.rate_limit as rate_limit_module


def _make_request(host="127.0.0.1"):
    req = MagicMock(spec=Request)
    req.client = MagicMock()
    req.client.host = host
    return req


def test_in_memory_rate_limit_allows_under_limit():
    reset_rate_limits()
    req = _make_request()
    rate_limit(req, "user-1", "UPLOAD", default_count=3, default_window=60)
    rate_limit(req, "user-1", "UPLOAD", default_count=3, default_window=60)
    rate_limit(req, "user-1", "UPLOAD", default_count=3, default_window=60)


def test_in_memory_rate_limit_blocks_over_limit():
    reset_rate_limits()
    req = _make_request()
    rate_limit(req, "user-1", "UPLOAD", default_count=1, default_window=60)
    with pytest.raises(HTTPException, match="Rate limit exceeded"):
        rate_limit(req, "user-1", "UPLOAD", default_count=1, default_window=60)


def test_redis_rate_limit_allows_under_limit():
    redis_mock = MagicMock()
    redis_mock.pipeline.return_value = redis_mock
    redis_mock.execute.return_value = [0, 1, 1, 1]  # zrem, zadd, zcard, expire
    _redis_rate_limit(redis_mock, "ratelimit:test:user", count=3, window=60)
    redis_mock.zadd.assert_called_once()


def test_redis_rate_limit_blocks_over_limit():
    redis_mock = MagicMock()
    redis_mock.pipeline.return_value = redis_mock
    redis_mock.execute.return_value = [0, 1, 4, 1]  # zcard=4 exceeds count=3
    with pytest.raises(HTTPException, match="Rate limit exceeded"):
        _redis_rate_limit(redis_mock, "ratelimit:test:user", count=3, window=60)
    redis_mock.zrem.assert_called_once()


def test_redis_rate_limit_fallback_on_connection_error(monkeypatch):
    redis_mock = MagicMock()
    redis_mock.pipeline.side_effect = RuntimeError("Redis down")

    calls = []
    monkeypatch.setattr("core.rate_limit._in_memory_rate_limit", lambda key, count, window: calls.append("memory"))

    _redis_rate_limit(redis_mock, "ratelimit:test:user", count=3, window=60)
    assert calls == ["memory"]


def test_rate_limit_uses_redis_when_available(monkeypatch):
    reset_rate_limits()
    redis_mock = MagicMock()
    redis_mock.pipeline.return_value = redis_mock
    redis_mock.execute.return_value = [0, 1, 1, 1]
    monkeypatch.setattr("core.rate_limit._get_redis_client", lambda: redis_mock)

    req = _make_request()
    rate_limit(req, "user-1", "UPLOAD", default_count=3, default_window=60)
    redis_mock.zadd.assert_called_once()


def test_rate_limit_uses_memory_when_redis_unavailable(monkeypatch):
    reset_rate_limits()
    monkeypatch.setattr("core.rate_limit._get_redis_client", lambda: None)

    req = _make_request()
    rate_limit(req, "user-1", "UPLOAD", default_count=3, default_window=60)
    # No exception means in-memory path succeeded


def test_reset_rate_limits_only_deletes_rate_limit_keys(monkeypatch):
    redis_mock = MagicMock()
    redis_mock.scan_iter.return_value = [b"ratelimit:UPLOAD:user-1", b"ratelimit:EXPORT:user-1"]
    monkeypatch.setattr(rate_limit_module, "_redis_client", redis_mock)

    reset_rate_limits()

    redis_mock.scan_iter.assert_called_once_with(match="ratelimit:*", count=1000)
    redis_mock.delete.assert_called_once_with(b"ratelimit:UPLOAD:user-1", b"ratelimit:EXPORT:user-1")
    redis_mock.flushdb.assert_not_called()
