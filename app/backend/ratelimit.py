"""A small in-process rate limiter for the public endpoints.

Why this and not Flask-Limiter
------------------------------
Flask-Limiter is the usual answer, but with its default in-memory storage it
gives exactly what this module gives — a per-process counter — for the cost of
another dependency. The extra reliability only arrives with a shared backend
(Redis), which this project does not have and does not need for a single
free-tier instance. So the counter is written here, in about forty lines that
can be read and explained in full, rather than pulled in.

What it does
------------
A fixed-window counter per (rule, client). The first request in a window starts
a timer; requests beyond the limit inside that window get 429 with a
`Retry-After` header saying when to come back.

Known limitations — stated because they matter, not hidden:

* **Per process.** Each gunicorn worker keeps its own counters, so with N
  workers the effective limit is up to N x the configured one. It still turns
  unlimited password guessing into a slow trickle, which is the point.
* **Resets on restart.** Counters live in memory.
* **Fixed window, not sliding.** A burst spanning a window boundary can briefly
  reach 2x the limit. Acceptable here: these limits exist to stop automated
  abuse, not to meter a paid API.

For this project's threat model — a public college demo that should not be
trivially brute-forcible or spammable — that is the right trade-off.
"""

from __future__ import annotations

import time
from collections import defaultdict
from functools import wraps
from threading import Lock

from flask import current_app, jsonify, request

# (rule, client) -> [window_started_at, count]
_hits: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0])
_lock = Lock()

# Entries are only dropped when we happen to touch the table, so a prune runs
# occasionally to stop it growing without bound on a long-lived process.
_PRUNE_EVERY = 500
_since_prune = 0


def client_id() -> str:
    """Who is being limited.

    `request.remote_addr` is the real client only once ProxyFix has rewritten
    it from X-Forwarded-For, which `create_app` enables in production. Without
    that, every request behind Render's proxy would share one address and a
    single abuser would lock out everybody.
    """
    return request.remote_addr or "unknown"


def _prune(now: float, longest_window: float) -> None:
    global _since_prune
    _since_prune = 0
    stale = [k for k, (started, _) in _hits.items() if now - started > longest_window]
    for key in stale:
        del _hits[key]


def check(rule: str, limit: int, window: int) -> int | None:
    """Count one hit. Returns seconds to wait if the caller is over the limit."""
    global _since_prune
    now = time.monotonic()
    key = (rule, client_id())

    with _lock:
        _since_prune += 1
        if _since_prune >= _PRUNE_EVERY:
            _prune(now, window * 4)

        started, count = _hits[key]
        if now - started >= window:
            _hits[key] = [now, 1]  # window expired (or first ever hit)
            return None

        if count >= limit:
            return max(1, int(window - (now - started)))

        _hits[key] = [started, count + 1]
        return None


def rate_limit(rule: str, limit: int, window: int):
    """Allow `limit` requests per `window` seconds per client, per process.

    Disabled when RATE_LIMIT_ENABLED is false, which is how the test suite runs
    hundreds of requests without tripping it.
    """

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_app.config.get("RATE_LIMIT_ENABLED", True):
                return fn(*args, **kwargs)

            retry_after = check(rule, limit, window)
            if retry_after is not None:
                response = jsonify(
                    {
                        "error": "Too many requests. Please wait a moment and try again.",
                        "retry_after": retry_after,
                    }
                )
                response.status_code = 429
                response.headers["Retry-After"] = str(retry_after)
                return response
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def reset() -> None:
    """Clear every counter. Used by the tests; not called by the app."""
    with _lock:
        _hits.clear()
