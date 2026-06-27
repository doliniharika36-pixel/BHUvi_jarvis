"""
Structured JSON Logger implementation for Jarvis OS.
"""
import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Optional
from jarvis_os.core.ports.config import ConfigurationPort
from jarvis_os.core.ports.logger import LoggerPort

# Thread-local storage for correlation context
_thread_local = threading.local()

def set_correlation_id(correlation_id: str) -> None:
    """Set the correlation/request ID for the current execution thread."""
    _thread_local.correlation_id = correlation_id

def get_correlation_id() -> Optional[str]:
    """Retrieve the correlation ID of the current execution thread."""
    return getattr(_thread_local, "correlation_id", None)

def clear_correlation_id() -> None:
    """Clear the correlation ID of the current execution thread."""
    if hasattr(_thread_local, "correlation_id"):
        delattr(_thread_local, "correlation_id")

@contextmanager
def correlation_context(correlation_id: str):
    """Context manager to scope a correlation ID to a specific block execution."""
    set_correlation_id(correlation_id)
    try:
        yield
    finally:
        clear_correlation_id()


class JsonFormatter(logging.Formatter):
    """Formats LogRecords into structured JSON Lines."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "filename": record.filename,
            "line": record.lineno,
        }

        # Inject correlation ID
        cid = get_correlation_id()
        if cid:
            log_data["correlation_id"] = cid

        # Inject structured metadata
        if hasattr(record, "metadata") and isinstance(record.metadata, dict): # type: ignore
            log_data["metadata"] = record.metadata # type: ignore
        else:
            log_data["metadata"] = {}

        # Inject error traceback if available
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


class ConsoleFormatter(logging.Formatter):
    """Formats LogRecords into clean, human-readable terminal output."""
    
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        cid = get_correlation_id()
        cid_str = f" [{cid}]" if cid else ""
        metadata_str = ""
        
        if hasattr(record, "metadata") and isinstance(record.metadata, dict) and record.metadata: # type: ignore
            meta_items = [f"{k}={v}" for k, v in record.metadata.items()] # type: ignore
            metadata_str = f" | {', '.join(meta_items)}"
            
        exc_str = ""
        if record.exc_info:
            exc_str = f"\n{self.formatException(record.exc_info)}"
            
        return f"[{timestamp}] [{record.levelname}]{cid_str} {record.getMessage()}{metadata_str}{exc_str}"


class StructuredLogger(LoggerPort):
    """Concrete structured logging system conforming to LoggerPort."""

    LEVEL_MAP = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }

    def __init__(self, config: ConfigurationPort):
        self._config = config
        self._logger = logging.getLogger("jarvis_os")
        self._logger.propagate = False  # Avoid duplicates with root loggers
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        """Configures file and console logging handlers dynamically based on configuration."""
        # Clear any existing handlers
        self._logger.handlers.clear()

        # Resolve level
        level_str = self._config.get_string("log.level", "INFO").upper()
        level = self.LEVEL_MAP.get(level_str, logging.INFO)
        self._logger.setLevel(level)

        # 1. Setup Rotating File Handler (JSON lines)
        log_file_path = self._config.get_string("log.file_path", "jarvis.log")
        log_path = Path(log_file_path).resolve()
        
        # Ensure log folder directory exists
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # 10 MB per file, max 3 backups to protect low disk space
        file_handler = RotatingFileHandler(
            filename=str(log_path),
            maxBytes=10 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8"
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(JsonFormatter())
        self._logger.addHandler(file_handler)

        # 2. Setup Console Handler (Human-readable text)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(ConsoleFormatter())
        self._logger.addHandler(console_handler)

    def debug(self, message: str, **kwargs: Any) -> None:
        self._logger.debug(message, extra={"metadata": kwargs})

    def info(self, message: str, **kwargs: Any) -> None:
        self._logger.info(message, extra={"metadata": kwargs})

    def warning(self, message: str, **kwargs: Any) -> None:
        self._logger.warning(message, extra={"metadata": kwargs})

    def error(self, message: str, error: Optional[Exception] = None, **kwargs: Any) -> None:
        # If an error object is passed, capture it into exc_info
        exc_info = (type(error), error, error.__traceback__) if error else None
        self._logger.error(message, exc_info=exc_info, extra={"metadata": kwargs})

    def critical(self, message: str, error: Optional[Exception] = None, **kwargs: Any) -> None:
        exc_info = (type(error), error, error.__traceback__) if error else None
        self._logger.critical(message, exc_info=exc_info, extra={"metadata": kwargs})

    def set_level(self, level: str) -> None:
        level_upper = level.upper()
        if level_upper in self.LEVEL_MAP:
            target_level = self.LEVEL_MAP[level_upper]
            self._logger.setLevel(target_level)
            for handler in self._logger.handlers:
                handler.setLevel(target_level)
        else:
            raise ValueError(f"Invalid log level: {level}")
