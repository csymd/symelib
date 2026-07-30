"""
Rate limiting for NCBI E-utilities and Crossref.

NCBI (without API key): max ~3 requests/second.
NCBI (with API key):    max ~10 requests/second.
Crossref polite pool:   ~1 request/second is comfortable; bursts ok briefly.

We enforce a minimum spacing between HTTP calls and exponential backoff on 429.
"""

from __future__ import annotations

from collections.abc import Callable
import random
import threading
import time

from symworx_elibrary.utils.logging import LoggerConfig, get_shared_logger

logger = get_shared_logger(LoggerConfig(name="rate_limiter"))


class RequestThrottle:
    """Thread-safe min-interval throttle + 429 backoff helper."""

    def __init__(self, min_interval: float = 0.4, name: str = "http"):
        self.min_interval = max(0.0, float(min_interval))
        self.name = name
        self._lock = threading.Lock()
        self._last_at = 0.0
        self._backoff = 0.0  # extra delay after 429s

    def set_min_interval(self, seconds: float) -> None:
        with self._lock:
            self.min_interval = max(0.0, float(seconds))

    def wait(self) -> None:
        """Block until the next request is allowed."""
        with self._lock:
            now = time.monotonic()
            gap = self.min_interval + self._backoff
            wait_for = self._last_at + gap - now
            if wait_for > 0:
                logger.debug(
                    "Throttle wait",
                    name=self.name,
                    seconds=round(wait_for, 3),
                    backoff=self._backoff,
                )
            else:
                wait_for = 0.0
        if wait_for > 0:
            time.sleep(wait_for)
        with self._lock:
            self._last_at = time.monotonic()

    def on_success(self) -> None:
        """Decay backoff after a successful call."""
        with self._lock:
            self._backoff = max(0.0, self._backoff * 0.5)
            if self._backoff < 0.05:
                self._backoff = 0.0

    def on_rate_limit(self, retry_after: float | None = None) -> float:
        """
        Record a 429 and return how long the caller should sleep.

        Uses Retry-After when provided, else exponential-ish backoff with jitter.
        """
        with self._lock:
            if retry_after is not None and retry_after > 0:
                sleep_s = float(retry_after)
            else:
                # 2s, 4s, 8s… capped, plus small jitter
                base = max(2.0, self._backoff * 2 if self._backoff else 2.0)
                sleep_s = min(60.0, base) + random.uniform(0.0, 0.5)
            self._backoff = sleep_s
            logger.info(
                "Rate limited; backing off",
                name=self.name,
                sleep_seconds=round(sleep_s, 2),
            )
            return sleep_s


# Shared throttles (module singletons so all clients share the budget)
_ncbi_throttle = RequestThrottle(min_interval=0.4, name="ncbi")
_crossref_throttle = RequestThrottle(min_interval=0.35, name="crossref")


def configure_ncbi_throttle(
    *, api_key: str | None = None, min_interval: float | None = None
) -> None:
    """Set NCBI spacing from API key presence or an explicit override."""
    if min_interval is not None:
        _ncbi_throttle.set_min_interval(min_interval)
    elif api_key:
        # ~10/s allowed → stay under at ~8/s
        _ncbi_throttle.set_min_interval(0.15)
    else:
        # ~3/s allowed → stay under at ~2/s
        _ncbi_throttle.set_min_interval(0.5)


def configure_process_delay(seconds: float | None) -> None:
    """CLI override for process/enrich: apply to both NCBI and Crossref."""
    if seconds is None:
        return
    seconds = max(0.0, float(seconds))
    _ncbi_throttle.set_min_interval(seconds)
    _crossref_throttle.set_min_interval(max(0.2, seconds * 0.75))


def ncbi_throttle() -> RequestThrottle:
    return _ncbi_throttle


def crossref_throttle() -> RequestThrottle:
    return _crossref_throttle


def rate_limited_batch(
    func: Callable | None = None, *, batch_size: int = 5, sleep_seconds: float = 2.0
):
    """Decorator (optionally parametrized) to batch calls and sleep between batches.

    Supports:
        @rate_limited_batch
        @rate_limited_batch(batch_size=10, sleep_seconds=1.0)
    """

    def _decorate(f: Callable) -> Callable:
        def wrapper(items: list, *args, **kwargs) -> list:
            results = []
            for i in range(0, len(items), batch_size):
                batch = items[i : i + batch_size]
                logger.debug(f"Processing batch {i // batch_size + 1} of size {len(batch)}")

                batch_results = f(batch, *args, **kwargs)
                results.extend(batch_results)

                if i + batch_size < len(items):
                    logger.info(
                        f"Sleeping {sleep_seconds}s after batch to respect NCBI rate limits"
                    )
                    time.sleep(sleep_seconds)

            return results

        return wrapper

    if func is not None:
        return _decorate(func)
    return _decorate


def simple_sleep(seconds: float = 2.0):
    """Simple sleep with logging."""
    logger.debug(f"Sleeping for {seconds} seconds")
    time.sleep(seconds)
