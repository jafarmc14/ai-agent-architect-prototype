import streamlit as st
from uuid import uuid4

from agent import configure_llm_provider, get_agent_response_with_trace, get_llm_config
from core.auth import create_session_token, verify_session_token
from core.llm.provider_catalog import build_provider_options
from core.optimization import summarize_token_trace
from core.repositories.user_repository import UserRepository


PROVIDER_OPTIONS = build_provider_options()

WELCOME_MESSAGE = "Hello, I'm Ubichinon. How can I help you today?"


def reset_ui_chat() -> None:
    st.session_state.messages = [
        {"role": "assistant", "content": WELCOME_MESSAGE}
    ]
    st.session_state.last_token_usage = None


def render_token_usage(usage: dict | None) -> None:
    st.header("Token Usage")
    if not usage:
        st.caption("No request metrics yet.")
        return

    st.caption(f"Last request: {usage.get('workflow') or 'unknown workflow'}")
    resource = usage.get("resource_usage") or {}
    if resource:
        st.subheader("Request Safety")
        st.caption(
            f"Tools: {resource.get('tool_calls', 0)} | "
            f"Agent steps: {resource.get('agent_steps', 0)} | "
            f"Runtime: {resource.get('runtime_ms', 0):,} ms | "
            f"Cost: ${float(resource.get('cost_usd', 0)):.6f}"
        )
    if usage.get("resource_limit"):
        st.warning(f"Blocked by: {usage['resource_limit'].get('code', 'resource limit')}")
    loop_safety = usage.get("agent_loop_safety") or {}
    if loop_safety.get("reason"):
        st.warning(f"Agent loop stopped: {loop_safety['reason']}")

    if usage["llm_calls"] == 0:
        st.success("0 LLM calls. The request was handled deterministically.")
        st.caption(f"Request latency: {usage['request_latency_ms']:,} ms")
        return

    input_column, output_column = st.columns(2)
    input_column.metric("Input", f"{usage['input_tokens']:,}")
    output_column.metric("Output", f"{usage['output_tokens']:,}")
    st.metric("Total tokens", f"{usage['total_tokens']:,}")

    utilization = usage["context_utilization_ratio"]
    st.progress(min(utilization, 1.0))
    st.caption(
        f"Peak context utilization: {utilization:.1%} | "
        f"Combined input budget: {usage['input_budget']:,}"
    )
    if not usage["within_budget"]:
        st.error("Token budget exceeded.")
    elif utilization >= 0.8:
        st.warning("Context utilization is above 80%.")

    st.caption(
        f"LLM calls: {usage['llm_calls']} | LLM latency: {usage['llm_latency_ms']:,} ms | "
        f"Request latency: {usage['request_latency_ms']:,} ms"
    )
    if usage["cost_usd"] is not None:
        st.caption(f"Reported cost: ${usage['cost_usd']:.6f}")

    routing_decisions = usage.get("routing_decisions") or []
    if routing_decisions:
        latest_route = routing_decisions[-1]
        st.caption(
            f"Route: {latest_route.get('selected_tier', 'configured')} | "
            f"{latest_route.get('provider', 'unknown')} / {latest_route.get('model', 'unknown')}"
        )
        st.caption(f"Premium model calls: {usage.get('premium_model_calls', 0)}")

    with st.expander("Token breakdown"):
        st.caption(f"System prompt: {usage['system_prompt_tokens']:,}")
        st.caption(f"User: {usage['user_tokens']:,}")
        st.caption(f"Conversation: {usage['conversation_tokens']:,}")
        st.caption(f"Retrieval: {usage['retrieval_tokens']:,}")
        st.caption(f"Tool schemas: {usage['tool_schema_tokens']:,}")
        if usage["tasks"]:
            st.caption(f"Tasks: {', '.join(usage['tasks'])}")


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

token_usage_placeholder = None
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
    st.caption(
        "Model routing: enabled" if current_config.get("model_routing_enabled")
        else "Model routing: disabled"
    )
    model_governance = current_config.get("model_governance", {})
    st.caption(f"Model version: {current_config.get('model_version') or 'unknown'}")
    st.caption("Model pinned: yes" if model_governance.get("pinned") else "Model pinned: no (alias observed)")

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

    if current_config["environment"] == "development":
        token_usage_placeholder = st.empty()
        with token_usage_placeholder.container():
            render_token_usage(st.session_state.get("last_token_usage"))

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
        result = get_agent_response_with_trace(
            prompt,
            auth_token=st.session_state.get("auth_token"),
            session_id=st.session_state.session_id,
        )
        response = result.get("response") or (
            f"*(System Message)* Sorry, an error occurred while contacting the AI model: {result.get('exception')}"
        )
        if current_config["environment"] == "development":
            st.session_state.last_token_usage = summarize_token_trace(result)
            if token_usage_placeholder is not None:
                token_usage_placeholder.empty()
                with token_usage_placeholder.container():
                    render_token_usage(st.session_state.last_token_usage)

    st.session_state.messages.append({"role": "assistant", "content": response})
    with st.chat_message("assistant"):
        st.markdown(response)
