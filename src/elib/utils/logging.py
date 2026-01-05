"""
src/elib/utils/logging.py
"""
from __future__ import annotations

import os
import json
from typing import Any, Optional

# ================================================== #
# Simple Logger                                      #
# ================================================== #

_logger_instance: Optional[eLibLogger] = None

class eLibLogger:
    """
    A minimal JSON logger for structured logging.
    """
    def __init__(
            self,
            name: Optional[str] = None,
            service: Optional[str] = None,
            env: Optional[str] = None,
            level: Optional[str] = 'INFO',
    ):
        self.name = name or os.getenv('ELIB_SERVICE_NAME', 'eLibApp')
        self.service = service or os.getenv('ELIB_SERVICE_NAME', 'eLibApp')
        self.env = env or os.getenv('LOG_ENV', 'DEV')
        self.level = level.upper()
        self.level_order = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

    def _should_log(self, level: str) -> bool:
        """Check if the log level is high enough to log."""
        try:
            result = self.level_order.index(level) >= self.level_order.index(self.level)
            return result
        except ValueError:
            return False

    def _emit(self, level: str, message: str, **kwargs: Any) -> None:
        """Emit a log message as a JSON object."""
        if not self._should_log(level):
            return
        log_entry = {
            "level": level,
            "message": message,
            "service": self.service,
        }
        log_entry.update(kwargs)  # Add extra fields
        print(json.dumps(log_entry), flush=True)

    def debug(self, message: str, **kwargs: Any) -> None:
        self._emit('DEBUG', message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        self._emit('INFO', message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        self._emit('WARNING', message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        self._emit('ERROR', message, **kwargs)

    def critical(self, message: str, **kwargs: Any) -> None:
        self._emit('CRITICAL', message, **kwargs)


# ================================================= #
# Logger Factory                                    #
# ================================================= #
# Allows all loggers to be created in a standard way and linked together

def initialize_logger(name: str, env: Optional[str] = None) -> eLibLogger:
    """
    Create and return a eLibLogger instance with the specified name and level.

    args:
        name (str): The name of the logger (e.g., the module or file name).
        env (Optional[str]): The environment string ('PROD', 'DEV', etc.). If None, fetch from LOG_ENV.

    returns:
        eLibLogger: A configured eLibLogger instance.
    """
    global _logger_instance

    # Determine the environment
    if env is None:
        env = os.getenv('LOG_ENV', 'DEV')  # Default to 'DEV'

    # Map environment to logging levels
    env_to_level = {
        'PROD': 'ERROR',
        'STAGING': 'WARNING',
        'DEV': 'DEBUG',
        'TEST': 'INFO'
    }
    level = env_to_level.get(env.upper(), 'DEBUG')  # Default to 'DEBUG' if env is unrecognized

    # Initialize or update the logger instance
    if _logger_instance is None:
        print(f'Creating new logger: name={name}, env={env}')
        _logger_instance = eLibLogger(name=name, level=level)
    else:
        print(f'Updating logger level to: {level}')
        _logger_instance.level = level

    return _logger_instance


def get_shared_logger(name: str = 'eLibApp', level: str = 'INFO') -> eLibLogger:
    """
    Get or initialize the shared logger instance.

    args:
        name (str): The name of the logger (e.g., the module or file name).
        level (str): The logging level (e.g., DEBUG, INFO, WARNING, ERROR, CRITICAL).

    returns:
        eLibLogger: A shared eLibLogger instance.
    """
    global _logger_instance
    # print(f'Getting shared logger: {name} with level: {level}')
    if _logger_instance is None:
        _logger_instance = eLibLogger(name=name)
    else:
        _logger_instance.name = name
    return _logger_instance


def exception(self, message: str, exc: Exception, **kwargs: Any) -> None:
    """Log an exception with traceback."""
    import traceback
    kwargs['exception_type'] = type(exc).__name__
    kwargs['exception_message'] = str(exc)
    kwargs['traceback'] = traceback.format_exc()
    self._emit('ERROR', message, **kwargs)
