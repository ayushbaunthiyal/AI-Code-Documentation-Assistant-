"""
Streamlit UI - Codebase Reverse Engineer Agent
===============================================

This is the main user interface for the AI Code Documentation Assistant.
It provides a chat-based interface where users can:

1. Enter a GitHub repository URL for analysis
2. Watch the ingestion progress (cloning, parsing, graph building)
3. Ask questions about the codebase
4. View knowledge graph statistics

UI Flow:
    1. User enters GitHub URL → Click "Start Analysis"
    2. UI calls agent.ingest_codebase() → Shows progress status
    3. After ingestion, UI shows success + stats in sidebar
    4. User types questions in chat input
    5. Questions go through LangGraph agent pipeline
    6. Responses are displayed in chat format

Session State:
    - current_repo: The currently analyzed repository (None = input mode)
    - messages: Chat history (LangChain HumanMessage/AIMessage objects)
    - graph_stats: Cached (nodes, edges) tuple for sidebar display

Single-Repo Mode:
    The app enforces single-repo context - only one repository can be
    analyzed at a time. This prevents context confusion for the agent.
    Users must click "Change Repository" to analyze a different repo.
"""

import streamlit as st
import os
import io
from agent import graph, get_graph_stats
import asyncio
from langchain_core.messages import HumanMessage, AIMessage


# =============================================================================
# PAGE CONFIGURATION
# =============================================================================

# Set page title and layout (must be first Streamlit command)
st.set_page_config(page_title="AI Code Doc Assistant", layout="wide")


# =============================================================================
# SESSION STATE INITIALIZATION
# =============================================================================

# Session state must be initialized BEFORE any widgets that reference it
# This prevents "KeyError" when accessing st.session_state.current_repo

if "current_repo" not in st.session_state:
    # None = no repo loaded, show input form
    st.session_state.current_repo = None
    
if "messages" not in st.session_state:
    # Chat history - list of HumanMessage/AIMessage objects
    st.session_state.messages = []


# =============================================================================
# SIDEBAR - Settings and Stats
# =============================================================================

with st.sidebar:
    st.title("Settings")
    
    # OpenAI API Key input
    # Allows users to enter their key if not set via environment variable
    openai_key = st.text_input(
        "OpenAI API Key", 
        type="password", 
        value=os.getenv("OPENAI_API_KEY", "")
    )
    if openai_key:
        os.environ["OPENAI_API_KEY"] = openai_key
    
    # Knowledge Graph Statistics
    # Only shown when a repository is loaded
    if st.session_state.current_repo:
        st.divider()
        st.markdown("### 📊 Knowledge Graph")
        
        # Lazy-load stats: fetch from Memgraph if not cached
        if "graph_stats" not in st.session_state:
             import asyncio
             try:
                 # Query Memgraph for node and edge counts
                 st.session_state.graph_stats = asyncio.run(get_graph_stats())
             except Exception as e:
                 # Fallback to zeros on error
                 st.session_state.graph_stats = (0, 0)
        
        # Display stats as metrics
        n, e = st.session_state.graph_stats
        c1, c2 = st.columns(2)
        c1.metric("Nodes", n)
        c2.metric("Edges", e)
        
        # Manual refresh button
        if st.button("Refresh Stats"):
            del st.session_state.graph_stats
            st.rerun()


# =============================================================================
# MAIN CONTENT - Title
# =============================================================================

st.title("🔍 Codebase Reverse Engineer Agent")


# =============================================================================
# REPOSITORY INPUT / LOCKED STATE
# =============================================================================

if st.session_state.current_repo is None:
    # =========================================================================
    # INPUT MODE - No repository loaded
    # =========================================================================
    
    st.warning("Please upload/enter a GitHub Repository to start.")
    
    # GitHub URL input field
    repo_url = st.text_input(
        "GitHub Repository URL", 
        placeholder="https://github.com/user/repo"
    )
    
    # Start Analysis button
    confirm = st.button("Start Analysis")
    
    if confirm and repo_url:
        # Trigger ingestion with granular progress feedback
        with st.status("🚀 Processing Repository...", expanded=True) as status:
            import asyncio
            from agent import ingest_codebase
            
            # Step 1: Show cloning status
            st.write("🧹 Cleaning Database & 📦 Cloning Codebase...")
            
            try:
                # Step 2: Show parsing status
                st.write("⚙️ Parsing AST & Building Knowledge Graph (Memgraph)...")
                
                # Call the MCP tool via agent helper
                response = asyncio.run(ingest_codebase(repo_url))
                
                # Display the response from the ingestion tool
                # MCP returns TextContent objects, extract readable content
                st.code(
                    str(response.content if hasattr(response, 'content') else response), 
                    language="text"
                )
                
                # Step 3: Success
                st.write("✅ Knowledge Graph Built!")
                status.update(label="Ingestion Complete!", state="complete", expanded=False)
                
                # Lock the repository - user must click "Change" to switch
                st.session_state.current_repo = repo_url
                
                # Clear cached stats so sidebar fetches fresh values
                if "graph_stats" in st.session_state:
                    del st.session_state.graph_stats
                
            except Exception as e:
                # Handle ingestion failure
                st.error(f"Ingestion failed: {e}")
                status.update(label="Ingestion Failed", state="error")
                st.stop()
else:
    # =========================================================================
    # LOCKED MODE - Repository is loaded
    # =========================================================================
    
    # Show current repository
    st.success(f"Analyzing: **{st.session_state.current_repo}**")
    
    # Button to switch to a different repository
    if st.button("Change Repository"):
        st.session_state.current_repo = None
        st.session_state.messages = []  # Clear chat history
        st.rerun()


# =============================================================================
# CHAT INTERFACE
# =============================================================================

# Display existing chat messages
for msg in st.session_state.messages:
    if isinstance(msg, HumanMessage):
        with st.chat_message("user"):
            st.write(msg.content)
    elif isinstance(msg, AIMessage):
        with st.chat_message("assistant"):
            st.write(msg.content)

# Chat input field
if prompt := st.chat_input("Ask a question about the codebase..."):
    # Add user message to history
    st.session_state.messages.append(HumanMessage(content=prompt))
    
    # Display user message
    with st.chat_message("user"):
        st.write(prompt)

    # Run the LangGraph agent pipeline
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            # Prepare input for LangGraph
            inputs = {"messages": st.session_state.messages}
            
            # Invoke the compiled LangGraph workflow
            # This runs: DISCOVERER -> MAPPER -> SUMMARIZER
            import asyncio
            result = asyncio.run(graph.ainvoke(inputs))
            
            # Extract the final response (last message from summarizer)
            final_msg = result["messages"][-1]
            st.write(final_msg.content)
            
            # Add to chat history
            st.session_state.messages.append(final_msg)
