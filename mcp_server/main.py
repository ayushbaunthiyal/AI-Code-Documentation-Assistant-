from fastmcp import FastMCP
from app.core.config import settings
from app.core.logger import configure_logger, logger
from app.services.graph_service import GraphService

# Setup
configure_logger()
mcp = FastMCP(settings.PROJECT_NAME)
graph_service = GraphService()

@mcp.tool()
def ingest_repository(source: str) -> str:
    """Ingests a repository (Git URL or local path)."""
    logger.info(f"TOOL CALL: ingest_repository with source={source}")
    return graph_service.ingest_repository(source)

@mcp.tool()
def cypher_query(query: str) -> str:
    """Executes a Cypher query."""
    try:
        results = graph_service.execute_cypher(query)
        return str(results)
    except Exception as e:
        return str(e)

if __name__ == "__main__":
    logger.info("Starting MCP Server", port=settings.MCP_PORT, environment=settings.ENVIRONMENT)
    mcp.settings.port = settings.MCP_PORT
    mcp.settings.host = settings.MCP_HOST
    mcp.run(transport="sse")
