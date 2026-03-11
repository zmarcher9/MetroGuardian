import logging
import os
import sys


def setup_logging(log_level: str | None = None) -> None:
    """
    Configure logging for the entire application.
    
    Sets up structured logging with consistent format across all modules.
    This should be called early in application startup, before any other
    modules start logging.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
                  If None, reads from LOG_LEVEL env var or defaults to INFO.
    
    Features:
    - Consistent log format across all modules
    - Configurable log levels via env var or parameter
    - Proper uvicorn logging integration
    - Ready for production (can be extended with JSON logging, file handlers, etc.)
    """
    # Get log level from parameter, env var, or default to INFO
    if log_level is None:
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    # Convert string level to logging constant
    numeric_level = getattr(logging, log_level, logging.INFO)
    
    # Standard log format: timestamp | level | module | file:line | message
    log_format = (
        "%(asctime)s | %(levelname)-8s | %(name)s | "
        "%(filename)s:%(lineno)d | %(message)s"
    )
    
    # Date format for timestamps
    date_format = "%Y-%m-%d %H:%M:%S"
    
    # Configure root logger
    logging.basicConfig(
        level=numeric_level,
        format=log_format,
        datefmt=date_format,
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,  # Override any existing configuration
    )
    
    # Configure third-party loggers
    # Uvicorn access logs (HTTP requests)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").propagate = True
    
    # Uvicorn error logs
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("uvicorn.error").propagate = True
    
    # Reduce noise from some libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    
    # SQLAlchemy query logging (can be enabled via echo=True in engine)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    
    # Get logger for this module to log setup completion
    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured | level={log_level}")

