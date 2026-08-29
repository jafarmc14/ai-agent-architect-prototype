import re
from dataclasses import dataclass
from enum import Enum


class Intent(str, Enum):
    PRODUCT_SEARCH = "PRODUCT_SEARCH"
    PRODUCT_INFO = "PRODUCT_INFO"
    PRODUCT_COMPARE = "PRODUCT_COMPARE"
    ORDER_STATUS = "ORDER_STATUS"
    RETURN_POLICY = "RETURN_POLICY"
    CART = "CART"
    TRANSACTION = "TRANSACTION"
    COMPLAINT = "COMPLAINT"
    ESCALATION = "ESCALATION"
    GENERAL_FAQ = "GENERAL_FAQ"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RouteDecision:
    intent: Intent
    workflow: str
    use_agent_loop: bool
    reason: str


ORDER_ID_PATTERN = re.compile(r"\bORD\d+\b", re.IGNORECASE)


def classify_intent(user_input: str) -> Intent:
    text = user_input.lower().strip()
    tokens = set(re.findall(r"[a-zA-Z0-9]+", text))

    if not text:
        return Intent.UNKNOWN

    if _has_any(text, ["human agent", "real person", "customer service", "speak to human", "talk to human"]):
        return Intent.ESCALATION
    if _has_any(text, ["admin manusia", "orang asli", "manusia", "customer service"]) or "cs" in tokens:
        return Intent.ESCALATION

    if _has_any(text, ["angry", "frustrated", "ridiculous", "complaint", "complain", "damaged", "broken"]):
        return Intent.COMPLAINT
    if _has_any(text, ["marah", "kecewa", "komplain", "rusak", "cacat", "barang rusak"]):
        return Intent.COMPLAINT

    if _has_any(text, ["cancel order", "cancel my order", "change the address", "update address", "shipping address"]):
        return Intent.TRANSACTION
    if _has_any(text, ["batalkan pesanan", "ubah alamat", "ganti alamat", "alamat pengiriman"]):
        return Intent.TRANSACTION

    if _has_any(text, ["cart", "basket", "add ", "clear cart", "checkout"]):
        return Intent.CART
    if _has_any(text, ["keranjang", "troli", "masukkan", "tambahkan", "checkout"]):
        return Intent.CART

    if ORDER_ID_PATTERN.search(text) and _has_any(text, ["status", "track", "where", "arrived", "order", "pesanan", "cek"]):
        return Intent.ORDER_STATUS

    if _has_any(text, ["compare", "comparison", " vs ", " versus ", "better between"]):
        return Intent.PRODUCT_COMPARE
    if _has_any(text, ["bandingkan", "dibanding", "lebih bagus"]):
        return Intent.PRODUCT_COMPARE

    if _has_any(text, ["return", "refund", "shipping", "delivery", "warranty", "payment method", "policy"]):
        return Intent.RETURN_POLICY
    if _has_any(text, ["retur", "pengembalian", "refund", "ongkir", "pengiriman", "garansi", "metode pembayaran", "kebijakan"]):
        return Intent.RETURN_POLICY

    if _has_any(text, ["faq", "hours", "open", "loyalty", "member", "store location"]):
        return Intent.GENERAL_FAQ
    if _has_any(text, ["jam buka", "loyalty", "member", "lokasi toko", "toko buka"]):
        return Intent.GENERAL_FAQ

    if _has_any(text, ["stock", "available", "availability", "price", "detail", "origin"]):
        return Intent.PRODUCT_INFO
    if _has_any(text, ["stok", "tersedia", "harga", "detail", "asal"]):
        return Intent.PRODUCT_INFO

    if _has_any(text, ["find", "search", "show", "list", "looking for", "recommend"]):
        return Intent.PRODUCT_SEARCH
    if _has_any(text, ["cari", "tampilkan", "daftar", "rekomendasi", "produk", "sepatu", "baju"]):
        return Intent.PRODUCT_SEARCH

    if tokens & {"hello", "hi", "thanks", "thank", "help", "halo", "hai", "terima", "bantu"}:
        return Intent.GENERAL_FAQ

    return Intent.UNKNOWN


def route_intent(user_input: str) -> RouteDecision:
    intent = classify_intent(user_input)

    if intent == Intent.RETURN_POLICY and not _looks_complex(user_input):
        return RouteDecision(
            intent=intent,
            workflow="rag_policy",
            use_agent_loop=False,
            reason="simple policy/FAQ question can use direct RAG workflow",
        )

    if intent == Intent.GENERAL_FAQ and _is_document_faq_question(user_input) and not _looks_complex(user_input):
        return RouteDecision(
            intent=intent,
            workflow="rag_policy",
            use_agent_loop=False,
            reason="simple documented FAQ question can use direct RAG workflow",
        )

    if intent == Intent.ORDER_STATUS and ORDER_ID_PATTERN.search(user_input):
        return RouteDecision(
            intent=intent,
            workflow="order_status",
            use_agent_loop=False,
            reason="simple order-status request has an explicit order id",
        )

    if intent == Intent.PRODUCT_SEARCH and not _looks_complex(user_input):
        return RouteDecision(
            intent=intent,
            workflow="product_search",
            use_agent_loop=False,
            reason="simple product search can use structured product workflow",
        )

    return RouteDecision(
        intent=intent,
        workflow="agent_loop",
        use_agent_loop=True,
        reason="complex or write-capable request needs the agent loop",
    )


def _looks_complex(text: str) -> bool:
    lowered = text.lower()
    complex_markers = [
        " and ",
        " also ",
        "then ",
        "damaged",
        "broken",
        "complaint",
        "frustrated",
        "angry",
        "refund and",
        "replacement",
        " lalu ",
        " juga ",
        " kemudian ",
        " rusak",
        " komplain",
    ]
    return any(marker in lowered for marker in complex_markers)


def _is_document_faq_question(text: str) -> bool:
    lowered = text.lower()
    faq_markers = [
        "faq",
        "hours",
        "open",
        "loyalty",
        "member",
        "store location",
        "jam buka",
        "lokasi toko",
        "toko buka",
    ]
    return any(marker in lowered for marker in faq_markers)


def _has_any(text: str, phrases: list[str]) -> bool:
    return any(phrase in text for phrase in phrases)
