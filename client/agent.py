"""
LangGraph Multi-Agent System
============================

This module implements the core AI agent system using LangGraph.
It defines a three-stage pipeline that processes user questions:

    DISCOVERER → MAPPER → SUMMARIZER

Agent Pipeline:
    1. DISCOVERER: Scans file structure, identifies tech stack
    2. MAPPER: Queries Memgraph for classes, functions, endpoints
    3. SUMMARIZER: Synthesizes findings into user-friendly answer

Architecture:
    ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
    │ DISCOVERER  │ ──► │   MAPPER    │ ──► │ SUMMARIZER  │
    │ (tech scan) │     │ (graph query│     │ (synthesis) │
    └─────────────┘     └─────────────┘     └─────────────┘
          │                    │                    │
          └────────────────────┼────────────────────┘
                               ▼
                        [MCP Server]
                               │
                               ▼
                         [Memgraph]

MCP Integration:
    The agents communicate with the MCP server via SSE (Server-Sent Events).
    Two tools are available:
    - ingest_repository: Clone and parse a codebase
    - cypher_query: Execute Cypher queries against the knowledge graph

Why LangGraph?
    - State management: Tracks messages across agent transitions
    - Async support: Non-blocking tool calls
    - Composability: Easy to add/remove agents
    - Debugging: Clear step-by-step execution

Usage:
    from agent import graph
    result = asyncio.run(graph.ainvoke({"messages": [HumanMessage(content="What does this code do?")]}))
"""

import os
import asyncio
import ast
from typing import Annotated, Literal, TypedDict, List, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.graph import StateGraph, END, START
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client


# =============================================================================
# CONFIGURATION
# =============================================================================

# MCP Server URL - Docker service name resolves to container IP
SERVER_URL = "http://mcp_server:8000/sse"


# =============================================================================
# STATE DEFINITION
# =============================================================================

class AgentState(TypedDict):
    """
    State passed between agents in the LangGraph workflow.
    
    Attributes:
        messages: List of chat messages (HumanMessage, AIMessage, SystemMessage)
        next_step: The next agent to invoke (used by LangGraph routing)
    """
    messages: List[Any]
    next_step: str


# =============================================================================
# LLM SETUP
# =============================================================================

# Initialize the language model
# GPT-4o chosen for:
# - Strong code understanding
# - Tool-use capabilities
# - Reasoning for multi-step analysis
llm = ChatOpenAI(model="gpt-4o", temperature=0)


# =============================================================================
# MCP TOOL HELPERS
# These functions wrap MCP tool calls for cleaner agent code
# =============================================================================

async def call_mcp_tool(tool_name: str, arguments: dict = {}) -> Any:
    """
    Call an MCP tool on the server via SSE transport.
    
    This is the bridge between LangGraph agents and the MCP server.
    It establishes an SSE connection, initializes a session, and
    invokes the requested tool.
    
    Args:
        tool_name: Name of the MCP tool ("ingest_repository" or "cypher_query")
        arguments: Dictionary of arguments to pass to the tool
        
    Returns:
        Tool result (typically a CallToolResult with content list)
        
    Example:
        >>> result = await call_mcp_tool("cypher_query", {"query": "MATCH (n) RETURN count(n)"})
        >>> result.content[0].text
        "[{'count(n)': 42}]"
    """
    try:
        # Establish SSE connection to MCP server
        async with sse_client(SERVER_URL) as (read, write):
            # Create MCP client session
            async with ClientSession(read, write) as session:
                # Initialize the session (required by MCP protocol)
                await session.initialize()
                # Call the tool and return result
                result = await session.call_tool(tool_name, arguments)
                return result
    except Exception as e:
        return f"Error calling tool {tool_name}: {e}"


async def ingest_codebase(repo_url: str) -> Any:
    """
    Trigger repository ingestion via MCP tool.
    
    This is called when the user clicks "Start Analysis" in the UI.
    It invokes the ingest_repository tool which:
    1. Clones the repository
    2. Parses all source files
    3. Builds the knowledge graph in Memgraph
    
    Args:
        repo_url: GitHub repository URL (https://github.com/user/repo)
        
    Returns:
        MCP tool result with ingestion statistics
    """
    print(f"Triggering ingestion for {repo_url}...")
    return await call_mcp_tool("ingest_repository", {"source": repo_url})


async def get_graph_stats() -> tuple:
    """
    Fetch node and edge counts from the knowledge graph.
    
    Used by the sidebar to display graph statistics.
    Executes two Cypher queries to count nodes and relationships.
    
    Returns:
        Tuple of (node_count, edge_count)
        
    Note:
        MCP tool results are wrapped in TextContent objects.
        We extract the text and parse it as Python literals.
    """
    try:
        # Query node count
        n_res = await call_mcp_tool("cypher_query", {"query": "MATCH (n) RETURN count(n) as c"})
        # Query edge count
        e_res = await call_mcp_tool("cypher_query", {"query": "MATCH ()-[r]->() RETURN count(r) as c"})
        
        def extract_text(result) -> str:
            """
            Extract text content from MCP tool result.
            
            MCP returns CallToolResult with a content list of TextContent objects.
            This helper handles various result formats gracefully.
            """
            if hasattr(result, 'content'):
                # It's a CallToolResult with content list
                if isinstance(result.content, list) and len(result.content) > 0:
                    return result.content[0].text
                return str(result.content)
            elif isinstance(result, list) and len(result) > 0:
                if hasattr(result[0], 'text'):
                    return result[0].text
                return str(result[0])
            return str(result)
        
        # Extract text from results
        n_text = extract_text(n_res)
        e_text = extract_text(e_res)
        
        # Parse string result: "[{'c': 123}]" -> 123
        n_val = ast.literal_eval(n_text)[0]['c']
        e_val = ast.literal_eval(e_text)[0]['c']
        return n_val, e_val
        
    except Exception as e:
        print(f"Stats error: {e}")
        return 0, 0


# =============================================================================
# AGENT PROMPTS
# These define the persona and instructions for each agent
# =============================================================================

discoverer_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are the DISCOVERER, an elite Software Architect specializing in Codebase Reconnaissance.
    
    YOUR GOAL: 
    Scan the provided file structure to identify the **Technology Stack**, **Frameworks**, and **Entry Points**.
    
    INSTRUCTIONS:
    1. Look for configuration files (package.json, pyproject.toml, go.mod, pom.xml, docker-compose.yml).
    2. Identify the core programming languages.
    3. Locate the main entry point (main.py, index.js, App.java).
    4. Do NOT attempt to explain detailed logic yet. Focus on the high-level topology.
    
    Output a concise summary of your findings and explicitly state "Handing over to MAPPER" when done.
    """),
    MessagesPlaceholder(variable_name="messages"),
])

mapper_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are the MAPPER, a Senior Backend Engineer specializing in Dependency Graph Analysis.
    
    YOUR GOAL:
    Understand the **Internal Structure** and **Data Flow** of the system using the Knowledge Graph.
    
    INSTRUCTIONS:
    1. Use `cypher_query` to visualize relationships.
    2. Identify key Classes, Functions, and Models.
    3. Trace the flow of data from API Endpoints to Database Models.
    4. Focus on "How things are connected".
    
    Example Query: "MATCH (c:Class)-[:INHERITS]->(p) RETURN c.name, p.name"
    
    Once you have a mental model, summarize the architecture and state "Handing over to SUMMARIZER".
    """),
    MessagesPlaceholder(variable_name="messages"),
])

summarizer_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are the SUMMARIZER, a Technical Writer and Developer Advocate.
    
    YOUR GOAL:
    Synthesize the technical findings into a clear, natural language explanation for the user.
    
    INSTRUCTIONS:
    1. Read the reports from the DISCOVERER and MAPPER.
    2. Answer the user's original question directly.
    3. Use code blocks, bullet points, and clear English.
    4. Explain **"How it works"**, **"Where it lives"**, and **"Why it matters"**.
    5. Do NOT use jargon without explanation.
    
    This is the final response to the user.
    """),
    MessagesPlaceholder(variable_name="messages"),
])


# =============================================================================
# AGENT FUNCTIONS
# Each function is a node in the LangGraph workflow
# =============================================================================

async def discoverer_agent(state: AgentState) -> dict:
    """
    DISCOVERER: First agent in the pipeline.
    
    Purpose:
        Scan the file list and identify the technology stack.
        Provides high-level context for subsequent agents.
    
    Process:
        1. Query Memgraph for file list (up to 50 files)
        2. Inject file list as context into the prompt
        3. Ask LLM to identify tech stack and entry points
        4. Return findings for MAPPER
    
    Args:
        state: Current agent state with messages
        
    Returns:
        Updated state with discoverer's response and next_step="MAPPER"
    """
    messages = state['messages']
    
    # Query Memgraph for files to give context to the Agent
    files_result = await call_mcp_tool(
        "cypher_query", 
        {"query": "MATCH (f:File) RETURN f.path LIMIT 50"}
    )
    
    # Create context message with file list
    context_message = SystemMessage(
        content=f"## Codebase Context (Files identified):\n{files_result}"
    )
    
    # Run the LLM with discoverer prompt
    chain = discoverer_prompt | llm
    response = await chain.ainvoke({"messages": [context_message] + messages})
    
    return {"messages": [response], "next_step": "MAPPER"}


async def mapper_agent(state: AgentState) -> dict:
    """
    MAPPER: Second agent in the pipeline.
    
    Purpose:
        Query the knowledge graph to understand code structure.
        Extracts classes, functions, endpoints, and their relationships.
    
    Process:
        1. Execute multiple Cypher queries to fetch graph data
        2. Build a comprehensive context message with REAL data
        3. Ask LLM to analyze the structure
        4. Return findings for SUMMARIZER
    
    Key Queries:
        - Classes: MATCH (c:Class) RETURN c.name
        - Functions: MATCH (f:Function) RETURN f.name
        - Endpoints: MATCH (e:Endpoint) RETURN e.name, e.route
        - Files: MATCH (f:File) RETURN f.path, f.language
        - Relationships: MATCH (n)-[:DEFINED_IN]->(f) RETURN type, name, path
    
    Args:
        state: Current agent state with messages
        
    Returns:
        Updated state with mapper's response and next_step="SUMMARIZER"
    """
    messages = state['messages']
    
    # Query the ACTUAL graph for real data
    try:
        # Get all classes
        classes_result = await call_mcp_tool(
            "cypher_query", 
            {"query": "MATCH (c:Class) RETURN c.name LIMIT 20"}
        )
        
        # Get all functions
        functions_result = await call_mcp_tool(
            "cypher_query", 
            {"query": "MATCH (f:Function) RETURN f.name LIMIT 30"}
        )
        
        # Get API endpoints (FastAPI routes)
        endpoints_result = await call_mcp_tool(
            "cypher_query", 
            {"query": "MATCH (e:Endpoint) RETURN e.name, e.route LIMIT 20"}
        )
        
        # Get all files with their language
        files_result = await call_mcp_tool(
            "cypher_query", 
            {"query": "MATCH (f:File) RETURN f.path, f.language LIMIT 30"}
        )
        
        # Get relationships (what is defined where)
        relationships_result = await call_mcp_tool(
            "cypher_query", 
            {"query": "MATCH (n)-[:DEFINED_IN]->(f:File) RETURN labels(n)[0] as type, n.name, f.path LIMIT 30"}
        )
        
        # Build context message with REAL data from the knowledge graph
        # This is injected into the LLM to prevent hallucination
        context = f"""## ACTUAL DATA FROM CODEBASE (Memgraph Knowledge Graph):

### Files in Repository:
{files_result}

### API Endpoints (FastAPI Routes):
{endpoints_result}

### Classes:
{classes_result}

### Functions:
{functions_result}

### Code Structure (What is defined where):
{relationships_result}

CRITICAL INSTRUCTIONS:
1. Use ONLY the data above to answer questions
2. If asked about language: Look at file extensions (.py = Python, .js = JavaScript, etc.)
3. If asked about endpoints: List the actual routes from 'API Endpoints' section
4. Do NOT make up information not present above
5. Be CONCISE - answer in 2-3 sentences unless more detail is requested"""
        
        context_message = SystemMessage(content=context)
        
    except Exception as e:
        # Fallback context if graph query fails
        context_message = SystemMessage(content=f"Error querying graph: {e}")
    
    # Run the LLM with mapper prompt
    chain = mapper_prompt | llm
    response = await chain.ainvoke({"messages": [context_message] + messages})
    
    return {"messages": [response], "next_step": "SUMMARIZER"}


async def summarizer_agent(state: AgentState) -> dict:
    """
    SUMMARIZER: Final agent in the pipeline.
    
    Purpose:
        Synthesize findings from DISCOVERER and MAPPER into
        a clear, user-friendly answer.
    
    Process:
        1. Read all previous messages (including agent findings)
        2. Answer the user's original question directly
        3. Format response with clear structure
    
    Output Format:
        - How it works: Technical explanation
        - Where it lives: File/module locations
        - Why it matters: Business/architectural significance
    
    Args:
        state: Current agent state with all messages
        
    Returns:
        Updated state with final response and next_step=END
    """
    messages = state['messages']
    
    # Run the LLM with summarizer prompt
    chain = summarizer_prompt | llm
    response = await chain.ainvoke({"messages": messages})
    
    return {"messages": [response], "next_step": END}


# =============================================================================
# LANGGRAPH WORKFLOW DEFINITION
# =============================================================================

# Create the state graph
workflow = StateGraph(AgentState)

# Add agent nodes
workflow.add_node("discoverer", discoverer_agent)
workflow.add_node("mapper", mapper_agent)
workflow.add_node("summarizer", summarizer_agent)

# Define edges (execution order)
# START -> discoverer -> mapper -> summarizer -> END
workflow.add_edge(START, "discoverer")
workflow.add_edge("discoverer", "mapper")
workflow.add_edge("mapper", "summarizer")
workflow.add_edge("summarizer", END)

# Compile the workflow into an executable graph
# This is the main entry point for running agent queries
graph = workflow.compile()
