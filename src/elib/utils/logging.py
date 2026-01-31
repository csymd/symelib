"""
src/elib/utils/logging.py
"""
from __future__ import annotations

import os
import json

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
from typer.models import OptionInfo

from elib.utils.config import Config

# ================================================== #
# Log Level Enum                                     #
# ================================================== #

class LogLevel(str, Enum):
    OFF = 'OFF'
    DEBUG = 'DEBUG'
    INFO = 'INFO'
    WARNING = 'WARNING'
    ERROR = 'ERROR'
    CRITICAL = 'CRITICAL'


# ================================================== #
# LoggerConfig Model                                 #
# ================================================== #

class LoggerConfig(BaseModel):
    name: Optional[str] = Field(default=None, description='Name of the logger')
    service: Optional[str] = Field(default=None, description='Service name for the logger')
    env: Optional[str] = Field(default=None, description='Environment (e.g., DEV, PROD)')
    level: LogLevel = Field(default=LogLevel.INFO, description='Log level')

# ================================================== #
# Simple Logger                                      #
# ================================================== #

_logger_instance: Optional[eLibLogger] = None

class eLibLogger:
    """
    A minimal JSON logger for structured logging.
    """
    def __init__(self, config: LoggerConfig):
        self.name = config.name or os.getenv('ELIB_SERVICE_NAME', 'eLibApp')
        self.service = config.service or os.getenv('ELIB_SERVICE_NAME', 'eLibApp')
        self.env = config.env or os.getenv('LOG_ENV', 'DEV')
        self.level = config.level
        self.level_order = [log_level.value for log_level in LogLevel]

    def _should_log(self, level: LogLevel) -> bool:
        """Check if the log level is high enough to log."""
        if self.level == LogLevel.OFF:
            return False
        return self.level_order.index(level.value) >= self.level_order.index(self.level.value)

    def _emit(self, level: LogLevel, message: str, **kwargs: Any) -> None:
        """Emit a log message as a JSON object."""
        if not self._should_log(level):
            return
        log_entry = {
            'level': level.value,
            'message': message,
            'service': self.service,
        }
        log_entry.update(kwargs)
        print(json.dumps(log_entry), flush=True)

    def debug(self, message: str, **kwargs: Any) -> None:
        self._emit(LogLevel.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        self._emit(LogLevel.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        self._emit(LogLevel.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        self._emit(LogLevel.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs: Any) -> None:
        self._emit(LogLevel.CRITICAL, message, **kwargs)

    def exception(self, message: str, exc: Exception, **kwargs: Any) -> None:
        """Log an exception with traceback."""
        import traceback
        kwargs['exception_type'] = type(exc).__name__
        kwargs['exception_message'] = str(exc)
        kwargs['traceback'] = traceback.format_exc()
        self._emit(LogLevel.ERROR, message, **kwargs)


def initialize_logger(
        verbose: int,
        quiet: bool,
        log_level: Optional[LogLevel] = None,
    ) -> tuple[Config, eLibLogger]:
    """
    Initialize the logger and configuration.

    Args:
        verbose (int): Verbosity level (0-3).
        quiet (bool): If True, suppress output.
        log_level (Optional[LogLevel]): Explicit log level.

    Returns:
        tuple[Config, eLibLogger]: Loaded configuration and logger instance.
    """
    # Load Config
    config = Config.load()

    # Protect against OptionInfo being passed in from CLI and crashing Pydantic
    if isinstance(log_level, OptionInfo):
        log_level = None

    # Determine log level
    if log_level is not None:
        level = log_level
    elif quiet:
        level = LogLevel.ERROR
    elif verbose >= 3:
        level = LogLevel.DEBUG
    elif verbose == 2:
        level = LogLevel.DEBUG
    elif verbose == 1:
        level = LogLevel.INFO
    elif os.getenv('LOG_LEVEL'):
        level = os.getenv('LOG_LEVEL').upper()
    elif os.getenv('LOG_ENV'):
        env_to_level = {
            'PROD': LogLevel.ERROR,
            'STAGING': LogLevel.WARNING,
            'DEV': LogLevel.DEBUG,
            'TEST': LogLevel.INFO,
        }
        level = env_to_level.get(os.getenv('LOG_ENV', '').upper(), LogLevel.INFO)
    else:
        level = LogLevel.INFO

    # Logger Configuration and initialization
    logger_config = LoggerConfig(level=level)
    logger = get_shared_logger(config=logger_config)
    logger.debug('CLI initialized', log_level=level, verbose_count=verbose, quiet=quiet, explicit_log_level=log_level)

    return config, logger


def get_shared_logger(config: LoggerConfig) -> eLibLogger:
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
        _logger_instance = eLibLogger(config=config)
    else:
        _logger_instance.name = config.name
        _logger_instance.service = config.service
        _logger_instance.env = config.env
        _logger_instance.level = config.level
    return _logger_instance
