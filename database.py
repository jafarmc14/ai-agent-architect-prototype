import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "toko.db")

PRODUCT_ALIASES = {
    "nike shoes": "Nike",
    "nike shoe": "Nike",
    "sepatu nike": "Nike",
    "kaos hitam": "Black Plain T-Shirt",
    "kaos polos hitam": "Black Plain T-Shirt",
    "baju hitam": "Black Plain T-Shirt",
    "t-shirt hitam": "Black Plain T-Shirt",
    "tas eiger": "Eiger",
    "headphone sony": "Sony",
    "sony headphone": "Sony",
    "sony headphones": "Sony",
    "jam casio": "Casio",
}


def normalize_product_query(product_name: str) -> str:
    """Map common natural-language product aliases to searchable catalog terms."""
    product_key = product_name.lower().strip()
    return PRODUCT_ALIASES.get(product_key, product_name)

def get_connection():
    """Create a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Access query results by column name
    return conn

def init_database():
    """Create tables and populate dummy data if the database is empty."""
    conn = get_connection()
    cursor = conn.cursor()

    # ==================== PRODUCTS TABLE ====================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL,
            stock INTEGER NOT NULL,
            country TEXT NOT NULL DEFAULT 'Indonesia'
        )
    """)

    # ==================== ORDERS TABLE ====================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            customer_name TEXT NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            total_price REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'Processing',
            shipping_address TEXT,
            order_date TEXT NOT NULL,
            estimated_arrival TEXT,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)

    # ==================== SHOPPING CART TABLE (Feature 3) ====================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shopping_cart (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL DEFAULT 'default',
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            added_at TEXT NOT NULL,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)

    # ==================== SUPPORT TICKETS TABLE (Feature 5) ====================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS support_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_message TEXT NOT NULL,
            agent_summary TEXT,
            priority TEXT NOT NULL DEFAULT 'Normal',
            status TEXT NOT NULL DEFAULT 'Open',
            created_at TEXT NOT NULL
        )
    """)

    # Check if product data already exists
    cursor.execute("SELECT COUNT(*) FROM products")
    if cursor.fetchone()[0] == 0:
        # ==================== DUMMY PRODUCT DATA ====================
        products = [
            ("Nike Air Max Shoes",         "Shoes",        1_200_000, 50,  "Indonesia"),
            ("Adidas Ultraboost Shoes",    "Shoes",        1_500_000, 35,  "Indonesia"),
            ("Black Plain T-Shirt",        "Clothing",        89_000, 200, "Indonesia"),
            ("Oversize Denim Jacket",      "Clothing",       350_000, 80,  "Indonesia"),
            ("Eiger Backpack",             "Bags",           450_000, 60,  "Indonesia"),
            ("Galaxy Fit Smartwatch",      "Electronics",  1_800_000, 25,  "Indonesia"),
            ("Sony WH-1000 Headphone",     "Electronics",  3_200_000, 15,  "Japan"),
            ("Mechanical RGB Keyboard",    "Electronics",    550_000, 40,  "China"),
            ("Logitech G502 Mouse",        "Electronics",    750_000, 30,  "United States"),
            ("Eau de Toilette Perfume",    "Beauty",         280_000, 100, "France"),
            ("Premium Skincare Set",       "Beauty",         499_000, 70,  "South Korea"),
            ("Python Programming Book",   "Books",           95_000, 150, "Indonesia"),
            ("Birkenstock Sandals",        "Shoes",        1_100_000, 20,  "Germany"),
            ("Polarized Sunglasses",       "Accessories",    175_000, 90,  "Italy"),
            ("Casio Classic Watch",        "Accessories",    650_000, 45,  "Japan"),
        ]
        cursor.executemany(
            "INSERT INTO products (name, category, price, stock, country) VALUES (?, ?, ?, ?, ?)",
            products
        )

        # ==================== DUMMY ORDER DATA ====================
        orders = [
            ("ORD001", "Budi Santoso",    1, 2, 2_400_000, "Shipped",              "Jl. Merdeka No. 10, Jakarta",     "2026-03-18", "2026-03-25"),
            ("ORD002", "Siti Aminah",     3, 5,   445_000, "Processing",           "Jl. Asia Afrika No. 5, Bandung",  "2026-03-20", "2026-03-28"),
            ("ORD003", "Andi Wijaya",     7, 1, 3_200_000, "Completed",            "Jl. Sudirman No. 88, Surabaya",   "2026-03-10", "2026-03-15"),
            ("ORD004", "Rina Kartika",   10, 3,   840_000, "Shipped",              "Jl. Diponegoro No. 12, Semarang", "2026-03-19", "2026-03-26"),
            ("ORD005", "Doni Pratama",    6, 1, 1_800_000, "Awaiting Payment",     "Jl. Gajah Mada No. 3, Medan",     "2026-03-21", None),
            ("ORD006", "Lina Susanti",    5, 1,   450_000, "Shipped",              "Jl. Pemuda No. 22, Yogyakarta",   "2026-03-17", "2026-03-24"),
            ("ORD007", "Hendra Gunawan", 13, 1, 1_100_000, "Completed",            "Jl. Braga No. 45, Bandung",       "2026-03-05", "2026-03-12"),
            ("ORD008", "Maya Putri",     11, 2,   998_000, "Processing",           "Jl. Malioboro No. 9, Yogyakarta", "2026-03-22", "2026-03-30"),
        ]
        cursor.executemany(
            "INSERT INTO orders (id, customer_name, product_id, quantity, total_price, status, shipping_address, order_date, estimated_arrival) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            orders
        )

    conn.commit()
    conn.close()
    print(f"Database initialized successfully at: {DB_PATH}")


def reset_database():
    """Reset database contents to the original dummy baseline data."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM support_tickets")
    cursor.execute("DELETE FROM shopping_cart")
    cursor.execute("DELETE FROM orders")
    cursor.execute("DELETE FROM products")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('products', 'shopping_cart', 'support_tickets')")

    conn.commit()
    conn.close()
    init_database()


# =====================================================================
# QUERY FUNCTIONS USED BY AGENT TOOLS
# =====================================================================

# --- Feature 0: Original Stock Check ---
def query_stock(product_name: str) -> str:
    """Search product stock by name (partial match)."""
    search_term = normalize_product_query(product_name)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name, category, price, stock, country FROM products WHERE LOWER(name) LIKE LOWER(?)",
        (f"%{search_term}%",)
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return f"No products found matching '{product_name}' in the database."

    results = []
    for r in rows:
        results.append(
            f"• {r['name']} | Category: {r['category']} | Price: Rp{r['price']:,.0f} | Stock: {r['stock']} units | Origin: {r['country']}"
        )
    return "\n".join(results)


# --- Feature 0: Original Order Check ---
def query_order(order_id: str) -> str:
    """Search order status by order ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT o.id, o.customer_name, p.name as product_name, o.quantity, o.total_price,
                  o.status, o.shipping_address, o.order_date, o.estimated_arrival
           FROM orders o
           JOIN products p ON o.product_id = p.id
           WHERE UPPER(o.id) = UPPER(?)""",
        (order_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return f"Order with ID '{order_id}' not found in the database."

    arrival = row['estimated_arrival'] if row['estimated_arrival'] else "Not yet determined"
    return (
        f"📦 Order Details — {row['id']}:\n"
        f"• Customer: {row['customer_name']}\n"
        f"• Product: {row['product_name']} (x{row['quantity']})\n"
        f"• Total: Rp{row['total_price']:,.0f}\n"
        f"• Status: {row['status']}\n"
        f"• Address: {row['shipping_address']}\n"
        f"• Order Date: {row['order_date']}\n"
        f"• Estimated Arrival: {arrival}"
    )


# --- Feature 1: Smart Product Recommender ---
def query_products_by_filter(category: str = "", max_price: float = 0, min_price: float = 0) -> str:
    """Search products by category and/or price range."""
    conn = get_connection()
    cursor = conn.cursor()

    query = "SELECT name, category, price, stock, country FROM products WHERE 1=1"
    params = []

    if category:
        query += " AND LOWER(category) LIKE LOWER(?)"
        params.append(f"%{category}%")
    if min_price > 0:
        query += " AND price >= ?"
        params.append(min_price)
    if max_price > 0:
        query += " AND price <= ?"
        params.append(max_price)

    query += " ORDER BY price ASC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        filters = []
        if category:
            filters.append(f"category='{category}'")
        if min_price > 0:
            filters.append(f"min_price=Rp{min_price:,.0f}")
        if max_price > 0:
            filters.append(f"max_price=Rp{max_price:,.0f}")
        return f"No products found matching filters: {', '.join(filters)}."

    results = [f"Found {len(rows)} product(s):"]
    for r in rows:
        results.append(
            f"• {r['name']} | Category: {r['category']} | Price: Rp{r['price']:,.0f} | Stock: {r['stock']} units | Origin: {r['country']}"
        )
    return "\n".join(results)


# --- Feature 2: Cancel Order ---
def cancel_order(order_id: str) -> str:
    """Cancel an order if it is still in 'Processing' or 'Awaiting Payment' status."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, status, customer_name FROM orders WHERE UPPER(id) = UPPER(?)", (order_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return f"Order '{order_id}' not found in the database."

    if row['status'] in ('Completed', 'Shipped'):
        conn.close()
        return f"❌ Cannot cancel order {row['id']}. Current status is '{row['status']}'. Only orders with status 'Processing' or 'Awaiting Payment' can be cancelled."

    if row['status'] == 'Cancelled':
        conn.close()
        return f"Order {row['id']} has already been cancelled."

    cursor.execute("UPDATE orders SET status = 'Cancelled' WHERE UPPER(id) = UPPER(?)", (order_id,))
    conn.commit()
    conn.close()
    return f"✅ Order {row['id']} for customer '{row['customer_name']}' has been successfully cancelled. Previous status: '{row['status']}' → New status: 'Cancelled'."


# --- Feature 2: Update Shipping Address ---
def update_order_address(order_id: str, new_address: str) -> str:
    """Update the shipping address of an order if it has not been shipped yet."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, status, shipping_address FROM orders WHERE UPPER(id) = UPPER(?)", (order_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return f"Order '{order_id}' not found in the database."

    if row['status'] in ('Shipped', 'Completed', 'Cancelled'):
        conn.close()
        return f"❌ Cannot update address for order {row['id']}. Current status is '{row['status']}'. Address can only be changed for 'Processing' or 'Awaiting Payment' orders."

    old_address = row['shipping_address']
    cursor.execute("UPDATE orders SET shipping_address = ? WHERE UPPER(id) = UPPER(?)", (new_address, order_id))
    conn.commit()
    conn.close()
    return f"✅ Shipping address for order {row['id']} has been updated.\n• Old address: {old_address}\n• New address: {new_address}"


# --- Feature 3: Shopping Cart ---
def add_to_cart(product_name: str, quantity: int = 1, session_id: str = "default") -> str:
    """Add a product to the shopping cart by product name."""
    search_term = normalize_product_query(product_name)
    conn = get_connection()
    cursor = conn.cursor()

    # Find the product first
    cursor.execute("SELECT id, name, price, stock FROM products WHERE LOWER(name) LIKE LOWER(?)", (f"%{search_term}%",))
    rows = cursor.fetchall()

    if not rows:
        conn.close()
        return f"Product '{product_name}' not found. Please check the product name and try again."

    if len(rows) > 1:
        names = ", ".join([r['name'] for r in rows])
        conn.close()
        return f"Multiple products matched '{product_name}': {names}. Please be more specific."

    product = rows[0]
    if quantity > product['stock']:
        conn.close()
        return f"❌ Insufficient stock for '{product['name']}'. Requested: {quantity}, Available: {product['stock']} units."

    # Check if product already in cart
    cursor.execute(
        "SELECT id, quantity FROM shopping_cart WHERE session_id = ? AND product_id = ?",
        (session_id, product['id'])
    )
    existing = cursor.fetchone()

    if existing:
        new_qty = existing['quantity'] + quantity
        cursor.execute("UPDATE shopping_cart SET quantity = ? WHERE id = ?", (new_qty, existing['id']))
    else:
        cursor.execute(
            "INSERT INTO shopping_cart (session_id, product_id, quantity, added_at) VALUES (?, ?, ?, ?)",
            (session_id, product['id'], quantity, datetime.now().isoformat())
        )

    conn.commit()
    conn.close()
    total = product['price'] * quantity
    return f"🛒 Added to cart: {product['name']} x{quantity} (Rp{total:,.0f})"


def view_cart(session_id: str = "default") -> str:
    """View all items currently in the shopping cart."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT p.name, p.price, c.quantity, (p.price * c.quantity) as subtotal
           FROM shopping_cart c
           JOIN products p ON c.product_id = p.id
           WHERE c.session_id = ?""",
        (session_id,)
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return "🛒 Your shopping cart is empty."

    results = ["🛒 Your Shopping Cart:"]
    grand_total = 0
    for r in rows:
        results.append(f"• {r['name']} x{r['quantity']} — Rp{r['subtotal']:,.0f}")
        grand_total += r['subtotal']
    results.append(f"\n💰 Grand Total: Rp{grand_total:,.0f}")
    return "\n".join(results)


def clear_cart(session_id: str = "default") -> str:
    """Remove all items from the shopping cart."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM shopping_cart WHERE session_id = ?", (session_id,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    if deleted == 0:
        return "🛒 Cart is already empty, nothing to clear."
    return f"🗑️ Shopping cart cleared. {deleted} item(s) removed."


# --- Feature 5: Human Handoff / Support Tickets ---
def create_support_ticket(customer_message: str, agent_summary: str = "", priority: str = "Normal") -> str:
    """Create a support ticket for human escalation."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO support_tickets (customer_message, agent_summary, priority, status, created_at) VALUES (?, ?, ?, 'Open', ?)",
        (customer_message, agent_summary, priority, datetime.now().isoformat())
    )
    ticket_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return f"🎫 Support ticket #{ticket_id} created successfully (Priority: {priority}). A human agent will review your case within 1x24 hours."


# Run init when this file is executed directly
if __name__ == "__main__":
    init_database()
