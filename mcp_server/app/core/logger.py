"""
Structured Logging Configuration
================================

This module configures structured logging using structlog.
Structured logging outputs logs as key-value pairs, making them:

1. Machine-parseable (JSON format in production)
2. Human-readable (colored output in local development)
3. Easily searchable in log aggregation systems (Datadog, ELK, CloudWatch)

Why Structlog over stdlib logging?
    - Contextual: Add context vars that propagate through async calls
    - Typed: Logs are dicts, not interpolated strings
    - Flexible: Same code outputs different formats based on environment

Usage:
    from app.core.logger import logger
    
    logger.info("User action", user_id=123, action="login")
    # Local:  2024-01-15 10:30:00 [info] User action  user_id=123 action=login
    # Prod:   {"event": "User action", "user_id": 123, "action": "login", "level": "info"}
"""

import structlog
import logging
import sys
from app.core.config import settings


def configure_logger():
    """
    Configures the global structlog logger based on environment.
    
    This function MUST be called before any logging occurs, typically
    at the very start of main.py. It sets up the processing pipeline
    that transforms log calls into formatted output.
    
    Processing Pipeline:
        1. merge_contextvars: Include async context variables
        2. add_log_level: Add 'level' key to each log
        3. StackInfoRenderer: Include stack traces for exceptions
        4. set_exc_info: Attach exception info if logging an error
        5. TimeStamper: Add ISO timestamp
        6. ConsoleRenderer/JSONRenderer: Final formatting
    
    Environment Behavior:
        - local: Pretty-printed, colored output for developer readability
        - production: JSON output for log aggregation systems
    """
    
    # Define the log processing pipeline
    # Each processor transforms the log event dict before passing to the next
    processors = [
        # Merge any context variables (useful for request_id tracking)
        structlog.contextvars.merge_contextvars,
        
        # Add 'level' key: {"level": "info", ...}
        structlog.processors.add_log_level,
        
        # Include stack info for debugging
        structlog.processors.StackInfoRenderer(),
        
        # Add exception info to log events
        structlog.dev.set_exc_info,
        
        # Add ISO timestamp: {"timestamp": "2024-01-15T10:30:00Z", ...}
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    # Add environment-specific final renderer
    if settings.ENVIRONMENT == "local":
        # Pretty printing with colors for local development
        # Makes logs easy to read in terminal during development
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        # JSON logs for production
        # Compatible with log aggregation: Datadog, ELK, CloudWatch, Grafana
        processors.append(structlog.processors.JSONRenderer())

    # Apply the configuration globally
    structlog.configure(
        processors=processors,
        
        # Filter logs below the configured level (INFO by default)
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.LOG_LEVEL)
        ),
        
        # Use plain dict for log events (fastest)
        context_class=dict,
        
        # Output to stdout (Docker-friendly - logs accessible via docker logs)
        logger_factory=structlog.PrintLoggerFactory(),
        
        # Cache the logger after first use for performance
        cache_logger_on_first_use=True,
    )


# =============================================================================
# Global Logger Instance
# =============================================================================

# Get the configured logger instance
# Import this in other modules: `from app.core.logger import logger`
# Note: configure_logger() must be called before first use
logger = structlog.get_logger()
