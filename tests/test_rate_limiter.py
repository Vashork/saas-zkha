"""
Tests for rate limiter.
"""

import time
import pytest

from app.rate_limiter import _is_rate_limited, _record_attempt, MAX_ATTEMPTS, WINDOW_SECONDS


# --- Constants ---

def test_window_is_positive():
    assert WINDOW_SECONDS > 0


def test_limit_is_positive():
    assert MAX_ATTEMPTS > 0


# --- _record_attempt and _is_rate_limited ---

@pytest.fixture(autouse=True)
def clean_state():
    """Clear the internal state before and after each test."""
    from app.rate_limiter import _attempts
    _attempts.clear()
    yield
    _attempts.clear()


def test_first_attempt_not_limited():
    assert _is_rate_limited("127.0.0.1") is False


def test_under_limit_not_limited():
    for _ in range(MAX_ATTEMPTS - 1):
        _record_attempt("127.0.0.1")
    assert _is_rate_limited("127.0.0.1") is False


def test_at_limit_is_limited():
    for _ in range(MAX_ATTEMPTS):
        _record_attempt("127.0.0.1")
    assert _is_rate_limited("127.0.0.1") is True


def test_over_limit_is_limited():
    for _ in range(MAX_ATTEMPTS + 5):
        _record_attempt("127.0.0.1")
    assert _is_rate_limited("127.0.0.1") is True


def test_different_ips_independent():
    for _ in range(MAX_ATTEMPTS):
        _record_attempt("127.0.0.1")
    assert _is_rate_limited("192.168.1.1") is False


def test_window_expiry():
    from app import rate_limiter
    orig_time = time.time

    for _ in range(MAX_ATTEMPTS):
        _record_attempt("127.0.0.1")

    assert _is_rate_limited("127.0.0.1") is True

    # Simulate time passing beyond window
    fake_time = orig_time() + WINDOW_SECONDS + 1
    rate_limiter.time.time = lambda: fake_time
    try:
        assert _is_rate_limited("127.0.0.1") is False
    finally:
        rate_limiter.time.time = orig_time
