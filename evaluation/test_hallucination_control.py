import sys
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.hallucination import audit_response_claims, hallucination_abstention_message  # noqa: E402
from core.orchestration.runtime import (  # noqa: E402
    _ensure_rag_citations,
    _finalize_workflow_response,
    _grounded_product_response,
    _public_workflow_output,
)


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


def test_paraphrased_product_results_remain_supported():
    evidence = (
        "Found 3 product(s):\n"
        "- Adidas Ultraboost Shoes | Category: Shoes | Price: Rp1,500,000 | "
        "Stock: 35 units | Scores: Vector: 0.661\n"
        "- Nike Air Max Shoes | Category: Shoes | Price: Rp1,200,000 | "
        "Stock: 50 units | Scores: Vector: 0.660\n"
        "- Birkenstock Sandals | Category: Shoes | Price: Rp1,100,000 | "
        "Stock: 20 units | Scores: Vector: 0.604"
    )
    response = (
        "Based on your request, I found 3 products under Rp 1,500,000.\n"
        "1.\n"
        "Adidas Ultraboost Shoes are priced at Rp 1,500,000 and are available in stock.\n"
        "They have a score of 0.661 in vector-based retrieval.\n"
        "2.\n"
        "Nike Air Max Shoes are priced at Rp 1,200,000 and are available in stock."
    )

    audit = audit_response_claims(response, tool_outputs=[evidence])

    assert audit.unsupported_critical_claim_count == 0
    assert audit.should_abstain is False
    assert all(claim.text not in {"1.", "2."} for claim in audit.claims)


def test_product_budget_paraphrase_and_generic_caveat_do_not_abstain():
    evidence = (
        "Applied hard constraints: {'max_price': 1500000.0}\n"
        "- Adidas Ultraboost Shoes | Category: Shoes | Price: Rp1,500,000 | Stock: 35 units"
    )
    response = (
        "Based on your request, I found some shoes that meet your budget of Rp 1,500,000. "
        "Please note that prices and availability are subject to change."
    )

    audit = audit_response_claims(response, tool_outputs=[evidence])

    assert audit.unsupported_critical_claim_count == 0
    assert audit.should_abstain is False

    aggregate_audit = audit_response_claims(
        "We have found some shoe options for you that fit your budget of Rp 1,500,000.",
        tool_outputs=[evidence],
    )
    assert aggregate_audit.should_abstain is False

    count_audit = audit_response_claims(
        "We have found 3 products that match your search criteria.",
        tool_outputs=["Found 3 product(s):"],
    )
    assert count_audit.should_abstain is False


def test_helpful_intro_repeating_user_constraint_is_not_a_business_claim():
    audit = audit_response_claims(
        "I'd be happy to help you find shoes under Rp 1,500,000.",
        tool_outputs=[],
    )

    assert audit.claims == []
    assert audit.should_abstain is False


def test_product_workflow_hides_internal_retrieval_scores_from_llm():
    output = (
        "Found 1 product(s):\n"
        "Hybrid retrieval + reranker: enabled. Retrieved top 20 candidates, reranked to top 5.\n"
        "- Nike Air Max Shoes | Price: Rp1,200,000 | Stock: 50 units | "
        "Scores: Rerank: 0.573, Vector: 0.660"
    )

    public_output = _public_workflow_output("search_products", output)

    assert "Hybrid retrieval" not in public_output
    assert "Rerank:" not in public_output
    assert "Vector:" not in public_output
    assert "Nike Air Max Shoes" in public_output
    assert "Rp1,200,000" in public_output
    assert "Applied hard constraints" not in _public_workflow_output(
        "search_products",
        "Applied hard constraints: {'max_price': 1500000.0}\n- Nike Air Max Shoes | Price: Rp1,200,000",
    )


def test_grounded_product_fallback_localizes_indonesian_labels():
    output = "Found 1 product(s):\n- Nike Air Max Shoes | Category: Shoes | Price: Rp1,200,000 | Stock: 50 units"

    response = _grounded_product_response("Cari sepatu Nike", output)

    assert response.startswith("Ditemukan 1 produk:")
    assert "Kategori: Shoes" in response
    assert "Harga: Rp1,200,000" in response
    assert "Stok: 50 unit" in response


def test_product_finalizer_uses_deterministic_database_response_without_llm():
    from core.orchestration import runtime

    tool_output = (
        "Found 1 product(s):\n"
        "Applied hard constraints: {'max_price': 1500000.0}\n"
        "- Adidas Ultraboost Shoes | Category: Shoes | Price: Rp1,500,000 | Stock: 35 units"
    )
    original_generate = runtime.llm_gateway.generate_sync
    calls = []
    runtime.llm_gateway.generate_sync = lambda *_args, **_kwargs: calls.append(True)
    trace = {}
    try:
        response = _finalize_workflow_response(
            "Find shoes under Rp 1,500,000",
            "search_products",
            tool_output,
            trace=trace,
        )
    finally:
        runtime.llm_gateway.generate_sync = original_generate

    assert response.startswith("Found 1 product(s):")
    assert "Price: Rp1,500,000" in response
    assert "Stock: 35 units" in response
    assert "above your budget" not in response
    assert "out of stock" not in response
    assert trace["deterministic_first"] is True
    assert calls == []


def test_order_finalizer_uses_deterministic_database_response_without_llm():
    from core.orchestration import runtime

    tool_output = (
        "Order Details - ORD001:\n"
        "- Product: Nike Air Max Shoes (x2)\n"
        "- Total: Rp2,400,000\n"
        "- Status: Shipped\n"
        "- Estimated Arrival: 2026-03-25"
    )
    original_generate = runtime.llm_gateway.generate_sync
    calls = []
    runtime.llm_gateway.generate_sync = lambda *_args, **_kwargs: calls.append(True)
    trace = {}
    try:
        response = _finalize_workflow_response(
            "Check order ORD001",
            "check_order_status",
            tool_output,
            trace=trace,
        )
    finally:
        runtime.llm_gateway.generate_sync = original_generate

    assert response == tool_output
    assert "Status: Shipped" in response
    assert "Cancelled" not in response
    assert trace["deterministic_first"] is True
    assert calls == []


def test_rag_response_keeps_source_citations():
    tool_output = (
        "Relevant policy evidence:\n"
        "[C1] Customers may return products within 7 days.\n\n"
        "Citations:\n"
        "- [C1] Return Policy (return_policy, version v1)"
    )

    response = _ensure_rag_citations("Returns are allowed within 7 days.", tool_output)

    assert "Sources:" in response
    assert "[C1] Return Policy" in response
    assert _ensure_rag_citations(response, tool_output) == response


def test_paraphrased_product_result_still_rejects_wrong_price():
    audit = audit_response_claims(
        "Nike Air Max Shoes are priced at Rp 999,000 and are available in stock.",
        tool_outputs=["- Nike Air Max Shoes | Price: Rp1,200,000 | Stock: 50 units"],
    )

    assert audit.unsupported_critical_claim_count == 1
    assert audit.should_abstain is True


def test_false_above_budget_comparison_is_rejected():
    audit = audit_response_claims(
        "Adidas Ultraboost Shoes are priced at Rp 1,500,000, which is above your budget.",
        tool_outputs=[
            "Applied hard constraints: {'max_price': 1500000.0}\n"
            "- Adidas Ultraboost Shoes | Price: Rp1,500,000 | Stock: 35 units"
        ],
    )

    assert audit.unsupported_critical_claim_count == 1
    assert audit.should_abstain is True

    implicit_price_audit = audit_response_claims(
        "Adidas Ultraboost Shoes are just above your budget.",
        tool_outputs=[
            "Applied hard constraints: {'max_price': 1500000.0}\n"
            "- Adidas Ultraboost Shoes | Price: Rp1,500,000 | Stock: 35 units"
        ],
    )
    assert implicit_price_audit.should_abstain is True


def test_false_out_of_stock_claim_is_rejected():
    audit = audit_response_claims(
        "Adidas Ultraboost Shoes are currently out of stock (only 35 units available).",
        tool_outputs=["- Adidas Ultraboost Shoes | Price: Rp1,500,000 | Stock: 35 units"],
    )

    assert audit.unsupported_critical_claim_count == 1
    assert audit.should_abstain is True

    supported = audit_response_claims(
        "Adidas Ultraboost Shoes have 35 units in stock.",
        tool_outputs=["- Adidas Ultraboost Shoes | Price: Rp1,500,000 | Stock: 35 units"],
    )
    assert supported.should_abstain is False


def test_grounded_no_product_result_is_supported():
    audit = audit_response_claims(
        "I couldn't find any black waterproof hiking shoes that meet your size and price requirements.",
        tool_outputs=[
            "No products found matching database-enforced filters: "
            "category='Shoes', max_price=Rp500,000, size=42. "
            "Additional criteria captured but not catalog-filterable: color='black', waterproof=True."
        ],
    )

    assert audit.unsupported_critical_claim_count == 0
    assert audit.should_abstain is False


def test_no_product_renderer_is_user_friendly_and_grounded():
    tool_output = (
        "No products found matching database-enforced filters: "
        "category='Shoes', max_price=Rp500,000, size=42. "
        "Additional criteria captured but not catalog-filterable: color='black', waterproof=True."
    )

    english = _grounded_product_response(
        "Find black waterproof hiking shoes size 42 under Rp 500,000",
        tool_output,
    )
    indonesian = _grounded_product_response(
        "Cari sepatu hiking hitam waterproof ukuran 42 di bawah Rp 500.000",
        tool_output,
    )

    assert "database-enforced" not in english
    assert "catalog-filterable" not in english
    assert "maximum price Rp500,000" in english
    assert "size 42" in english
    assert "color 'black'" in english
    assert "waterproof products" in english
    assert "=True" not in english
    assert "harga maksimal Rp500,000" in indonesian
    assert "ukuran 42" in indonesian


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
    test_paraphrased_product_results_remain_supported()
    test_product_budget_paraphrase_and_generic_caveat_do_not_abstain()
    test_helpful_intro_repeating_user_constraint_is_not_a_business_claim()
    test_product_workflow_hides_internal_retrieval_scores_from_llm()
    test_grounded_product_fallback_localizes_indonesian_labels()
    test_product_finalizer_uses_deterministic_database_response_without_llm()
    test_order_finalizer_uses_deterministic_database_response_without_llm()
    test_rag_response_keeps_source_citations()
    test_paraphrased_product_result_still_rejects_wrong_price()
    test_false_above_budget_comparison_is_rejected()
    test_false_out_of_stock_claim_is_rejected()
    test_grounded_no_product_result_is_supported()
    test_no_product_renderer_is_user_friendly_and_grounded()
    test_rag_facts_must_have_evidence()
    test_generated_prose_is_not_treated_as_business_fact()
    test_support_ticket_output_is_supported_by_tool_output()
    test_abstention_message_matches_language()
    print("Hallucination control tests passed.")
