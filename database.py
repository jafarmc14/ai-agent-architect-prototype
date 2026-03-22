import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "toko.db")

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

    # Check if data already exists
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


# === Query functions used by Agent Tools ===
def query_stock(product_name: str) -> str:
    """Search product stock by name (partial match)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name, category, price, stock, country FROM products WHERE LOWER(name) LIKE LOWER(?)",
        (f"%{product_name}%",)
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


# Run init when this file is executed directly
if __name__ == "__main__":
    init_database()
