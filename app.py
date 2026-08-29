import streamlit as st
from uuid import uuid4

from agent import configure_llm_provider, get_agent_response, get_llm_config
from core.auth import create_session_token, verify_session_token
from core.repositories.user_repository import UserRepository


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

if "session_id" not in st.session_state:
    st.session_state.session_id = f"streamlit-{uuid4()}"

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
    st.caption(f"Database: {current_config['database_provider']}")
    st.caption(f"Active: {current_config['provider']} / {current_config['model']}")

    if selected_provider == "ollama":
        st.caption("Make sure Ollama is running at http://localhost:11434.")

    st.header("Session")
    demo_users = []
    try:
        if current_config["database_provider"] == "postgres":
            demo_users = UserRepository().list_customer_users()
    except Exception:
        demo_users = []

    if demo_users:
        user_labels = [f"{user['name']} ({user['email']})" for user in demo_users]
        selected_user_label = st.selectbox("Authenticated user", options=user_labels)
        selected_user = demo_users[user_labels.index(selected_user_label)]
        auth_user_key = str(selected_user["id"])
        if st.session_state.get("auth_user_key") != auth_user_key:
            st.session_state.auth_token = create_session_token(
                user_id=str(selected_user["id"]),
                email=selected_user.get("email") or "",
                name=selected_user.get("name") or "",
                role="customer",
                tenant_id=(selected_user.get("metadata") or {}).get("tenant_id", "default"),
            )
            st.session_state.auth_user_key = auth_user_key
            reset_ui_chat()
        st.caption(f"Signed in as: {selected_user['name']}")
    else:
        st.session_state.auth_token = None
        st.caption("No authenticated user loaded. Running anonymous session.")

    if st.session_state.get("auth_token"):
        try:
            verify_session_token(st.session_state.auth_token)
            st.caption("Authenticated session active.")
        except Exception:
            st.session_state.auth_token = None
            st.caption("Session token is invalid. Running anonymous session.")

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
        response = get_agent_response(
            prompt,
            auth_token=st.session_state.get("auth_token"),
            session_id=st.session_state.session_id,
        )

    st.session_state.messages.append({"role": "assistant", "content": response})
    with st.chat_message("assistant"):
        st.markdown(response)
