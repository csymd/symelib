"""
Rate limiter for NCBI E-utilities to respect rate limits.
"""
import time
from typing import Callable, Any

from elib.utils.logging import LoggerConfig, get_shared_logger

logger = get_shared_logger(LoggerConfig(name="rate_limiter"))


def rate_limited_batch(func: Callable, batch_size: int = 5, sleep_seconds: float = 2.0):
    """Decorator or wrapper to batch calls and sleep between batches.
    
    Useful for NCBI bulk operations.
    """
    def wrapper(items: list, *args, **kwargs) -> list:
        results = []
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            logger.debug(f'Processing batch {i//batch_size + 1} of size {len(batch)}')
            
            batch_results = func(batch, *args, **kwargs)
            results.extend(batch_results)
            
            if i + batch_size < len(items):
                logger.info(f'Sleeping {sleep_seconds}s after batch to respect NCBI rate limits')
                time.sleep(sleep_seconds)
        
        return results
    return wrapper


def simple_sleep(seconds: float = 2.0):
    """Simple sleep with logging."""
    logger.debug(f'Sleeping for {seconds} seconds')
    time.sleep(seconds)
