# 🤖 Store AI-Agent Architect — Prototype

## 1. Product Requirement Document (PRD)

**Project Name:** Store AI-Agent Architect Prototype  
**Version:** MVP v2.0 (Enhanced)

### Objective
Build an autonomous AI assistant for e-commerce operations that can perform **message classification**, **stock checking**, **order tracking**, **smart product recommendations**, **transactional actions**, **shopping cart management**, **policy Q&A**, and **human escalation** — all automatically through internal database and knowledge base integration.

### Product Description
**Current agent profile:** The assistant's name is **Ubichinon**. It is configured to speak in a friendly, polite, natural Indonesian customer-service style when users communicate in Indonesian.

This system is a web-based chat interface powered by an AI model that supports store operations across 19 countries. The AI functions as an **"Agent"** — an entity that has access to **10 tools** (functions) to read and write data from the company's internal database system, search store policies, and escalate issues to human agents when needed.

### Functional Requirements

| # | Requirement | Description |
|---|---|---|
| 1 | **Intent Recognition** | Classify whether the user is asking about stock, orders, policies, shopping, or needs human help. |
| 2 | **Database Interaction (Read)** | Automatically execute SQL queries against SQLite to retrieve real-time product and order data. |
| 3 | **Database Interaction (Write)** | Cancel orders, update shipping addresses, and manage shopping cart data in the database. |
| 4 | **Smart Product Search** | Filter and recommend products by category, price range, or combination of both. |
| 5 | **Shopping Cart** | Add products to cart, view cart contents, and clear cart — all via natural conversation. |
| 6 | **Knowledge Base (RAG)** | Search store policies (returns, refunds, shipping, warranty, payments) from a knowledge document. |
| 7 | **Human Escalation** | Create support tickets when the AI cannot resolve an issue or the customer requests a human agent. |
| 8 | **Multi-step Reasoning** | Use multi-step reasoning and chain multiple tool calls before providing a final answer. |
| 9 | **Response Generation** | Deliver polite, professional responses aligned with store customer service standards. |

---

## 2. Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Frontend** | [Streamlit](https://streamlit.io/) (Python) | Web-based chat interface for user interaction. |
| **Orchestrator** | [LangChain](https://www.langchain.com/) + Native LLM Tool Calling | Manages the AI agent loop — prompt → LLM → tool calls → reasoning → response. |
| **LLM API** | [OpenRouter](https://openrouter.ai/) — Model: `openrouter/free` by default, configurable with `OPENROUTER_MODEL` | The large language model that powers intent recognition, reasoning, and response generation. |
| **Database** | [SQLite](https://www.sqlite.org/) | Local database storing products, orders, shopping cart, and support tickets. |
| **Knowledge Base** | Plain text file (`knowledge_base.txt`) | Store policies and FAQ document searched by the AI agent for policy-related queries. |

### Architecture Flow

```
┌──────────────┐     ┌──────────────────┐     ┌────────────────┐
│   Streamlit  │────▶│   LangChain      │────▶│  OpenRouter    │
│   (Frontend) │◀────│   (Orchestrator)  │◀────│  LLM API       │
│   app.py     │     │   agent.py        │     │  step-3.5-flash│
└──────────────┘     └──────┬───────────┘     └────────────────┘
                            │
                   ┌────────┴────────┐
                   │   10 AI Tools   │
                   └────────┬────────┘
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
        ┌──────────┐  ┌──────────┐  ┌─────────────────┐
        │  SQLite  │  │ Knowledge│  │  Support Ticket  │
        │  (Data)  │  │   Base   │  │    System        │
        │ toko.db  │  │  .txt    │  │  (in SQLite)     │
        └──────────┘  └──────────┘  └─────────────────┘
```

Note: The default runtime model is `openrouter/free`, unless overridden with `OPENROUTER_MODEL` in `.env`.

---

## 3. AI Agent Tools (10 Total)

| # | Tool Name | Feature | Type | Description |
|---|---|---|---|---|
| 1 | `check_stock` | Original | Read | Look up product availability by name |
| 2 | `check_order_status` | Original | Read | Look up order status by order ID |
| 3 | `search_products` | Smart Recommender | Read | Filter products by category and/or price range |
| 4 | `cancel_customer_order` | Transactional | Write | Cancel orders (only Processing/Awaiting Payment) |
| 5 | `update_shipping_address` | Transactional | Write | Change shipping address (only before shipment) |
| 6 | `add_product_to_cart` | Shopping Cart | Write | Add a product to the shopping cart |
| 7 | `view_shopping_cart` | Shopping Cart | Read | View all items in the cart |
| 8 | `clear_shopping_cart` | Shopping Cart | Write | Empty the entire cart |
| 9 | `search_knowledge_base` | Knowledge Base (RAG) | Read | Search store policies and FAQ |
| 10 | `escalate_to_human` | Human Handoff | Write | Create a support ticket for human review |

---

## 4. File Descriptions

| File | Purpose |
|---|---|
| `app.py` | **Frontend entry point.** Defines the Streamlit chat interface, manages session-based chat history, captures user input, and displays AI responses. |
| `agent.py` | **Orchestrator / AI Agent core.** Initializes the LLM via OpenRouter, defines all 10 agent tools, binds them to the model, and implements the multi-step tool-calling execution loop. |
| `database.py` | **Database layer.** Creates and initializes the SQLite database (`toko.db`) with schema and dummy data. Provides all query and mutation functions used by the agent tools. |
| `knowledge_base.txt` | **Store policies & FAQ.** Contains official store rules for returns, refunds, shipping, warranty, payments, operating hours, and loyalty program. Searched by the AI agent for policy-related questions. |
| `.env` | **Environment configuration.** Stores the `OPENROUTER_API_KEY` securely, loaded at runtime by `python-dotenv`. |
| `toko.db` | **SQLite database file.** Auto-generated on first run. Contains `products`, `orders`, `shopping_cart`, and `support_tickets` tables. |
| `.gitignore` | **Git ignore rules.** Prevents `.env`, `toko.db`, and temp files from being pushed to the repository. |
| `CAPABILITY_MATRIX.md` | **Capability inventory.** Groups all agent tools by access type (`READ`/`WRITE`) and risk level (`LOW`/`MEDIUM`/`HIGH`). |
| `evaluation/datasets/baseline/*.jsonl` | **Baseline evaluation dataset.** Contains 41 JSONL test cases converted from manual prompts and additional baseline variants. |
| `evaluation/run_baseline.py` | **Evaluation runner v1.** Runs baseline cases, traces tool calls, measures accuracy/latency/exceptions, and saves the latest report. |
| `evaluation/reports/baseline_report_latest.json` | **Latest evaluation report.** Generated by the runner and overwritten on each evaluation run. |
| `mvp.txt` | **Original PRD document** (in Bahasa Indonesia) outlining the initial project requirements. |
| `README.md` | **This file.** Full project documentation in English. |

---

## 5. Installation & Setup

### Prerequisites
- **Python 3.10+** installed on Windows
- An **OpenRouter API key** (free tier available at [openrouter.ai](https://openrouter.ai/))

### Step-by-Step Installation

```bash
# 1. Navigate to the project directory
cd "D:\AI-Agent Arch Prot"

# 2. Install all required Python packages
py -m pip install streamlit langchain langchain-openai python-dotenv

# 3. Configure your API key
#    Open the .env file and set your OpenRouter API key:
#    OPENROUTER_API_KEY=sk-or-v1-your-key-here
#    Optional: override the default model
#    OPENROUTER_MODEL=openrouter/free

# 4. Initialize the database (auto-creates toko.db with dummy data)
py database.py

# 5. Launch the application
py -m streamlit run app.py
```

After running step 5, Streamlit will start a local server. Open your browser and navigate to:
```
http://localhost:8501
```

---

## 6. Baseline Evaluation

### Freeze Point

The current prototype baseline is tagged as:

```bash
prototype-v2
```

This tag is used as the rollback point and reference for regression comparison.

### Capability Inventory

The full capability matrix is documented in:

```text
CAPABILITY_MATRIX.md
```

Summary:

| Group | Tools |
|---|---|
| READ / LOW | `check_stock`, `check_order_status`, `search_products`, `search_knowledge_base`, `view_shopping_cart` |
| WRITE / MEDIUM | `add_product_to_cart`, `clear_shopping_cart`, `escalate_to_human` |
| WRITE / HIGH | `cancel_customer_order`, `update_shipping_address` |

### Dataset

Baseline cases are stored in:

```text
evaluation/datasets/baseline/
```

| File | Cases | Focus |
|---|---:|---|
| `stock.jsonl` | 5 | Stock lookup |
| `orders.jsonl` | 8 | Order tracking, cancellation, address update |
| `products.jsonl` | 6 | Product browsing and filtering |
| `cart.jsonl` | 6 | Add/view/clear cart |
| `knowledge.jsonl` | 7 | Policy and FAQ lookup |
| `escalation.jsonl` | 5 | Human handoff |
| `multistep.jsonl` | 4 | No-tool and multi-tool conversations |

Each JSONL row follows this shape:

```json
{
  "id": "stock_001",
  "query": "Do you have Nike shoes?",
  "expected_tool": "check_stock",
  "expected_arguments": {
    "product_name": "Nike"
  }
}
```

For no-tool cases, `expected_tool` is `null`. For multi-step cases, `expected_tool` and `expected_arguments` are arrays in expected call order.

### Runner

Run a smoke test:

```bash
py evaluation/run_baseline.py --limit 3
```

Run a specific dataset file:

```bash
py evaluation/run_baseline.py --files cart
py evaluation/run_baseline.py --files escalation
```

Run in batches:

```bash
py evaluation/run_baseline.py --offset 0 --limit 10
py evaluation/run_baseline.py --offset 10 --limit 10
py evaluation/run_baseline.py --offset 20 --limit 10
```

Add delay between cases to reduce OpenRouter per-minute rate limit errors:

```bash
py evaluation/run_baseline.py --limit 10 --delay-seconds 5
```

The runner measures:

| Metric | Description |
|---|---|
| `tool_selection_rate` | Whether the actual tool sequence matches the expected tool sequence. |
| `argument_accuracy_rate` | Whether actual tool arguments match expected arguments, including known aliases. |
| `response_return_rate` | Whether the agent returned a final response. |
| `exceptions` | Runtime/API exceptions encountered during evaluated cases. |
| `rate_limit_exceptions` | OpenRouter rate-limit exceptions among evaluated cases. |
| `latency_ms` | Per-case latency in milliseconds. |
| `skipped_cases` | Cases skipped after rate limit is detected. |

Reports are saved to:

```text
evaluation/reports/baseline_report_latest.json
```

The report file is overwritten on each run to avoid report folder growth.

### Free-Tier Rate Limit Note

`openrouter/free` is useful for avoiding hardcoded free-model slugs that may disappear, but it is still subject to OpenRouter free-tier limits. A full 41-case baseline can exceed the daily quota because each tool-calling case may require more than one LLM request. Prefer smoke tests, per-file runs, or small batches when using the free tier.

---

## 7. Testing the Project — Chat Prompts

Once the app is running at `http://localhost:8501`, use the following test prompts to verify each feature.

### 🔍 Feature: Stock Check (Original)

**Test 1 — Search by product name:**
```
User: Do you have Nike shoes in stock?
```
> Expected: Agent calls `check_stock("Nike")` → returns Nike Air Max Shoes, stock: 50 units.

**Test 2 — Search for non-existent product:**
```
User: Check if you have PS5 consoles available
```
> Expected: Agent calls `check_stock("PS5")` → returns "No products found matching 'PS5'."

---

### 📦 Feature: Order Tracking (Original)

**Test 3 — Track a shipped order:**
```
User: What is the status of order ORD001?
```
> Expected: Agent calls `check_order_status("ORD001")` → returns Budi Santoso's order, status: Shipped, ETA: 2026-03-25.

**Test 4 — Track a non-existent order:**
```
User: Track my order ORD999
```
> Expected: Agent calls `check_order_status("ORD999")` → returns "Order not found."

---

### 🎯 Feature 1: Smart Product Recommender

**Test 5 — Filter by category:**
```
User: Show me all electronics products you have
```
> Expected: Agent calls `search_products(category="Electronics")` → returns Galaxy Fit Smartwatch, Sony WH-1000 Headphone, Mechanical RGB Keyboard, Logitech G502 Mouse.

**Test 6 — Filter by category + price range:**
```
User: I'm looking for electronics under Rp 600,000
```
> Expected: Agent calls `search_products(category="Electronics", max_price=600000)` → returns only Mechanical RGB Keyboard (Rp 550,000).

**Test 7 — Filter by price range only:**
```
User: What products do you have between Rp 100,000 and Rp 300,000?
```
> Expected: Agent calls `search_products(min_price=100000, max_price=300000)` → returns Polarized Sunglasses (Rp 175,000) and Eau de Toilette Perfume (Rp 280,000).

---

### ✏️ Feature 2: Transactional Actions (Cancel Order & Update Address)

**Test 8 — Cancel a processing order:**
```
User: I want to cancel my order ORD002
```
> Expected: Agent calls `cancel_customer_order("ORD002")` → returns success message. Status changes from "Processing" to "Cancelled".

**Test 9 — Cancel a shipped order (should fail):**
```
User: Please cancel order ORD001
```
> Expected: Agent calls `cancel_customer_order("ORD001")` → returns error: "Cannot cancel, current status is Shipped."

**Test 10 — Update shipping address:**
```
User: I need to change the address for order ORD005 to Jl. Sudirman No. 100, Jakarta
```
> Expected: Agent calls `update_shipping_address("ORD005", "Jl. Sudirman No. 100, Jakarta")` → returns success with old and new address.

**Test 11 — Update address for shipped order (should fail):**
```
User: Change the address for ORD001 to Jl. Baru No. 1
```
> Expected: Agent calls `update_shipping_address("ORD001", ...)` → returns error: "Cannot update, order already shipped."

---

### 🛒 Feature 3: Shopping Cart

**Test 12 — Add item to cart:**
```
User: Add 2 Nike shoes to my cart
```
> Expected: Agent calls `add_product_to_cart("Nike", 2)` → returns "Added to cart: Nike Air Max Shoes x2 (Rp 2,400,000)."

**Test 13 — Add another item:**
```
User: Also add 1 Python Programming Book please
```
> Expected: Agent calls `add_product_to_cart("Python Programming Book", 1)` → returns "Added to cart: Python Programming Book x1 (Rp 95,000)."

**Test 14 — View cart:**
```
User: What's in my cart right now?
```
> Expected: Agent calls `view_shopping_cart()` → returns list of items with subtotals and grand total.

**Test 15 — Clear cart:**
```
User: Please clear my cart, I changed my mind
```
> Expected: Agent calls `clear_shopping_cart()` → returns "Shopping cart cleared."

---

### 📚 Feature 4: Knowledge Base / Policy Q&A (RAG)

**Test 16 — Return policy:**
```
User: What is your return policy? Can I return a product after 10 days?
```
> Expected: Agent calls `search_knowledge_base("return policy")` → finds return policy section and explains the 7-day return window.

**Test 17 — Refund timeline:**
```
User: How long does a refund take?
```
> Expected: Agent calls `search_knowledge_base("refund")` → explains 3-5 business days refund processing.

**Test 18 — Shipping info:**
```
User: How long does international shipping take?
```
> Expected: Agent calls `search_knowledge_base("international shipping")` → returns 10-14 business days.

**Test 19 — Payment methods:**
```
User: What payment methods do you accept?
```
> Expected: Agent calls `search_knowledge_base("payment methods")` → lists Bank Transfer, Credit Card, E-Wallet, COD.

**Test 20 — Warranty claim:**
```
User: My headphone is defective, how do I claim warranty?
```
> Expected: Agent calls `search_knowledge_base("warranty")` → explains warranty process: provide Order ID, proof of purchase, photos.

---

### 🎫 Feature 5: Human Escalation / Support Ticket

**Test 21 — Explicit request for human:**
```
User: I want to speak to a real human agent please
```
> Expected: Agent calls `escalate_to_human(...)` → creates a support ticket and informs the user a human will follow up within 24 hours.

**Test 22 — Frustrated customer:**
```
User: This is ridiculous! I've been waiting for 2 weeks and my order still hasn't arrived. Nobody is helping me! I'm extremely frustrated!
```
> Expected: Agent recognizes frustration, calls `escalate_to_human(...)` with priority "High" or "Urgent" → creates a ticket and reassures the customer.

**Test 23 — Complex issue beyond AI capability:**
```
User: I received a damaged product but the order shows as Completed. I want a replacement, not a refund. Also, the delivery person was rude.
```
> Expected: Agent may first call `search_knowledge_base("return damaged")` for context, then calls `escalate_to_human(...)` since this requires human judgment → creates a support ticket.

---

### 💬 General Conversation Tests

**Test 24 — Greeting:**
```
User: Hello, what can you help me with?
```
> Expected: Agent responds with a friendly greeting and lists all its capabilities without calling any tools.

**Test 25 — Multi-step reasoning:**
```
User: I'd like to check if you have any shoes under Rp 1,200,000, and also check my order ORD006
```
> Expected: Agent makes TWO tool calls: `search_products(category="Shoes", max_price=1200000)` AND `check_order_status("ORD006")` → combines both results into one coherent response.

**Test 26 — Closing:**
```
User: Thank you for your help!
```
> Expected: Agent responds politely without calling any tools.

---

## 8. Database Schema Reference

### `products` Table

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER (PK) | Auto-incremented product ID |
| `name` | TEXT | Product name |
| `category` | TEXT | Product category (Shoes, Electronics, etc.) |
| `price` | REAL | Price in IDR (Rupiah) |
| `stock` | INTEGER | Available stock quantity |
| `country` | TEXT | Country of origin |

### `orders` Table

| Column | Type | Description |
|---|---|---|
| `id` | TEXT (PK) | Order ID (e.g., ORD001) |
| `customer_name` | TEXT | Customer full name |
| `product_id` | INTEGER (FK) | References `products.id` |
| `quantity` | INTEGER | Number of items ordered |
| `total_price` | REAL | Total order price in IDR |
| `status` | TEXT | Order status: Processing, Shipped, Completed, Awaiting Payment, Cancelled |
| `shipping_address` | TEXT | Delivery address |
| `order_date` | TEXT | Date the order was placed |
| `estimated_arrival` | TEXT | Estimated delivery date (nullable) |

### `shopping_cart` Table

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER (PK) | Auto-incremented cart item ID |
| `session_id` | TEXT | Session identifier (default: 'default') |
| `product_id` | INTEGER (FK) | References `products.id` |
| `quantity` | INTEGER | Number of items in cart |
| `added_at` | TEXT | Timestamp when item was added |

### `support_tickets` Table

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER (PK) | Auto-incremented ticket ID |
| `customer_message` | TEXT | Original customer message/complaint |
| `agent_summary` | TEXT | AI agent's reason for escalation |
| `priority` | TEXT | Low, Normal, High, or Urgent |
| `status` | TEXT | Open, In Progress, Resolved, Closed |
| `created_at` | TEXT | Timestamp when ticket was created |

---

## 9. Available Dummy Data

### Products (15 items)

| ID | Product | Category | Price (Rp) | Stock | Origin |
|---|---|---|---|---|---|
| 1 | Nike Air Max Shoes | Shoes | 1,200,000 | 50 | Indonesia |
| 2 | Adidas Ultraboost Shoes | Shoes | 1,500,000 | 35 | Indonesia |
| 3 | Black Plain T-Shirt | Clothing | 89,000 | 200 | Indonesia |
| 4 | Oversize Denim Jacket | Clothing | 350,000 | 80 | Indonesia |
| 5 | Eiger Backpack | Bags | 450,000 | 60 | Indonesia |
| 6 | Galaxy Fit Smartwatch | Electronics | 1,800,000 | 25 | Indonesia |
| 7 | Sony WH-1000 Headphone | Electronics | 3,200,000 | 15 | Japan |
| 8 | Mechanical RGB Keyboard | Electronics | 550,000 | 40 | China |
| 9 | Logitech G502 Mouse | Electronics | 750,000 | 30 | United States |
| 10 | Eau de Toilette Perfume | Beauty | 280,000 | 100 | France |
| 11 | Premium Skincare Set | Beauty | 499,000 | 70 | South Korea |
| 12 | Python Programming Book | Books | 95,000 | 150 | Indonesia |
| 13 | Birkenstock Sandals | Shoes | 1,100,000 | 20 | Germany |
| 14 | Polarized Sunglasses | Accessories | 175,000 | 90 | Italy |
| 15 | Casio Classic Watch | Accessories | 650,000 | 45 | Japan |

### Orders (8 records)

| ID | Customer | Product | Qty | Total (Rp) | Status |
|---|---|---|---|---|---|
| ORD001 | Budi Santoso | Nike Air Max Shoes | 2 | 2,400,000 | Shipped |
| ORD002 | Siti Aminah | Black Plain T-Shirt | 5 | 445,000 | Processing |
| ORD003 | Andi Wijaya | Sony WH-1000 Headphone | 1 | 3,200,000 | Completed |
| ORD004 | Rina Kartika | Eau de Toilette Perfume | 3 | 840,000 | Shipped |
| ORD005 | Doni Pratama | Galaxy Fit Smartwatch | 1 | 1,800,000 | Awaiting Payment |
| ORD006 | Lina Susanti | Eiger Backpack | 1 | 450,000 | Shipped |
| ORD007 | Hendra Gunawan | Birkenstock Sandals | 1 | 1,100,000 | Completed |
| ORD008 | Maya Putri | Premium Skincare Set | 2 | 998,000 | Processing |
