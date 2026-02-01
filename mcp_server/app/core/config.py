"""
Application Configuration
=========================

This module provides centralized configuration management using Pydantic Settings.
All configuration is validated at application startup, ensuring type safety and
catching missing required values early (fail-fast principle).

Configuration Sources (in priority order):
    1. Environment variables
    2. .env file (if present)
    3. Default values defined in the Settings class

Usage:
    from app.core.config import settings
    print(settings.MEMGRAPH_HOST)  # "memgraph"
    
Benefits of Pydantic Settings:
    - Type validation: PORT must be int, not "8000"
    - Required field enforcement: App won't start without OPENAI_API_KEY
    - IDE autocomplete: settings.MEM<tab> works
    - Immutability: Can't accidentally modify settings at runtime
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    """
    Application Settings with validation.
    
    This class defines ALL configuration variables used by the MCP server.
    Pydantic validates types and presence at instantiation time, meaning
    if a required variable is missing, the app fails immediately on startup
    rather than failing later when the variable is first used.
    
    Environment Variable Mapping:
        - Class attribute names are automatically mapped to env vars
        - MEMGRAPH_HOST in class -> MEMGRAPH_HOST env var
        - Underscores in names stay as underscores
    
    Attributes:
        PROJECT_NAME: Display name for the MCP server
        VERSION: Semantic version string
        ENVIRONMENT: "local" for dev, "production" for deployed
        LOG_LEVEL: Logging verbosity (DEBUG, INFO, WARNING, ERROR)
        MEMGRAPH_*: Database connection settings
        MCP_*: Server binding settings
    """
    
    # Pydantic model configuration
    # - env_file: Load from .env file if it exists
    # - env_ignore_empty: Treat empty strings as missing
    # - extra: Ignore unknown environment variables
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_ignore_empty=True, 
        extra="ignore"
    )

    # =========================================================================
    # Project Metadata
    # =========================================================================
    
    PROJECT_NAME: str = "AI Code Documentation Assistant"
    VERSION: str = "1.0.0"
    
    # Environment affects logging format (pretty vs JSON)
    ENVIRONMENT: Literal["local", "production"] = "local"
    
    # Standard Python logging levels
    LOG_LEVEL: str = "INFO"

    # =========================================================================
    # Memgraph Database Connection
    # =========================================================================
    
    # Docker service name resolves to container IP
    MEMGRAPH_HOST: str = "memgraph"
    
    # Bolt protocol port (default for Memgraph/Neo4j)
    MEMGRAPH_PORT: int = 7687
    
    # Authentication credentials (set via docker-compose environment)
    MEMGRAPH_USER: str = "memgraph"
    MEMGRAPH_PASSWORD: str = "memgraph"
    
    # Full connection URI (used by some clients)
    MEMGRAPH_URI: str = "bolt://memgraph:7687"

    # =========================================================================
    # MCP Server Settings
    # =========================================================================
    
    # Port the FastMCP SSE server listens on
    MCP_PORT: int = 8000
    
    # Host binding - 0.0.0.0 allows connections from other containers
    MCP_HOST: str = "0.0.0.0"


# =============================================================================
# Singleton Settings Instance
# =============================================================================

# Create a single settings instance at module load time
# This validates all configuration immediately when the app starts
# Import this instance: `from app.core.config import settings`
settings = Settings()
