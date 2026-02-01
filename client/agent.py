import os
import asyncio
from typing import Annotated, Literal, TypedDict, List, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.graph import StateGraph, END, START
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client

SERVER_URL = "http://mcp_server:8000/sse"

# Define Agent State
class AgentState(TypedDict):
    messages: List[Any]
    next_step: str

# Setup LLM
llm = ChatOpenAI(model="gpt-4o", temperature=0)

# --- Tool Helpers ---
async def call_mcp_tool(tool_name: str, arguments: dict = {}):
    """
    Calls an MCP tool on the server via SSE.
    """
    try:
        async with sse_client(SERVER_URL) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                return result
    except Exception as e:
        return f"Error calling tool {tool_name}: {e}"

async def ingest_codebase(repo_url: str):
    """
    Triggers the ingestion process.
    """
    print(f"Triggering ingestion for {repo_url}...")
    return await call_mcp_tool("ingest_repository", {"source": repo_url})

# --- Prompts ---

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

# --- Agent Roles ---

async def discoverer_agent(state: AgentState):
    """
    Scans the file list and identifies the tech stack.
    """
    messages = state['messages']
    
    # 1. Get file list from Graph
    # We query Memgraph for files to give context to the Agent
    files_result = await call_mcp_tool("cypher_query", {"query": "MATCH (f:File) RETURN f.path LIMIT 50"})
    
    # Inject context
    context_message = SystemMessage(content=f"## Codebase Context (Files identified):\n{files_result}")
    
    chain = discoverer_prompt | llm
    response = await chain.ainvoke({"messages": [context_message] + messages})
    return {"messages": [response], "next_step": "MAPPER"}

async def mapper_agent(state: AgentState):
    """
    Uses the Knowledge Graph (Memgraph) to map dependencies.
    """
    messages = state['messages']
    
    # In a full impl, we'd parse the LLM output to run tools.
    # For now, we rely on the pre-filled graph data.
    
    chain = mapper_prompt | llm
    response = await chain.ainvoke({"messages": messages})
    return {"messages": [response], "next_step": "SUMMARIZER"}

async def summarizer_agent(state: AgentState):
    """
    Writes the final user-facing answer.
    """
    messages = state['messages']
    chain = summarizer_prompt | llm
    response = await chain.ainvoke({"messages": messages})
    return {"messages": [response], "next_step": END}

# --- Workflow ---
workflow = StateGraph(AgentState)

workflow.add_node("discoverer", discoverer_agent)
workflow.add_node("mapper", mapper_agent)
workflow.add_node("summarizer", summarizer_agent)

workflow.add_edge(START, "discoverer")
workflow.add_edge("discoverer", "mapper")
workflow.add_edge("mapper", "summarizer")
workflow.add_edge("summarizer", END)

graph = workflow.compile()
