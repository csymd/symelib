"""
Rate limiter for NCBI E-utilities to respect rate limits.
"""

from collections.abc import Callable
import time

from elib.utils.logging import LoggerConfig, get_shared_logger

logger = get_shared_logger(LoggerConfig(name="rate_limiter"))


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
        # Used as bare @rate_limited_batch
        return _decorate(func)
    # Used as @rate_limited_batch(...)
    return _decorate


def simple_sleep(seconds: float = 2.0):
    """Simple sleep with logging."""
    logger.debug(f"Sleeping for {seconds} seconds")
    time.sleep(seconds)
