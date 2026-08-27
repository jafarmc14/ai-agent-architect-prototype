import streamlit as st

from agent import configure_llm_provider, get_agent_response, get_llm_config


PROVIDER_OPTIONS = {
    "OpenRouter": {
        "provider": "openrouter",
        "models": ["openrouter/free"],
    },
    "Ollama": {
        "provider": "ollama",
        "models": ["llama3.1", "qwen2.5", "mistral"],
    },
}

WELCOME_MESSAGE = "Hello, I'm Ubichinon. How can I help you today?"


def reset_ui_chat() -> None:
    st.session_state.messages = [
        {"role": "assistant", "content": WELCOME_MESSAGE}
    ]


st.set_page_config(
    page_title="Store AI-Agent Assistant",
    layout="centered",
)

st.title("Store AI-Agent Architect")
st.markdown("Autonomous AI assistant for e-commerce (Prototype).")

active_config = get_llm_config()
provider_labels = list(PROVIDER_OPTIONS.keys())
active_provider_label = next(
    (
        label
        for label, config in PROVIDER_OPTIONS.items()
        if config["provider"] == active_config["provider"]
    ),
    "OpenRouter",
)
active_provider_index = provider_labels.index(active_provider_label)

with st.sidebar:
    st.header("LLM Provider")

    selected_provider_label = st.selectbox(
        "Provider",
        options=provider_labels,
        index=active_provider_index,
    )
    selected_provider = PROVIDER_OPTIONS[selected_provider_label]["provider"]
    model_options = list(PROVIDER_OPTIONS[selected_provider_label]["models"])
    active_model = active_config["model"]
    if selected_provider == active_config["provider"] and active_model and active_model not in model_options:
        model_options.insert(0, active_model)
    active_model_index = model_options.index(active_model) if active_model in model_options else 0

    selected_model = st.selectbox(
        "Model",
        options=model_options,
        index=active_model_index,
    )

    provider_key = f"{selected_provider}:{selected_model}"
    if st.session_state.get("llm_provider_key") != provider_key:
        configure_llm_provider(selected_provider, selected_model)
        st.session_state.llm_provider_key = provider_key
        reset_ui_chat()

    current_config = get_llm_config()
    st.caption(f"Environment: {current_config['environment']}")
    st.caption(f"Active: {current_config['provider']} / {current_config['model']}")

    if selected_provider == "ollama":
        st.caption("Make sure Ollama is running at http://localhost:11434.")

if "messages" not in st.session_state:
    reset_ui_chat()

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Type your message here..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.spinner("Agent is thinking..."):
        response = get_agent_response(prompt)

    st.session_state.messages.append({"role": "assistant", "content": response})
    with st.chat_message("assistant"):
        st.markdown(response)
