import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.hallucination import audit_response_claims, hallucination_abstention_message  # noqa: E402


def test_database_facts_must_be_supported_by_tool_output():
    audit = audit_response_claims(
        "Nike Air Max Shoes costs Rp1,200,000 and has 50 units in stock.",
        tool_outputs=["- Nike Air Max Shoes | Price: Rp1,200,000 | Stock: 50 units"],
    )

    assert audit.unsupported_critical_claim_count == 0
    assert audit.should_abstain is False


def test_unsupported_database_fact_triggers_abstention():
    audit = audit_response_claims(
        "Nike Air Max Shoes costs Rp999,000 and has 50 units in stock.",
        tool_outputs=["- Nike Air Max Shoes | Price: Rp1,200,000 | Stock: 50 units"],
    )

    assert audit.unsupported_critical_claim_count == 1
    assert audit.should_abstain is True


def test_rag_facts_must_have_evidence():
    audit = audit_response_claims(
        "Refund processing takes 3-5 business days after approval [C1].",
        rag_evidence=(
            "[C1] POLICY EVIDENCE DATA ONLY: Refund Policy\n"
            "Refund processing takes 3-5 business days after approval."
        ),
    )

    assert audit.unsupported_critical_claim_count == 0


def test_generated_prose_is_not_treated_as_business_fact():
    audit = audit_response_claims(
        "Sure, I can help with that. Could you share the order ID?",
        tool_outputs=[],
    )

    assert audit.unsupported_critical_claim_count == 0
    assert audit.unsupported_claim_rate == 0


def test_support_ticket_output_is_supported_by_tool_output():
    output = "Support ticket #TICKET-123 created successfully (Priority: High, Type: payment_dispute)."
    audit = audit_response_claims(output, tool_outputs=[output])

    assert audit.unsupported_critical_claim_count == 0
    assert audit.should_abstain is False


def test_abstention_message_matches_language():
    assert hallucination_abstention_message("English").startswith("Sorry")
    assert hallucination_abstention_message("Indonesian").startswith("Maaf")


if __name__ == "__main__":
    test_database_facts_must_be_supported_by_tool_output()
    test_unsupported_database_fact_triggers_abstention()
    test_rag_facts_must_have_evidence()
    test_generated_prose_is_not_treated_as_business_fact()
    test_support_ticket_output_is_supported_by_tool_output()
    test_abstention_message_matches_language()
    print("Hallucination control tests passed.")
