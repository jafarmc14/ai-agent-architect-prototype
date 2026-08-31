from dataclasses import dataclass
import re


PRIORITY_ORDER = {"Low": 1, "Normal": 2, "High": 3, "Urgent": 4}


@dataclass(frozen=True)
class EscalationDecision:
    should_escalate: bool
    priority: str = "Normal"
    escalation_type: str = ""
    reason: str = ""
    summarized_context: str = ""
    confidence: float = 1.0
    matched_rules: tuple[str, ...] = ()


RULES = (
    ("fraud", "Urgent", "fraud", (r"\bfraud\b", r"\bscam\b", r"\bunauthorized charge\b", r"\bpenipuan\b")),
    ("legal_complaint", "Urgent", "legal_complaint", (r"\blegal\b", r"\blawsuit\b", r"\bsue\b", r"\bpengacara\b", r"\bhukum\b")),
    ("payment_dispute", "High", "payment_dispute", (r"\bpayment dispute\b", r"\bcharged twice\b", r"\bduplicate payment\b", r"\bdouble charge\b", r"\bpembayaran ganda\b")),
    ("high_value_refund", "High", "high_value_refund", (r"\brefund\b.*\bRp\s*[\d.,]+", r"\brefund\b.*\b\d{7,}\b", r"\bpengembalian dana\b.*\b\d{7,}\b")),
    ("repeated_failure", "High", "repeated_failure", (r"\bthird time\b", r"\brepeated failure\b", r"\bagain and again\b", r"\bberulang\b", r"\bberkali-kali\b")),
    ("low_confidence", "Normal", "low_confidence", (r"\bnot sure\b", r"\bunclear\b", r"\bconfusing\b", r"\bkurang jelas\b")),
    ("human_requested", "Normal", "human_requested", (r"\bhuman agent\b", r"\breal person\b", r"\bspeak to human\b", r"\btalk to human\b", r"\bmanusia\b", r"\bcs\b")),
)


def evaluate_escalation(user_input: str, *, confidence: float = 1.0) -> EscalationDecision:
    text = user_input.strip()
    matched = []
    priority = "Normal"
    escalation_type = ""
    for rule_name, rule_priority, rule_type, patterns in RULES:
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns):
            matched.append(rule_name)
            if PRIORITY_ORDER[rule_priority] > PRIORITY_ORDER[priority]:
                priority = rule_priority
                escalation_type = rule_type

    if confidence < 0.45:
        matched.append("low_confidence")
        if PRIORITY_ORDER["Normal"] > PRIORITY_ORDER[priority]:
            priority = "Normal"
            escalation_type = "low_confidence"

    if not matched:
        return EscalationDecision(should_escalate=False, confidence=confidence)

    return EscalationDecision(
        should_escalate=True,
        priority=priority,
        escalation_type=escalation_type or matched[0],
        reason=", ".join(matched),
        summarized_context=summarize_escalation_context(text, matched),
        confidence=confidence,
        matched_rules=tuple(matched),
    )


def summarize_escalation_context(user_input: str, matched_rules: list[str] | tuple[str, ...] = ()) -> str:
    text = " ".join(user_input.split())
    clipped = text[:500]
    rule_text = ", ".join(matched_rules) if matched_rules else "manual_escalation"
    return f"Customer message summary: {clipped}. Triggered rules: {rule_text}."
