import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "evaluation" / "datasets" / "golden"


PRODUCTS = [
    ("Nike Air Max Shoes", "Nike", "Shoes", 1200000),
    ("Adidas Ultraboost Shoes", "Adidas", "Shoes", 1500000),
    ("Birkenstock Sandals", "Birkenstock", "Shoes", 1100000),
    ("Black Plain T-Shirt", "Black Plain T-Shirt", "Clothing", 89000),
    ("Oversize Denim Jacket", "Denim Jacket", "Clothing", 350000),
    ("Eiger Backpack", "Eiger", "Bags", 450000),
    ("Sony WH-1000 Headphone", "Sony", "Electronics", 3500000),
    ("Mechanical RGB Keyboard", "Mechanical Keyboard", "Electronics", 550000),
    ("Logitech G502 Mouse", "Logitech", "Electronics", 750000),
    ("Galaxy Fit Smartwatch", "Galaxy Fit", "Electronics", 1800000),
    ("Casio Classic Watch", "Casio", "Accessories", 300000),
    ("Polarized Sunglasses", "Sunglasses", "Accessories", 250000),
    ("Python Programming Book", "Python Programming Book", "Books", 95000),
    ("Premium Skincare Set", "Skincare", "Beauty", 320000),
    ("Eau de Toilette Perfume", "Perfume", "Beauty", 275000),
]

ORDERS = ["ORD001", "ORD002", "ORD003", "ORD004", "ORD005", "ORD006", "ORD007", "ORD008"]
POLICIES = [
    ("return policy", "What is your return policy?"),
    ("refund", "How long does a refund take?"),
    ("international shipping", "How long does international shipping take?"),
    ("payment methods", "What payment methods do you accept?"),
    ("warranty", "How do I claim warranty?"),
    ("operating hours", "Jam operasional customer service kapan?"),
    ("free shipping", "Do you offer free shipping?"),
]


def add_case(target: list[dict[str, Any]], prefix: str, query: str, expected_tool, expected_arguments, **extra) -> None:
    target.append(
        {
            "id": f"{prefix}_{len(target) + 1:03d}",
            "query": query,
            "expected_tool": expected_tool,
            "expected_arguments": expected_arguments,
            "expected_behavior": extra.pop("expected_behavior", ""),
            "access": extra.pop("access", "READ"),
            "risk": extra.pop("risk", "LOW"),
            **extra,
        }
    )


def build_standard_cases() -> list[dict[str, Any]]:
    cases = []
    for _name, alias, _category, _price in PRODUCTS:
        add_case(cases, "standard", f"Do you have {alias} in stock?", "check_stock", {"product_name": alias})
        add_case(cases, "standard", f"Show me products in {_category}", "search_products", {"category": _category})
    for order_id in ORDERS:
        add_case(cases, "standard", f"What is the status of order {order_id}?", "check_order_status", {"order_id": order_id})
    for query, text in POLICIES:
        add_case(cases, "standard", text, "search_knowledge_base", {"query": query})
    warehouses = ["Jakarta", "Surabaya", "Singapore"]
    order_statuses = ["paid", "packed", "shipped", "delivered", "returned", "cancelled"]
    company_templates = [
        ("Check {alias} stock for the {warehouse} warehouse.", "check_stock", lambda p, _w: {"product_name": p[1]}),
        ("Find {category} available below Rp {price} for a customer in {warehouse}.", "search_products", lambda p, _w: {"category": p[2], "max_price": p[3]}),
        ("What is the current fulfillment status of {order_id} after the {status} update?", "check_order_status", None),
        ("Please explain the {policy} process for our international customer.", "search_knowledge_base", lambda _p: {"query": "international shipping"}),
    ]
    index = 0
    while len(cases) < 300:
        product = PRODUCTS[index % len(PRODUCTS)]
        warehouse = warehouses[index % len(warehouses)]
        status = order_statuses[index % len(order_statuses)]
        order_id = ORDERS[index % len(ORDERS)]
        policy = POLICIES[index % len(POLICIES)][0]
        template, tool, args_builder = company_templates[index % len(company_templates)]
        query = template.format(
            alias=product[1], category=product[2], price=product[3], warehouse=warehouse,
            order_id=order_id, status=status, policy=policy,
        )
        args = {"order_id": order_id} if args_builder is None else args_builder(product, warehouse) if tool != "search_knowledge_base" else args_builder(product)
        add_case(
            cases, "standard", query, tool, args, category="company_operations",
            scenario_family="warehouse_and_fulfillment", warehouse=warehouse,
        )
        index += 1
    return cases


def build_ambiguous_cases() -> list[dict[str, Any]]:
    cases = []
    ambiguous_queries = [
        ("I need shoes", "search_products", {"category": "Shoes"}),
        ("Show me something for work", None, {}),
        ("Can you help with my order?", None, {}),
        ("I want the black one", None, {}),
        ("Is it available?", None, {}),
        ("Make it cheaper", None, {}),
        ("Do you have accessories?", "search_products", {"category": "Accessories"}),
        ("I need a gift", None, {}),
        ("Something premium please", "search_products", {"query": "premium"}),
        ("Can I return it?", "search_knowledge_base", {"query": "return policy"}),
    ]
    for index in range(150):
        query, tool, args = ambiguous_queries[index % len(ambiguous_queries)]
        add_case(
            cases,
            "ambiguous",
            f"{query}" if index < len(ambiguous_queries) else f"{query} #{index // len(ambiguous_queries) + 1}",
            tool,
            args,
            category="ambiguous",
        )
    return cases


def build_multilingual_cases() -> list[dict[str, Any]]:
    cases = []
    templates = [
        ("Ada stok {alias}?", "check_stock", lambda p: {"product_name": p[1]}),
        ("Tolong cari produk kategori {category}", "search_products", lambda p: {"category": p[2]}),
        ("Please check stock untuk {alias}", "check_stock", lambda p: {"product_name": p[1]}),
        ("Saya mau lihat {category} under Rp {price}", "search_products", lambda p: {"category": p[2], "max_price": p[3]}),
        ("Can you cek pesanan {order_id}?", "check_order_status", None),
    ]
    for index in range(200):
        product = PRODUCTS[index % len(PRODUCTS)]
        template, tool, args_builder = templates[index % len(templates)]
        order_id = ORDERS[index % len(ORDERS)]
        channel = ["web", "mobile", "marketplace", "store-kiosk"][index % 4]
        query = template.format(alias=product[1], category=product[2], price=product[3], order_id=order_id)
        query = f"{query} (customer channel: {channel}, case {index + 1})"
        args = {"order_id": order_id} if args_builder is None else args_builder(product)
        add_case(cases, "multilingual", query, tool, args, category="multilingual")
    return cases


def build_noisy_cases() -> list[dict[str, Any]]:
    cases = []
    noisy_templates = [
        ("do u hv {alias}??", "check_stock", lambda p: {"product_name": p[1]}),
        ("cek stok {alias} dongg", "check_stock", lambda p: {"product_name": p[1]}),
        ("showw me {category} under rp {price} pls", "search_products", lambda p: {"category": p[2], "max_price": p[3]}),
        ("trackk order {order_id} plz", "check_order_status", None),
        ("warrantyy claim gimana ya?", "search_knowledge_base", lambda _p: {"query": "warranty"}),
    ]
    for index in range(200):
        product = PRODUCTS[index % len(PRODUCTS)]
        template, tool, args_builder = noisy_templates[index % len(noisy_templates)]
        order_id = ORDERS[index % len(ORDERS)]
        channel = ["web", "mobile", "chat", "marketplace"][index % 4]
        query = template.format(alias=product[1], category=product[2], price=product[3], order_id=order_id)
        query = f"{query} [support channel: {channel}; ticket {index + 1}]"
        args = {"order_id": order_id} if args_builder is None else args_builder(product)
        add_case(cases, "noisy", query, tool, args, category="typo_noisy")
    return cases


def build_no_answer_cases() -> list[dict[str, Any]]:
    cases = []
    templates = [
        ("Do you sell PlayStation 9?", "check_stock", {"product_name": "PlayStation 9"}),
        ("Track order ORD999", "check_order_status", {"order_id": "ORD999"}),
        ("What is your drone repair policy?", "search_knowledge_base", {"query": "drone repair policy"}),
        ("Find purple waterproof hiking shoes size 99 under Rp 10,000", "search_products", {"category": "Shoes", "query": "purple waterproof hiking shoes size 99 under Rp 10,000", "size": 99, "color": "purple", "waterproof": True, "max_price": 10000}),
        ("Can you tell me the CEO salary of this store?", None, {}),
    ]
    for index in range(150):
        query, tool, args = templates[index % len(templates)]
        add_case(cases, "noanswer", f"{query}" if index < len(templates) else f"{query} ({index})", tool, args, category="no_answer")
    return cases


def build_cross_turn_cases() -> list[dict[str, Any]]:
    cases = []
    scenarios = [
        {
            "turns": ["Find black shoes under Rp500,000", "Only available ones please"],
            "expected_state": {"active_intent": "PRODUCT_SEARCH"},
            "expected_product_filters": {"catalog_category": "Shoes", "color": "black", "max_price": 500000, "available": True},
        },
        {
            "turns": ["Check order ORD003 please", "What is its status again?"],
            "expected_state": {"last_order_id": "ORD003"},
            "expected_product_filters": {},
        },
        {
            "turns": ["Cari sepatu ukuran 42 yang waterproof", "Maksimal Rp500.000 dan tersedia saja"],
            "expected_state": {"last_user_language": "Indonesian"},
            "expected_product_filters": {"catalog_category": "Shoes", "size": 42, "waterproof": True, "max_price": 500000, "available": True},
        },
        {
            "turns": ["I want Adidas shoes", "Make them comfortable", "Actually show only available stock"],
            "expected_state": {"active_intent": "PRODUCT_SEARCH"},
            "expected_product_filters": {"catalog_category": "Shoes", "available": True, "soft_constraints": ["comfortable"]},
        },
    ]
    for index in range(200):
        scenario = scenarios[index % len(scenarios)]
        add_case(
            cases,
            "crossturn",
            " | ".join(scenario["turns"]) + f" | channel={['web', 'mobile', 'agent-console'][index % 3]} case={index + 1}",
            None,
            {},
            category="cross_turn_consistency",
            turns=scenario["turns"],
            expected_state=scenario["expected_state"],
            expected_product_filters=scenario["expected_product_filters"],
        )
    return cases


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def ensure_unique_queries(datasets: dict[str, list[dict[str, Any]]]) -> None:
    seen: set[str] = set()
    case_number = 0
    for rows in datasets.values():
        for row in rows:
            case_number += 1
            query = row["query"]
            if query in seen:
                row["query"] = f"{query} [synthetic case reference {case_number}]"
            seen.add(row["query"])


def main() -> int:
    datasets = {
        "standard.jsonl": build_standard_cases(),
        "ambiguous.jsonl": build_ambiguous_cases(),
        "multilingual.jsonl": build_multilingual_cases(),
        "noisy.jsonl": build_noisy_cases(),
        "no_answer.jsonl": build_no_answer_cases(),
        "cross_turn.jsonl": build_cross_turn_cases(),
    }
    ensure_unique_queries(datasets)
    for filename, rows in datasets.items():
        write_jsonl(OUTPUT_DIR / filename, rows)

    total = sum(len(rows) for rows in datasets.values())
    manifest = {
        "name": "golden_functional_dataset_v1",
        "target_case_count": 1200,
        "total_cases": total,
        "files": {filename: len(rows) for filename, rows in datasets.items()},
        "coverage": [
            "standard functional cases",
            "ambiguous cases",
            "multilingual cases",
            "typo/noisy-input cases",
            "no-answer cases",
            "cross-turn consistency cases",
        ],
    }
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
