from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any


class FactSource(str, Enum):
    DATABASE = "database_fact"
    RAG = "rag_fact"
    GENERATED_PROSE = "generated_prose"


DATABASE_FACT_MARKERS = {
    "address",
    "alamat",
    "available",
    "budget",
    "cart",
    "category",
    "harga",
    "inventory",
    "keranjang",
    "order",
    "pesanan",
    "price",
    "product",
    "produk",
    "shipping address",
    "sku",
    "status",
    "stock",
    "stok",
    "total",
    "unit",
    "units",
}

RAG_FACT_MARKERS = {
    "cod",
    "faq",
    "payment",
    "payments",
    "policy",
    "refund",
    "return",
    "returns",
    "shipping",
    "warranty",
}

SUPPORT_FACT_MARKERS = {
    "support ticket",
    "ticket",
    "human agent",
    "priority",
    "escalation",
}

CRITICAL_BUSINESS_MARKERS = RAG_FACT_MARKERS | {
    "budget",
    "business day",
    "business days",
    "estimated arrival",
    "hari kerja",
    "order",
    "pesanan",
    "price",
    "refund status",
    "shipping address",
    "sku",
    "status",
    "stock",
    "stok",
    "total",
    "unit",
    "units",
}


@dataclass(frozen=True)
class ClassifiedClaim:
    text: str
    source: FactSource
    critical: bool
    supported: bool
    reason: str
    evidence_type: str = ""
    evidence_snippet: str = ""


@dataclass(frozen=True)
class ClaimAuditResult:
    claims: list[ClassifiedClaim] = field(default_factory=list)
    unsupported_claims: list[ClassifiedClaim] = field(default_factory=list)
    unsupported_critical_claims: list[ClassifiedClaim] = field(default_factory=list)
    unsupported_claim_rate: float = 0.0
    unsupported_critical_claim_count: int = 0
    should_abstain: bool = False

    @property
    def passed(self) -> bool:
        return self.unsupported_critical_claim_count == 0 and self.unsupported_claim_rate < 0.01


def audit_response_claims(
    response: str,
    *,
    tool_outputs: list[str] | None = None,
    rag_evidence: str = "",
) -> ClaimAuditResult:
    claims = classify_factual_claims(response, tool_outputs=tool_outputs, rag_evidence=rag_evidence)
    unsupported = [claim for claim in claims if not claim.supported]
    unsupported_critical = [claim for claim in unsupported if claim.critical]
    rate = len(unsupported) / len(claims) if claims else 0.0
    return ClaimAuditResult(
        claims=claims,
        unsupported_claims=unsupported,
        unsupported_critical_claims=unsupported_critical,
        unsupported_claim_rate=round(rate, 4),
        unsupported_critical_claim_count=len(unsupported_critical),
        should_abstain=bool(unsupported_critical),
    )


def classify_factual_claims(
    response: str,
    *,
    tool_outputs: list[str] | None = None,
    rag_evidence: str = "",
) -> list[ClassifiedClaim]:
    database_evidence = "\n".join(tool_outputs or [])
    all_evidence = "\n".join(part for part in [database_evidence, rag_evidence] if part)
    claims = []
    for sentence in _split_sentences(response):
        source = _classify_source(sentence)
        critical = _is_critical(sentence)
        if source == FactSource.GENERATED_PROSE:
            supported = True
            reason = "Generated prose does not contain critical business facts."
            evidence_type = ""
            snippet = ""
        elif source == FactSource.RAG:
            supported, reason, snippet = _supported_by_evidence(sentence, rag_evidence or all_evidence)
            evidence_type = "rag"
        else:
            supported, reason, snippet = _supported_by_evidence(sentence, database_evidence)
            evidence_type = "database"

        claims.append(
            ClassifiedClaim(
                text=sentence,
                source=source,
                critical=critical,
                supported=supported,
                reason=reason,
                evidence_type=evidence_type,
                evidence_snippet=snippet,
            )
        )
    return claims


def hallucination_abstention_message(language_hint: str = "English") -> str:
    if language_hint.lower().startswith("indonesian"):
        return (
            "Maaf, saya belum punya bukti yang cukup dari database atau dokumen resmi "
            "untuk menjawab fakta bisnis itu dengan aman."
        )
    return (
        "Sorry, I do not have enough verified evidence from the database or official documents "
        "to answer that business fact safely."
    )


def _classify_source(sentence: str) -> FactSource:
    lowered = sentence.lower()
    if _is_non_factual_caveat(lowered):
        return FactSource.GENERATED_PROSE
    if _contains_any(lowered, SUPPORT_FACT_MARKERS):
        return FactSource.DATABASE
    if _contains_any(lowered, RAG_FACT_MARKERS) or re.search(r"\bC\d+\b", sentence):
        return FactSource.RAG
    if _contains_any(lowered, DATABASE_FACT_MARKERS) or _has_business_number(sentence):
        return FactSource.DATABASE
    return FactSource.GENERATED_PROSE


def _is_critical(sentence: str) -> bool:
    lowered = sentence.lower()
    if _is_non_factual_caveat(lowered):
        return False
    return _contains_any(lowered, CRITICAL_BUSINESS_MARKERS) or _has_business_number(sentence)


def _is_non_factual_caveat(text: str) -> bool:
    return any(
        phrase in text
        for phrase in (
            "availability and prices are subject to change",
            "price and availability are subject to change",
            "prices and availability are subject to change",
        )
    )


def _supported_by_evidence(sentence: str, evidence: str) -> tuple[bool, str, str]:
    if not evidence.strip():
        return False, "No evidence was available for this factual claim.", ""

    evidence_norm = _normalize(evidence)
    sentence_norm = _normalize(sentence)
    status_value = _status_value(sentence)
    if status_value and status_value not in evidence_norm:
        return False, f"Status value was not found in evidence: {status_value}.", ""

    comparison_valid = _price_comparison_valid(sentence, evidence)
    if comparison_valid is False:
        return False, "The price comparison contradicts the database-enforced price limit.", ""

    stock_valid = _stock_availability_valid(sentence, evidence)
    if stock_valid is False:
        return False, "The stock availability claim contradicts database inventory.", ""

    if _is_negative_product_result(sentence) and "no products found" in evidence_norm:
        return True, "The negative product result is present in database evidence.", _snippet(evidence, {"product"})

    claim_terms = _claim_terms(sentence)
    if sentence_norm and sentence_norm in evidence_norm:
        return True, "The claim sentence appears in evidence.", _snippet(evidence, claim_terms)

    missing_numbers = [number for number in _business_numbers(sentence) if number not in _business_numbers(evidence)]
    if missing_numbers:
        return False, f"Business number(s) not found in evidence: {', '.join(missing_numbers)}.", ""

    anchor_terms = _anchor_terms(sentence)
    if anchor_terms and all(term in evidence_norm for term in anchor_terms):
        return True, "All critical anchor terms were found in evidence.", _snippet(evidence, anchor_terms)

    if claim_terms:
        overlap = len(claim_terms & _claim_terms(evidence)) / len(claim_terms)
        if _business_numbers(sentence) and overlap >= 0.25:
            return True, "Business numbers and a factual anchor were found in evidence.", _snippet(evidence, claim_terms)
        if overlap >= 0.55:
            return True, "Claim has sufficient lexical support in evidence.", _snippet(evidence, claim_terms)

    return False, "Claim does not have enough matching evidence.", ""


def _split_sentences(text: str) -> list[str]:
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(("-", "*", "|")):
            lines.append(line.strip("-*| "))
            continue
        lines.extend(part.strip() for part in re.split(r"(?<=[.!?])\s+", line) if part.strip())
    return [line for line in lines if _looks_like_claim(line)]


def _looks_like_claim(sentence: str) -> bool:
    if re.fullmatch(r"\d+[.)]?", sentence.strip()):
        return False
    if sentence.strip().endswith("?"):
        return False
    lowered = sentence.lower()
    if lowered.startswith((
        "could you",
        "can you",
        "i can help",
        "i'd be happy to help",
        "i would be happy to help",
        "please share",
        "mohon",
        "saya bisa membantu",
        "saya dengan senang hati membantu",
        "silakan",
    )):
        return False
    if _contains_any(lowered, CRITICAL_BUSINESS_MARKERS):
        return True
    return bool(_business_numbers(sentence))


def _contains_any(text: str, markers: set[str]) -> bool:
    return any(marker in text for marker in markers)


def _has_business_number(text: str) -> bool:
    return bool(_business_numbers(text))


def _business_numbers(text: str) -> list[str]:
    numbers = []
    for match in re.finditer(r"Rp\s*[\d.,]+|\b\d+(?:[.,]\d+)*\b", text, flags=re.IGNORECASE):
        raw = match.group(0)
        compact = re.sub(r"\D", "", raw)
        if compact:
            numbers.append(compact)
    return numbers


def _status_value(text: str) -> str:
    match = re.search(
        r"\bstatus\s+(?:is|:)?\s*['\"]?(awaiting payment|processing|shipped|completed|cancelled|canceled)\b",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    return _normalize(match.group(1))


def _is_negative_product_result(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in (
            "couldn't find any",
            "could not find any",
            "didn't find any",
            "did not find any",
            "no matching product",
            "no products",
            "no product",
            "tidak ada produk",
            "tidak menemukan produk",
        )
    )


def _price_comparison_valid(sentence: str, evidence: str) -> bool | None:
    lowered = sentence.lower()
    above_markers = ("above your budget", "over your budget", "exceeds your budget", "above the price limit")
    within_markers = ("within your budget", "under your budget", "below your budget", "fits your budget")
    if not any(marker in lowered for marker in above_markers + within_markers):
        return None

    limit_match = re.search(
        r"max[_ ]price['\"]?\s*[:=]\s*(?:rp\s*)?([\d.,]+)",
        evidence,
        flags=re.IGNORECASE,
    )
    if not limit_match:
        return None
    limit = _numeric_value(limit_match.group(1))

    price_match = re.search(r"rp\s*([\d.,]+)", sentence, flags=re.IGNORECASE)
    price = _numeric_value(price_match.group(1)) if price_match else _product_price_from_evidence(sentence, evidence)
    if limit is None or price is None:
        return None

    if any(marker in lowered for marker in above_markers):
        return price > limit
    return price <= limit


def _product_price_from_evidence(sentence: str, evidence: str) -> float | None:
    sentence_norm = _normalize(sentence)
    for line in evidence.splitlines():
        match = re.search(r"^-\s*(.+?)\s*\|.*?Price:\s*Rp\s*([\d.,]+)", line, flags=re.IGNORECASE)
        if not match:
            continue
        product_name = _normalize(match.group(1))
        if product_name and product_name in sentence_norm:
            return _numeric_value(match.group(2))
    return None


def _stock_availability_valid(sentence: str, evidence: str) -> bool | None:
    lowered = sentence.lower()
    says_out = "out of stock" in lowered or "stok habis" in lowered
    says_in = "in stock" in lowered or "tersedia" in lowered
    if not says_out and not says_in:
        return None

    stock = _product_stock_from_evidence(sentence, evidence)
    if stock is None:
        return None
    return stock <= 0 if says_out else stock > 0


def _product_stock_from_evidence(sentence: str, evidence: str) -> float | None:
    sentence_norm = _normalize(sentence)
    sentence_numbers = set(_business_numbers(sentence))
    for line in evidence.splitlines():
        match = re.search(r"^-\s*(.+?)\s*\|.*?Stock:\s*([\d.,]+)\s*units?", line, flags=re.IGNORECASE)
        if not match:
            continue
        product_name = _normalize(match.group(1))
        stock = _numeric_value(match.group(2))
        stock_number = re.sub(r"\D", "", match.group(2))
        if product_name in sentence_norm or (stock_number and stock_number in sentence_numbers):
            return stock
    return None


def _numeric_value(raw: str) -> float | None:
    compact = re.sub(r"[^\d.,]", "", raw)
    if not compact:
        return None
    if "," in compact and "." in compact:
        compact = compact.replace(",", "")
    elif compact.count(",") > 1 or ("," in compact and len(compact.rsplit(",", 1)[1]) == 3):
        compact = compact.replace(",", "")
    try:
        return float(compact)
    except ValueError:
        return None


def _anchor_terms(sentence: str) -> set[str]:
    terms = _claim_terms(sentence)
    markers = {term.replace(" ", "") for term in CRITICAL_BUSINESS_MARKERS}
    return {term for term in terms if term in markers or len(term) >= 4}


def _claim_terms(text: str) -> set[str]:
    stopwords = {
        "about",
        "also",
        "adalah",
        "and",
        "anda",
        "are",
        "at",
        "atau",
        "based",
        "being",
        "bisa",
        "can",
        "could",
        "dari",
        "dengan",
        "found",
        "for",
        "fit",
        "fits",
        "following",
        "from",
        "have",
        "has",
        "kami",
        "here",
        "meet",
        "meets",
        "request",
        "requirement",
        "requirements",
        "option",
        "options",
        "some",
        "that",
        "they",
        "the",
        "these",
        "this",
        "under",
        "untuk",
        "with",
        "we",
        "would",
        "yang",
        "you",
        "your",
    }
    aliases = {
        "asal": "origin",
        "availability": "stock",
        "available": "stock",
        "budget": "price",
        "ditemukan": "found",
        "harga": "price",
        "kategori": "category",
        "cost": "price",
        "costs": "price",
        "priced": "price",
        "prices": "price",
        "produk": "product",
        "stok": "stock",
    }
    terms = set()
    for token in re.findall(r"[a-zA-Z][a-zA-Z0-9]+", _normalize(text)):
        if len(token) <= 2 or token in stopwords:
            continue
        canonical = aliases.get(token, token)
        if canonical.endswith("s") and len(canonical) > 4 and not canonical.endswith("ss"):
            canonical = canonical[:-1]
        terms.add(canonical)
    return terms


def _normalize(text: Any) -> str:
    return " ".join(str(text).lower().replace("_", " ").split())


def _snippet(evidence: str, terms: set[str]) -> str:
    if not terms:
        return evidence[:240]
    for line in evidence.splitlines():
        normalized = _normalize(line)
        if any(term in normalized for term in terms):
            return line.strip()[:240]
    return evidence[:240]
