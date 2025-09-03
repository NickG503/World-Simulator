from __future__ import annotations
import logging
from functools import wraps
from typing import Any, Callable


def log_calls(logger_name: str | None = None) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to log function calls at DEBUG level with basic error logging."""

    def _decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        name = logger_name or func.__module__
        logger = logging.getLogger(name)

        @wraps(func)
        def _wrapper(*args: Any, **kwargs: Any) -> Any:
            logger.debug("Calling %s args=%s kwargs=%s", func.__name__, args, kwargs)
            try:
                result = func(*args, **kwargs)
            except Exception as e:
                logger.exception("Error in %s: %s", func.__name__, e)
                raise
            logger.debug("%s returned %r", func.__name__, result)
            return result

        return _wrapper

    return _decorator

