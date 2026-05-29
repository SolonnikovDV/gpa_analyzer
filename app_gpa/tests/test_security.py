from modules.analysis.security import InMemoryRateLimiter


def test_rate_limiter_blocks_after_limit(monkeypatch):
    timestamps = iter([100.0, 100.1, 100.2])
    monkeypatch.setattr("detailed.security.time.time", lambda: next(timestamps))
    limiter = InMemoryRateLimiter(limit=2, window_seconds=10)

    first = limiter.check("client-1")
    second = limiter.check("client-1")
    third = limiter.check("client-1")

    assert first.allowed is True
    assert second.allowed is True
    assert third.allowed is False
    assert third.retry_after_seconds >= 1


def test_rate_limiter_allows_again_after_window(monkeypatch):
    timestamps = iter([10.0, 10.1, 12.2])
    monkeypatch.setattr("detailed.security.time.time", lambda: next(timestamps))
    limiter = InMemoryRateLimiter(limit=1, window_seconds=2)

    first = limiter.check("client-1")
    blocked = limiter.check("client-1")
    allowed_again = limiter.check("client-1")

    assert first.allowed is True
    assert blocked.allowed is False
    assert allowed_again.allowed is True
