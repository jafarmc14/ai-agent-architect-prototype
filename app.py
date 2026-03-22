import streamlit as st
from agent import get_agent_response

# Page configuration
st.set_page_config(
    page_title="Store AI-Agent Assistant",
    page_icon="🤖",
    layout="centered"
)

st.title("🤖 Store AI-Agent Architect")
st.markdown("Autonomous AI assistant for e-commerce (Prototype).")

# Initialize chat history in session_state
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Hello! I'm the Store's virtual assistant. How can I help you with product stock or your order today?"}
    ]

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# User input
if prompt := st.chat_input("Type your message here... e.g. 'Check Nike shoe stock'"):
    # Add and display user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Integration with the Orchestrator (LangChain AI Agent)
    with st.spinner("🧠 Agent is thinking..."):
        response = get_agent_response(prompt)
    
    # Add and display assistant message
    st.session_state.messages.append({"role": "assistant", "content": response})
    with st.chat_message("assistant"):
        st.markdown(response)
