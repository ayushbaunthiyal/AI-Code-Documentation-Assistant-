import streamlit as st
import os
import io
from agent import graph
from langchain_core.messages import HumanMessage, AIMessage

# Page Config
st.set_page_config(page_title="AI Code Doc Assistant", layout="wide")

# Sidebar
with st.sidebar:
    st.title("Settings")
    openai_key = st.text_input("OpenAI API Key", type="password", value=os.getenv("OPENAI_API_KEY", ""))
    if openai_key:
        os.environ["OPENAI_API_KEY"] = openai_key

# Session State for Single Repo
if "current_repo" not in st.session_state:
    st.session_state.current_repo = None
if "messages" not in st.session_state:
    st.session_state.messages = []

st.title("🔍 codebase Reverse Engineer Agent")

# Repo Input Area
if st.session_state.current_repo is None:
    st.warning("Please upload/enter a GitHub Repository to start.")
    repo_url = st.text_input("GitHub Repository URL", placeholder="https://github.com/user/repo")
    
    confirm = st.button("Start Analysis")
    if confirm and repo_url:
        # Trigger Ingestion with Granular Feedback
        with st.status("🚀 Processing Repository...", expanded=True) as status:
            import asyncio
            from agent import ingest_codebase
            
            st.write("📦 Cloning codebase...")
            try:
                st.write("⚙️ Parsing AST & Building Knowledge Graph (Memgraph)...")
                
                # Check if we already have it? No, always ingest for now.
                response = asyncio.run(ingest_codebase(repo_url))
                
                # Extract content from ToolResult if needed, or just print response
                # MCP tool result is usually an object or list.
                # Our agent helper returns the raw result.
                st.code(str(response.content if hasattr(response, 'content') else response), language="text")
                
                st.write("✅ Knowledge Graph Built!")
                status.update(label="Ingestion Complete!", state="complete", expanded=False)
                
                # NOW set the state to locked
                st.session_state.current_repo = repo_url
                
            except Exception as e:
                st.error(f"Ingestion failed: {e}")
                status.update(label="Ingestion Failed", state="error")
                st.stop()
else:
    # Locked State
    st.success(f"Analyzing: **{st.session_state.current_repo}**")
    if st.button("Change Repository"):
        st.session_state.current_repo = None
        st.session_state.messages = []
        st.rerun()

# Chat Interface
for msg in st.session_state.messages:
    if isinstance(msg, HumanMessage):
        with st.chat_message("user"):
            st.write(msg.content)
    elif isinstance(msg, AIMessage):
        with st.chat_message("assistant"):
            st.write(msg.content)

if prompt := st.chat_input("Ask a question about the codebase..."):
    # Add user message
    st.session_state.messages.append(HumanMessage(content=prompt))
    with st.chat_message("user"):
        st.write(prompt)

    # Run Agent
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            inputs = {"messages": st.session_state.messages}
            import asyncio
            inputs = {"messages": st.session_state.messages}
            result = asyncio.run(graph.ainvoke(inputs))
            
            # Get final response
            final_msg = result["messages"][-1]
            st.write(final_msg.content)
            
            # Update history
            st.session_state.messages.append(final_msg)
