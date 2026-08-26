import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langchain.tools import tool
from database import (
    init_database, query_stock, query_order,
    query_products_by_filter,       # Feature 1: Smart Recommender
    cancel_order, update_order_address,  # Feature 2: Transactional Actions
    add_to_cart, view_cart, clear_cart,   # Feature 3: Shopping Cart
    create_support_ticket,               # Feature 5: Human Handoff
)

# Ensure database exists and is populated with dummy data
init_database()

# Load environment variables
load_dotenv()

# Load knowledge base content for Feature 4 (RAG)
KB_PATH = os.path.join(os.path.dirname(__file__), "knowledge_base.txt")
knowledge_base_content = ""
if os.path.exists(KB_PATH):
    with open(KB_PATH, "r", encoding="utf-8") as f:
        knowledge_base_content = f.read()

# Initialize LLM via OpenRouter
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")

llm = ChatOpenAI(
    openai_api_base="https://openrouter.ai/api/v1",
    openai_api_key=os.getenv("OPENROUTER_API_KEY", "dummy"),
    model_name=OPENROUTER_MODEL,
    temperature=0.7,
)


# =====================================================================
# TOOL DEFINITIONS
# =====================================================================

# --- Tool 1: Check Product Stock (Original) ---
@tool
def check_stock(product_name: str) -> str:
    """Use this when the user asks about stock or availability of a product. Input can be a full name, partial name, or common Indonesian product alias."""
    return query_stock(product_name)

# --- Tool 2: Check Order Status (Original) ---
@tool
def check_order_status(order_id: str) -> str:
    """Use this when the user asks about order status or shipping tracking. Input: order ID (e.g. ORD001)."""
    return query_order(order_id)

# --- Tool 3: Smart Product Search / Recommender (Feature 1) ---
@tool
def search_products(category: str = "", max_price: float = 0, min_price: float = 0) -> str:
    """Use this when the user wants to browse or filter products by category and/or price range.
    Input parameters:
    - category: product category like 'Electronics', 'Shoes', 'Clothing', 'Beauty', 'Accessories', 'Bags', 'Books' (optional)
    - max_price: maximum price in Rupiah (optional, 0 means no limit)
    - min_price: minimum price in Rupiah (optional, 0 means no limit)
    Examples: user says 'show me cheap electronics under 600000' -> category='Electronics', max_price=600000"""
    return query_products_by_filter(category, max_price, min_price)

# --- Tool 4: Cancel Order (Feature 2) ---
@tool
def cancel_customer_order(order_id: str) -> str:
    """Use this when the user wants to cancel an order. Only works for orders with 'Processing' or 'Awaiting Payment' status. Input: order ID (e.g. ORD002)."""
    return cancel_order(order_id)

# --- Tool 5: Update Shipping Address (Feature 2) ---
@tool
def update_shipping_address(order_id: str, new_address: str) -> str:
    """Use this when the user wants to change/update the shipping address of an order. Only works for orders not yet shipped. Input: order ID and the new full address."""
    return update_order_address(order_id, new_address)

# --- Tool 6: Add to Cart (Feature 3) ---
@tool
def add_product_to_cart(product_name: str, quantity: int = 1) -> str:
    """Use this when the user wants to add a product to their shopping cart. Input can be a full name, partial name, or common Indonesian product alias. Call this tool before asking for clarification unless the product is truly ambiguous."""
    return add_to_cart(product_name, quantity)

# --- Tool 7: View Cart (Feature 3) ---
@tool
def view_shopping_cart() -> str:
    """Use this when the user wants to see what is currently in their shopping cart."""
    return view_cart()

# --- Tool 8: Clear Cart (Feature 3) ---
@tool
def clear_shopping_cart() -> str:
    """Use this when the user wants to empty/clear their entire shopping cart."""
    return clear_cart()

# --- Tool 9: Search Knowledge Base (Feature 4 — RAG) ---
@tool
def search_knowledge_base(query: str) -> str:
    """Use this when the user asks about store policies, return/refund rules, shipping info, warranty, payment methods, operating hours, loyalty program, or any general FAQ.
    Input: the user's question or keywords about store policy.
    This searches the store's official knowledge base document."""
    if not knowledge_base_content:
        return "Knowledge base is not available at this time."

    # Simple keyword-based search: find relevant sections
    query_lower = query.lower()
    lines = knowledge_base_content.split("\n")
    relevant_lines = []
    current_section = ""

    for line in lines:
        if line.startswith("---") and line.endswith("---"):
            current_section = line
        if any(keyword in line.lower() for keyword in query_lower.split()):
            if current_section and current_section not in relevant_lines:
                relevant_lines.append(current_section)
            relevant_lines.append(line)

    if not relevant_lines:
        # If no keyword match, return the full knowledge base for the LLM to reason over
        return f"No exact keyword match found for '{query}'. Here is the full knowledge base for reference:\n\n{knowledge_base_content}"

    return f"Relevant store policy information for '{query}':\n" + "\n".join(relevant_lines)

# --- Tool 10: Escalate to Human Support (Feature 5) ---
@tool
def escalate_to_human(customer_message: str, reason: str = "", priority: str = "Normal") -> str:
    """Use this when the user's issue cannot be resolved by the AI, when the user explicitly asks to speak to a human, or when the user is very frustrated/angry.
    Input:
    - customer_message: the original message or complaint from the user
    - reason: brief summary of why escalation is needed (written by the AI agent)
    - priority: 'Low', 'Normal', 'High', or 'Urgent'"""
    return create_support_ticket(customer_message, reason, priority)


# =====================================================================
# AGENT SETUP
# =====================================================================

tools = [
    check_stock,
    check_order_status,
    search_products,
    cancel_customer_order,
    update_shipping_address,
    add_product_to_cart,
    view_shopping_cart,
    clear_shopping_cart,
    search_knowledge_base,
    escalate_to_human,
]
tools_by_name = {t.name: t for t in tools}

# Bind all tools to the LLM
llm_with_tools = llm.bind_tools(tools)

# Simple global memory state (Streamlit reruns the script on each interaction)
chat_history = []

SYSTEM_PROMPT = (
    "Your name is Ubichinon. You are the official Virtual Store Assistant for an e-commerce platform operating in 19 countries. "
    "You are friendly, polite, helpful, and speak naturally like a courteous Indonesian customer service representative.\n"
    "When users ask your name or identity, introduce yourself as Ubichinon, the store's virtual assistant.\n\n"
    "YOUR CAPABILITIES:\n"
    "1. CHECK STOCK: Use 'check_stock' to look up product availability by name.\n"
    "2. CHECK ORDER: Use 'check_order_status' to look up order status by order ID.\n"
    "3. SMART SEARCH: Use 'search_products' to filter products by category and/or price range.\n"
    "4. CANCEL ORDER: Use 'cancel_customer_order' to cancel orders (only Processing / Awaiting Payment).\n"
    "5. UPDATE ADDRESS: Use 'update_shipping_address' to change shipping address (only before shipment).\n"
    "6. SHOPPING CART: Use 'add_product_to_cart', 'view_shopping_cart', 'clear_shopping_cart' to manage the user's cart.\n"
    "7. KNOWLEDGE BASE: Use 'search_knowledge_base' when asked about store policies, returns, refunds, shipping, warranty, payments, or FAQs.\n"
    "8. HUMAN ESCALATION: Use 'escalate_to_human' when you cannot solve the issue, the user is angry/frustrated, or they explicitly ask for a human agent.\n\n"
    "RULES:\n"
    "- Always use the appropriate tool to get real data before answering factual questions.\n"
    "- For add-to-cart requests, call 'add_product_to_cart' first using the user's product phrase and quantity. Do not invent alternate catalog items or ask for clarification before checking the tool.\n"
    "- Product tools support partial names and common Indonesian aliases, such as 'Nike shoes', 'sepatu Nike', and 'kaos hitam'.\n"
    "- Never make up product data, prices, or order statuses.\n"
    "- If a user asks about policies (returns, refunds, shipping, etc.), ALWAYS use the knowledge base tool first.\n"
    "- If the user explicitly asks for a human, admin, real person, or support agent, immediately call 'escalate_to_human'. Do not ask for a reason first.\n"
    "- If the user is angry, frustrated, reports a long unresolved delay, duplicate payment, damaged product, rude courier, or another complex complaint, immediately call 'escalate_to_human' with High priority unless Urgent is clearly needed.\n"
    "- Respond in the same language the user uses.\n"
    "- If the user uses Indonesian, use natural, friendly, and polite Indonesian. Avoid sounding stiff or overly formal."
)

def reset_chat_history() -> None:
    """Reset agent memory. Useful for isolated evaluation cases."""
    global chat_history
    chat_history = []


def _execute_agent(user_input: str, trace: dict | None = None) -> str:
    """Run the agent once, optionally recording tool calls into trace."""
    global chat_history

    # Initialize system prompt if memory is empty
    if not chat_history:
        chat_history.append(SystemMessage(content=SYSTEM_PROMPT))

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

            if trace is not None:
                trace.setdefault("tool_calls", []).append({
                    "name": tool_call["name"],
                    "args": tool_call["args"],
                    "output": str(tool_output),
                })

            # Append tool result back to history
            chat_history.append(ToolMessage(
                content=str(tool_output),
                tool_call_id=tool_call["id"],
                name=tool_call["name"]
            ))

        # Call LLM again after it receives the tool results
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
