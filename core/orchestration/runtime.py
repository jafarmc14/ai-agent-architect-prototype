from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from core.llm import llm_gateway
from core.prompts import SYSTEM_PROMPT
from core.tools import tools, tools_by_name
from database import init_database


init_database()

LLM_PROVIDER = llm_gateway.provider_name
LLM_MODEL = llm_gateway.model
OPENROUTER_MODEL = llm_gateway.model
llm = llm_gateway.client
llm_with_tools = llm.bind_tools(tools)
chat_history = []


def _response_language_instruction(user_input: str) -> str:
    """Create a per-turn language hint for models that weakly follow system prompts."""
    text = f" {user_input.lower()} "
    indonesian_markers = [
        " apa ",
        " apakah ",
        " bagaimana ",
        " berapa ",
        " bisa ",
        " saya ",
        " kamu ",
        " tolong ",
        " pesanan ",
        " keranjang ",
        " barang ",
        " produk ",
        " alamat ",
        " harga ",
        " stok ",
    ]
    english_markers = [
        " what ",
        " how ",
        " can ",
        " could ",
        " would ",
        " please ",
        " i ",
        " my ",
        " your ",
        " order ",
        " cart ",
        " product ",
        " address ",
        " price ",
        " stock ",
    ]

    indonesian_score = sum(1 for marker in indonesian_markers if marker in text)
    english_score = sum(1 for marker in english_markers if marker in text)

    if english_score > indonesian_score:
        return "The current user message is in English. Your final answer must be in English."
    if indonesian_score > english_score:
        return "The current user message is in Indonesian. Your final answer must be in Indonesian."
    return "Use the same language as the user's current message for your final answer."


def configure_llm_provider(provider_name: str, model: str | None = None) -> dict:
    """Switch the active LLM provider for the running process."""
    global LLM_PROVIDER, LLM_MODEL, OPENROUTER_MODEL, llm, llm_with_tools

    llm_gateway.configure(provider_name=provider_name, model=model)
    LLM_PROVIDER = llm_gateway.provider_name
    LLM_MODEL = llm_gateway.model
    OPENROUTER_MODEL = llm_gateway.model
    llm = llm_gateway.client
    llm_with_tools = llm.bind_tools(tools)
    reset_chat_history()

    return get_llm_config()


def get_llm_config() -> dict:
    """Return the active LLM runtime configuration."""
    return {
        "provider": LLM_PROVIDER,
        "model": LLM_MODEL,
    }


def reset_chat_history() -> None:
    """Reset agent memory. Useful for isolated evaluation cases."""
    global chat_history
    chat_history = []


def _execute_agent(user_input: str, trace: dict | None = None) -> str:
    """Run the agent once, optionally recording tool calls into trace."""
    global chat_history

    if not chat_history:
        chat_history.append(SystemMessage(content=SYSTEM_PROMPT))

    chat_history.append(SystemMessage(content=_response_language_instruction(user_input)))
    chat_history.append(HumanMessage(content=user_input))

    llm_response = llm_gateway.generate_sync(chat_history, tools=tools)
    ai_msg = llm_response.raw
    chat_history.append(ai_msg)

    while hasattr(ai_msg, "tool_calls") and ai_msg.tool_calls:
        for tool_call in ai_msg.tool_calls:
            selected_tool = tools_by_name.get(tool_call["name"].lower())
            if selected_tool:
                tool_output = selected_tool.invoke(tool_call["args"])
            else:
                tool_output = f"Error: Tool {tool_call['name']} not found."

            if trace is not None:
                trace.setdefault("tool_calls", []).append({
                    "name": tool_call["name"],
                    "args": tool_call["args"],
                    "output": str(tool_output),
                })

            chat_history.append(ToolMessage(
                content=str(tool_output),
                tool_call_id=tool_call["id"],
                name=tool_call["name"],
            ))

        llm_response = llm_gateway.generate_sync(chat_history, tools=tools)
        ai_msg = llm_response.raw
        chat_history.append(ai_msg)

    return ai_msg.content


def get_agent_response(user_input: str) -> str:
    """Standalone executor function using native LLM tool calling."""
    try:
        return _execute_agent(user_input)
    except Exception as e:
        return f"*(System Message)* Sorry, an error occurred while contacting the AI model: {str(e)}"


def get_agent_response_with_trace(user_input: str) -> dict:
    """Run the agent and return response, tool calls, and exception details."""
    trace = {"tool_calls": []}
    try:
        response = _execute_agent(user_input, trace=trace)
        return {
            "response": response,
            "tool_calls": trace["tool_calls"],
            "exception": None,
        }
    except Exception as e:
        return {
            "response": "",
            "tool_calls": trace["tool_calls"],
            "exception": str(e),
        }
