"""
Утилитарные декораторы.
"""

import asyncio
import functools
import logging

from ..config import Constants

logger = logging.getLogger(__name__)


def retry_on_error(
    max_attempts: int = Constants.RETRY_ATTEMPTS, 
    delay: float = Constants.RETRY_DELAY
):
    """Декоратор для повторных попыток операций при ошибках."""

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    logger.warning(
                        f"Attempt {attempt + 1} failed: {e}, retrying in {delay}s"
                    )
                    await asyncio.sleep(
                        delay * (2**attempt)
                    )  # Exponential backoff
            return None

        return wrapper

    return decorator
