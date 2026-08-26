import os

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from core.prompts import SYSTEM_PROMPT
from core.tools import tools, tools_by_name
from database import init_database


init_database()
load_dotenv()

OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")

llm = ChatOpenAI(
    openai_api_base="https://openrouter.ai/api/v1",
    openai_api_key=os.getenv("OPENROUTER_API_KEY", "dummy"),
    model_name=OPENROUTER_MODEL,
    temperature=0.7,
)

llm_with_tools = llm.bind_tools(tools)
chat_history = []


def reset_chat_history() -> None:
    """Reset agent memory. Useful for isolated evaluation cases."""
    global chat_history
    chat_history = []


def _execute_agent(user_input: str, trace: dict | None = None) -> str:
    """Run the agent once, optionally recording tool calls into trace."""
    global chat_history

    if not chat_history:
        chat_history.append(SystemMessage(content=SYSTEM_PROMPT))

    chat_history.append(HumanMessage(content=user_input))

    ai_msg = llm_with_tools.invoke(chat_history)
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

        ai_msg = llm_with_tools.invoke(chat_history)
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
