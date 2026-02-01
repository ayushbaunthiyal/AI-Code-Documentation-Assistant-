"""
MCP Server Entry Point
======================

This module is the main entry point for the Model Context Protocol (MCP) server.
It exposes two tools that can be called by the LangGraph agent running in the client:

1. `ingest_repository(source)` - Clones and parses a codebase into the Memgraph knowledge graph
2. `cypher_query(query)` - Executes Cypher queries against the knowledge graph

Architecture:
    Client (Streamlit) --> SSE --> FastMCP Server --> GraphService --> Memgraph
    
The server runs on SSE (Server-Sent Events) transport, enabling HTTP-based
tool invocations from the client container over Docker's internal network.

Usage:
    python main.py  # Starts the SSE server on port 8000
"""

from fastmcp import FastMCP
from app.core.config import settings
from app.core.logger import configure_logger, logger
from app.services.graph_service import GraphService

# =============================================================================
# INITIALIZATION
# =============================================================================

# Configure structured logging (JSON in production, colored in local dev)
configure_logger()

# Initialize the FastMCP server with the project name
# FastMCP wraps our tools and exposes them via SSE/HTTP
mcp = FastMCP(settings.PROJECT_NAME)

# Initialize the GraphService which handles all Memgraph interactions
# This is a singleton-like instance used by all tool calls
graph_service = GraphService()


# =============================================================================
# MCP TOOLS
# These tools are exposed to the LangGraph agent and can be invoked remotely
# =============================================================================

@mcp.tool()
def ingest_repository(source: str) -> str:
    """
    Ingests a repository into the Memgraph knowledge graph.
    
    This is the main entry point for codebase analysis. When a user provides
    a GitHub URL or local path, this tool:
    
    1. Clones the repository (if URL) to a temp directory
    2. Clears the existing database (single-repo mode)
    3. Walks all files in the repository
    4. Parses supported files (Python, JS) using Tree-sitter AST
    5. Extracts Classes, Functions, and API Endpoints
    6. Stores them as nodes in Memgraph with DEFINED_IN relationships
    
    Args:
        source: Either a Git URL (https://github.com/...) or local filesystem path
        
    Returns:
        Success message with file count and graph statistics,
        or error message if ingestion fails
        
    Example:
        ingest_repository("https://github.com/user/repo")
        # Returns: "Ingestion Complete. Processed 42 files. Graph: 150 Nodes, 45 Edges."
    """
    logger.info(f"TOOL CALL: ingest_repository with source={source}")
    return graph_service.ingest_repository(source)


@mcp.tool()
def cypher_query(query: str) -> str:
    """
    Executes a Cypher query against the Memgraph knowledge graph.
    
    This tool enables the LangGraph agent to query the code structure.
    The agent uses this to answer user questions by fetching:
    - List of files: MATCH (f:File) RETURN f.path
    - List of classes: MATCH (c:Class) RETURN c.name
    - API endpoints: MATCH (e:Endpoint) RETURN e.name, e.route
    - Relationships: MATCH (n)-[:DEFINED_IN]->(f) RETURN n.name, f.path
    
    Args:
        query: A valid Cypher query string
        
    Returns:
        String representation of query results (list of dicts),
        or error message if query fails
        
    Example:
        cypher_query("MATCH (c:Class) RETURN c.name LIMIT 5")
        # Returns: "[{'c.name': 'Book'}, {'c.name': 'User'}]"
    """
    try:
        results = graph_service.execute_cypher(query)
        return str(results)
    except Exception as e:
        return str(e)


# =============================================================================
# MAIN EXECUTION
# =============================================================================

if __name__ == "__main__":
    # Log startup information for debugging and monitoring
    logger.info(
        "Starting MCP Server", 
        port=settings.MCP_PORT, 
        environment=settings.ENVIRONMENT
    )
    
    # Configure the FastMCP server settings
    mcp.settings.port = settings.MCP_PORT
    mcp.settings.host = settings.MCP_HOST
    
    # Run the server with SSE transport
    # SSE (Server-Sent Events) is chosen over stdio because:
    # 1. Works with Docker networking (HTTP-based)
    # 2. Enables multiple concurrent connections
    # 3. Better for debugging (can curl the endpoints)
    mcp.run(transport="sse")
