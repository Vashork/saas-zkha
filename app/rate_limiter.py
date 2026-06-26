"""
Simple in-memory rate limiter for the login endpoint.

Tracks request counts per IP address using a sliding window.
Blocks login attempts exceeding 10 per minute.
"""

import logging
import time
from collections import defaultdict

logger = logging.getLogger("zhkh.ratelimit")

MAX_ATTEMPTS = 10
WINDOW_SECONDS = 60

# ip -> list of timestamps
_attempts: dict[str, list[float]] = defaultdict(list)


def _is_rate_limited(ip: str) -> bool:
    """Return True if the IP has exceeded the rate limit."""
    now = time.time()
    window_start = now - WINDOW_SECONDS

    # Prune old entries
    timestamps = [t for t in _attempts.get(ip, []) if t > window_start]
    _attempts[ip] = timestamps

    if len(timestamps) >= MAX_ATTEMPTS:
        return True

    return False


def _record_attempt(ip: str) -> None:
    """Record a login attempt from the given IP."""
    _attempts[ip].append(time.time())


def cleanup(stale_seconds: int = WINDOW_SECONDS * 2) -> None:
    """Remove stale entries to prevent memory leak. Call periodically."""
    now = time.time()
    cutoff = now - stale_seconds
    keys_to_remove = [
        ip for ip, timestamps in _attempts.items()
        if not timestamps or max(timestamps) < cutoff
    ]
    for ip in keys_to_remove:
        del _attempts[ip]
