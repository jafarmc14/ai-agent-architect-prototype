import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langchain.tools import tool
from database import init_database, query_stock, query_order

# Ensure database exists and is populated with dummy data
init_database()

# Load environment variables
load_dotenv()

# Initialize LLM via OpenRouter
llm = ChatOpenAI(
    openai_api_base="https://openrouter.ai/api/v1",
    openai_api_key=os.getenv("OPENROUTER_API_KEY", "dummy"),
    model_name="stepfun/step-3.5-flash:free",
    temperature=0.7,
)

# Tool 1: Check Product Stock (queries SQLite)
@tool
def check_stock(product_name: str) -> str:
    """Use this function when the user asks about stock or product availability. Input is the product name."""
    return query_stock(product_name)

# Tool 2: Check Order Status (queries SQLite)
@tool
def check_order_status(order_id: str) -> str:
    """Use this function when the user asks about order status or shipping tracking. Input is the order ID."""
    return query_order(order_id)

tools = [check_stock, check_order_status]
tools_by_name = {t.name: t for t in tools}

# Bind tools to the LLM
llm_with_tools = llm.bind_tools(tools)

# Simple global memory state (Streamlit reruns the script on each interaction)
chat_history = []

def get_agent_response(user_input: str) -> str:
    """Standalone executor function using native LLM tool calling."""
    global chat_history
    try:
        # Initialize system prompt if memory is empty
        if not chat_history:
            chat_history.append(SystemMessage(
                content=(
                    "You are a Virtual Store Assistant for an e-commerce platform operating in 19 countries. "
                    "Provide professional, informative, and polite responses. "
                    "Use the provided tools to check the database when asked about product stock or order status."
                )
            ))
            
        # Add user message
        chat_history.append(HumanMessage(content=user_input))
        
        # Call LLM
        ai_msg = llm_with_tools.invoke(chat_history)
        chat_history.append(ai_msg)
        
        # Multi-step tool execution loop if the model requests tool access
        while hasattr(ai_msg, 'tool_calls') and ai_msg.tool_calls:
            for tool_call in ai_msg.tool_calls:
                selected_tool = tools_by_name.get(tool_call["name"].lower())
                if selected_tool:
                    tool_output = selected_tool.invoke(tool_call["args"])
                else:
                    tool_output = f"Error: Tool {tool_call['name']} not found."
                
                # Append tool result back to history
                chat_history.append(ToolMessage(
                    content=str(tool_output), 
                    tool_call_id=tool_call["id"],
                    name=tool_call["name"]
                ))
            
            # Call LLM again after it receives the database results
            ai_msg = llm_with_tools.invoke(chat_history)
            chat_history.append(ai_msg)
            
        return ai_msg.content
    except Exception as e:
        return f"*(System Message)* Sorry, an error occurred while contacting the AI model: {str(e)}"
