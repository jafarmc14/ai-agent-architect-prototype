# 🤖 Store AI-Agent Architect — Prototype

## 1. Product Requirement Document (PRD)

**Project Name:** Store AI-Agent Architect Prototype  
**Version:** MVP (Minimum Viable Product)

### Objective
Build an autonomous AI assistant for e-commerce operations that can perform **message classification**, **stock checking**, and **order tracking** automatically through internal database integration.

### Product Description
This system is a web-based chat interface powered by an AI model that supports store operations across 19 countries. The AI functions as an **"Agent"** — an entity that has access to **tools** (functions) to read data from the company's internal database system and reason over the results before responding to the customer.

### Functional Requirements

| # | Requirement | Description |
|---|---|---|
| 1 | **Intent Recognition** | Classify whether the user is asking about product stock, order status, or general assistance. |
| 2 | **Database Interaction** | Automatically execute SQL queries against an SQLite database to retrieve real-time data. |
| 3 | **Reasoning Capability** | Use multi-step reasoning before providing a final answer to the customer. |
| 4 | **Response Generation** | Deliver polite, professional responses aligned with store customer service standards. |

### MVP Scope
The MVP focuses on a **local-first, fully functional prototype** that demonstrates the core AI agent loop:
1. User sends a message via the chat UI.
2. The AI agent classifies the intent of the message.
3. If data is needed, the agent autonomously calls the appropriate tool (stock check / order lookup).
4. The tool queries the SQLite database and returns results.
5. The agent reasons over the data and generates a human-friendly response.

---

## 2. Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Frontend** | [Streamlit](https://streamlit.io/) (Python) | Web-based chat interface for user interaction. |
| **Orchestrator** | [LangChain](https://www.langchain.com/) + native LLM tool calling | Manages the AI agent loop — prompt → LLM → tool calls → reasoning → response. |
| **LLM API** | [OpenRouter](https://openrouter.ai/) — Model: `stepfun/step-3.5-flash:free` | The large language model that powers intent recognition, reasoning, and response generation. |
| **Database** | [SQLite](https://www.sqlite.org/) | Local database storing product catalog and order information. |

### Architecture Flow

```
┌──────────────┐     ┌──────────────────┐     ┌────────────────┐     ┌──────────┐
│   Streamlit  │────▶│   LangChain      │────▶│  OpenRouter    │     │  SQLite  │
│   (Frontend) │◀────│   (Orchestrator)  │◀────│  LLM API       │     │  (Data)  │
│   app.py     │     │   agent.py        │     │  step-3.5-flash│     │  toko.db │
└──────────────┘     └────────┬─────────┘     └────────────────┘     └────┬─────┘
                              │                                           │
                              │         Tool Calls (check_stock,          │
                              │          check_order_status)              │
                              └───────────────────────────────────────────┘
```

---

## 3. File Descriptions

| File | Purpose |
|---|---|
| `app.py` | **Frontend entry point.** Defines the Streamlit chat interface, manages session-based chat history, captures user input, and displays AI responses. |
| `agent.py` | **Orchestrator / AI Agent core.** Initializes the LLM via OpenRouter, defines the agent tools (`check_stock`, `check_order_status`), binds them to the model, and implements the multi-step tool-calling execution loop. |
| `database.py` | **Database layer.** Creates and initializes the SQLite database (`toko.db`) with schema and dummy data. Provides query functions (`query_stock`, `query_order`) used by the agent tools. |
| `.env` | **Environment configuration.** Stores the `OPENROUTER_API_KEY` securely, loaded at runtime by `python-dotenv`. |
| `toko.db` | **SQLite database file.** Auto-generated on first run. Contains `products` (15 items) and `orders` (8 records) tables. |
| `mvp.txt` | **Original PRD document** (in Bahasa Indonesia) outlining the project requirements. |
| `README.md` | **This file.** Full project documentation in English. |

---

## 4. Installation & Setup

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

## 5. Testing the Project

Once the app is running at `http://localhost:8501`, try the following test prompts in the chat input:

### Stock Check Tests
```
Check stock for Nike
```
> Expected: Agent calls `check_stock` tool → returns Nike Air Max Shoes with stock = 50 units.

```
Do you have any electronics available?
```
> Expected: Agent calls `check_stock` tool → returns Galaxy Fit Smartwatch, Sony WH-1000 Headphone, Mechanical RGB Keyboard, Logitech G502 Mouse.

```
Is the Birkenstock sandal still in stock?
```
> Expected: Agent calls `check_stock` tool → returns Birkenstock Sandals with stock = 20 units.

### Order Status Tests
```
What is the status of order ORD001?
```
> Expected: Agent calls `check_order_status` tool → returns order details for Budi Santoso, status: Shipped, arriving 2026-03-25.

```
Track my order ORD005
```
> Expected: Agent calls `check_order_status` tool → returns Doni Pratama's order, status: Awaiting Payment.

```
Can you check order ORD999?
```
> Expected: Agent calls `check_order_status` tool → returns "Order not found" message.

### General Conversation Tests
```
Hello, what can you help me with?
```
> Expected: Agent responds with a general greeting and explains its capabilities (stock check + order tracking).

```
Thank you for your help!
```
> Expected: Agent responds politely without calling any tools.

---

## 6. Database Schema Reference

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
| `status` | TEXT | Order status (Processing, Shipped, Completed, Awaiting Payment) |
| `shipping_address` | TEXT | Delivery address |
| `order_date` | TEXT | Date the order was placed |
| `estimated_arrival` | TEXT | Estimated delivery date (nullable) |

---

## 7. Available Dummy Data

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

| ID | Customer | Product | Qty | Status |
|---|---|---|---|---|
| ORD001 | Budi Santoso | Nike Air Max Shoes | 2 | Shipped |
| ORD002 | Siti Aminah | Black Plain T-Shirt | 5 | Processing |
| ORD003 | Andi Wijaya | Sony WH-1000 Headphone | 1 | Completed |
| ORD004 | Rina Kartika | Eau de Toilette Perfume | 3 | Shipped |
| ORD005 | Doni Pratama | Galaxy Fit Smartwatch | 1 | Awaiting Payment |
| ORD006 | Lina Susanti | Eiger Backpack | 1 | Shipped |
| ORD007 | Hendra Gunawan | Birkenstock Sandals | 1 | Completed |
| ORD008 | Maya Putri | Premium Skincare Set | 2 | Processing |
