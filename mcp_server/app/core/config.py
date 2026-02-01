from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal

class Settings(BaseSettings):
    """
    Application Settings.
    Reads from environment variables or .env file.
    """
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    # Project Info
    PROJECT_NAME: str = "AI Code Documentation Assistant"
    VERSION: str = "1.0.0"
    ENVIRONMENT: Literal["local", "production"] = "local"
    LOG_LEVEL: str = "INFO"

    # Memgraph
    MEMGRAPH_HOST: str = "memgraph"
    MEMGRAPH_PORT: int = 7687
    MEMGRAPH_USER: str = "memgraph"
    MEMGRAPH_PASSWORD: str = "memgraph"
    MEMGRAPH_URI: str = "bolt://memgraph:7687"

    # MCP
    MCP_PORT: int = 8000
    MCP_HOST: str = "0.0.0.0"

settings = Settings()
