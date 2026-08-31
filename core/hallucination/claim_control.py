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
    if _contains_any(lowered, SUPPORT_FACT_MARKERS):
        return FactSource.DATABASE
    if _contains_any(lowered, RAG_FACT_MARKERS) or re.search(r"\bC\d+\b", sentence):
        return FactSource.RAG
    if _contains_any(lowered, DATABASE_FACT_MARKERS) or _has_business_number(sentence):
        return FactSource.DATABASE
    return FactSource.GENERATED_PROSE


def _is_critical(sentence: str) -> bool:
    lowered = sentence.lower()
    return _contains_any(lowered, CRITICAL_BUSINESS_MARKERS) or _has_business_number(sentence)


def _supported_by_evidence(sentence: str, evidence: str) -> tuple[bool, str, str]:
    if not evidence.strip():
        return False, "No evidence was available for this factual claim.", ""

    evidence_norm = _normalize(evidence)
    sentence_norm = _normalize(sentence)
    status_value = _status_value(sentence)
    if status_value and status_value not in evidence_norm:
        return False, f"Status value was not found in evidence: {status_value}.", ""

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
    if sentence.strip().endswith("?"):
        return False
    lowered = sentence.lower()
    if lowered.startswith(("could you", "can you", "please share", "mohon", "silakan")):
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


def _anchor_terms(sentence: str) -> set[str]:
    terms = _claim_terms(sentence)
    markers = {term.replace(" ", "") for term in CRITICAL_BUSINESS_MARKERS}
    return {term for term in terms if term in markers or len(term) >= 4}


def _claim_terms(text: str) -> set[str]:
    stopwords = {
        "about",
        "adalah",
        "anda",
        "atau",
        "bisa",
        "can",
        "could",
        "dari",
        "dengan",
        "for",
        "from",
        "have",
        "kami",
        "that",
        "the",
        "this",
        "untuk",
        "with",
        "would",
        "yang",
        "you",
        "your",
    }
    return {
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9]+", _normalize(text))
        if len(token) > 2 and token not in stopwords
    }


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
