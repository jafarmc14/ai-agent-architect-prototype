from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.services.knowledge_service import DOCUMENT_ORDER, KnowledgeService  # noqa: E402


def test_knowledge_base_is_split_into_expected_documents():
    service = KnowledgeService(knowledge_base_dir=PROJECT_ROOT / "knowledge_base")

    assert [document.document_id for document in service.documents] == DOCUMENT_ORDER


def test_search_knowledge_base_returns_document_ids():
    service = KnowledgeService(knowledge_base_dir=PROJECT_ROOT / "knowledge_base")

    response = service.search_knowledge_base("How long does international shipping take?")

    assert "shipping_policy" in response
    assert "Shipping Policy" in response
    assert "International shipping takes 10-14 business days" in response


def test_search_knowledge_base_preserves_refund_lookup():
    service = KnowledgeService(knowledge_base_dir=PROJECT_ROOT / "knowledge_base")

    response = service.search_knowledge_base("How long does a refund take?")

    assert "refund_policy" in response
    assert "Refund Policy" in response
    assert "3-5 business days" in response


if __name__ == "__main__":
    test_knowledge_base_is_split_into_expected_documents()
    test_search_knowledge_base_returns_document_ids()
    test_search_knowledge_base_preserves_refund_lookup()
    print("Knowledge document tests passed.")
