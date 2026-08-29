from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.services.knowledge_service import KnowledgeService  # noqa: E402
from core.workflows import RetrievalScope, build_rag_context, rerank_rag_chunks  # noqa: E402


class StaticEmbeddingProvider:
    def __init__(self):
        self.inputs = []

    def embed_text(self, text):
        self.inputs.append(text)
        return [0.1] * 768


class RecordingVectorRepository:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def search_chunks(self, **kwargs):
        self.calls.append(kwargs)
        return self.rows


def _chunk(title, document_id, trust_level, similarity, access_level="public"):
    return {
        "id": f"{document_id}-chunk",
        "document_id": f"{document_id}-uuid",
        "title": title,
        "source": f"knowledge_base/{document_id}.md",
        "chunk_index": 0,
        "content": f"{title} evidence text.",
        "embedding_model": "nomic-embed-text",
        "tenant_id": "default",
        "similarity": similarity,
        "document_metadata": {
            "document_id": document_id,
            "title": title,
            "version": "v1",
            "effective_date": "2026-08-29",
            "expires_at": None,
            "status": "active",
            "superseded_by": None,
            "source": f"knowledge_base/{document_id}.md",
            "category": document_id,
            "tenant_id": "default",
            "access_level": access_level,
            "trust_level": trust_level,
        },
        "chunk_metadata": {"document_id": document_id, "access_level": access_level},
    }


def test_reranker_prefers_more_trusted_evidence_when_similarity_is_close():
    chunks = [
        _chunk("External Note", "external_note", "EXTERNAL", 0.84),
        _chunk("Official Policy", "official_policy", "OFFICIAL", 0.8),
    ]

    reranked = rerank_rag_chunks(chunks, limit=2)

    assert reranked[0]["document_metadata"]["trust_level"] == "OFFICIAL"


def test_build_rag_context_abstains_when_evidence_is_weak():
    result = build_rag_context([_chunk("Weak Evidence", "weak", "OFFICIAL", 0.2)])

    assert result.abstained is True
    assert result.citations == []


def test_knowledge_service_uses_authorized_retrieval_and_citations():
    repository = RecordingVectorRepository([
        _chunk("Shipping Policy", "shipping_policy", "OFFICIAL", 0.78)
    ])
    embedding_provider = StaticEmbeddingProvider()
    service = KnowledgeService(
        embedding_provider=embedding_provider,
        vector_repository=repository,
    )

    response = service._search_postgres_rag(
        "international shipping",
        RetrievalScope(tenant_id="default", role="customer", department="public", access_level="public"),
    )

    assert "Citations:" in response
    assert "[C1] Shipping Policy" in response
    assert repository.calls[0]["tenant_id"] == "default"
    assert repository.calls[0]["role"] == "customer"
    assert repository.calls[0]["department"] == "public"
    assert repository.calls[0]["access_level"] == "public"
    assert repository.calls[0]["status"] == "active"


if __name__ == "__main__":
    test_reranker_prefers_more_trusted_evidence_when_similarity_is_close()
    test_build_rag_context_abstains_when_evidence_is_weak()
    test_knowledge_service_uses_authorized_retrieval_and_citations()
    print("RAG retrieval tests passed.")
