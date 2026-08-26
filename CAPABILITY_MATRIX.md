# Capability Matrix

Inventory of existing agent capabilities in the `prototype-v2` baseline.

## Risk Classification

| Risk Level | Meaning |
|---|---|
| Low | Read-only access or informational retrieval. Does not modify database state. |
| Medium | Writes non-critical operational data such as cart contents or support tickets. Reversible or low business impact. |
| High | Writes customer order data or changes fulfillment-related state. Higher business impact and should require stronger guardrails. |

## Matrix

| Tool | Access | Risk | Backend Function | Data Surface | Description |
|---|---|---|---|---|---|
| `check_stock` | READ | LOW | `query_stock` | `products` | Searches product availability by partial product name. |
| `check_order_status` | READ | LOW | `query_order` | `orders`, `products` | Retrieves order status, customer, product, shipping address, order date, and ETA. |
| `search_products` | READ | LOW | `query_products_by_filter` | `products` | Filters and lists products by category and/or price range. |
| `search_knowledge_base` | READ | LOW | local text search | `knowledge_base.txt` | Searches policy and FAQ content for returns, refunds, shipping, warranty, payments, hours, loyalty, and contact info. |
| `view_shopping_cart` | READ | LOW | `view_cart` | `shopping_cart`, `products` | Displays current cart items, quantities, subtotals, and grand total. |
| `add_product_to_cart` | WRITE | MEDIUM | `add_to_cart` | `shopping_cart`, `products` | Adds a product to the cart or increases existing cart quantity after stock validation. |
| `clear_shopping_cart` | WRITE | MEDIUM | `clear_cart` | `shopping_cart` | Removes all items from the current cart session. |
| `escalate_to_human` | WRITE | MEDIUM | `create_support_ticket` | `support_tickets` | Creates a human support ticket with customer message, reason, priority, status, and timestamp. |
| `cancel_customer_order` | WRITE | HIGH | `cancel_order` | `orders` | Changes eligible order status to `Cancelled`; allowed only for `Processing` or `Awaiting Payment`. |
| `update_shipping_address` | WRITE | HIGH | `update_order_address` | `orders` | Updates shipping address for eligible unshipped orders. |

## Grouped View

### READ

| Tool | Risk |
|---|---|
| `check_stock` | LOW |
| `check_order_status` | LOW |
| `search_products` | LOW |
| `search_knowledge_base` | LOW |
| `view_shopping_cart` | LOW |

### WRITE

| Tool | Risk |
|---|---|
| `add_product_to_cart` | MEDIUM |
| `clear_shopping_cart` | MEDIUM |
| `escalate_to_human` | MEDIUM |
| `cancel_customer_order` | HIGH |
| `update_shipping_address` | HIGH |

### LOW RISK

| Tool | Access |
|---|---|
| `check_stock` | READ |
| `check_order_status` | READ |
| `search_products` | READ |
| `search_knowledge_base` | READ |
| `view_shopping_cart` | READ |

### MEDIUM RISK

| Tool | Access |
|---|---|
| `add_product_to_cart` | WRITE |
| `clear_shopping_cart` | WRITE |
| `escalate_to_human` | WRITE |

### HIGH RISK

| Tool | Access |
|---|---|
| `cancel_customer_order` | WRITE |
| `update_shipping_address` | WRITE |

## Notes

- The current cart implementation uses the default session id `default`, so cart operations are shared unless session-specific IDs are introduced.
- `check_order_status` is read-only, but it exposes customer and shipping information. It is classified as LOW for write-risk, but should receive privacy guardrails before production use.
- HIGH-risk write tools should be candidates for confirmation, authorization, and audit logging in future phases.
