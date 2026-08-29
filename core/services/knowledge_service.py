from dataclasses import dataclass
from pathlib import Path

from configs import get_settings
from core.embeddings import OpenAICompatibleEmbeddingProvider
from core.repositories.postgres_vector_repository import PostgresVectorRepository
from core.workflows import RetrievalScope, build_rag_context, rerank_rag_chunks


DOCUMENT_ORDER = [
    "return_policy",
    "refund_policy",
    "shipping_policy",
    "warranty",
    "payments",
    "faq",
]


@dataclass(frozen=True)
class KnowledgeDocument:
    document_id: str
    title: str
    path: Path | None
    content: str


class KnowledgeService:
    """Business logic for policy and FAQ knowledge-base search."""

    def __init__(
        self,
        knowledge_base_path: Path | None = None,
        knowledge_base_dir: Path | None = None,
        embedding_provider: OpenAICompatibleEmbeddingProvider | None = None,
        vector_repository: PostgresVectorRepository | None = None,
    ):
        settings = get_settings()
        self.settings = settings
        self.knowledge_base_path = knowledge_base_path or settings.knowledge_base_path
        self.knowledge_base_dir = knowledge_base_dir or settings.knowledge_base_dir
        self.embedding_provider = embedding_provider
        self.vector_repository = vector_repository
        self.documents = self._load_documents()

    def search_knowledge_base(self, query: str) -> str:
        if self.settings.database_provider == "postgres":
            rag_response = self._search_postgres_rag(query)
            if rag_response:
                return rag_response

        return self._search_file_knowledge_base(query)

    def _search_postgres_rag(self, query: str, scope: RetrievalScope | None = None) -> str:
        scope = scope or RetrievalScope()
        try:
            embedding_provider = self.embedding_provider or OpenAICompatibleEmbeddingProvider()
            vector_repository = self.vector_repository or PostgresVectorRepository()
            query_embedding = embedding_provider.embed_text(query)
            retrieved_chunks = vector_repository.search_chunks(
                query_embedding=query_embedding,
                limit=12,
                embedding_model=self.settings.embedding_model,
                tenant_id=scope.tenant_id,
                role=scope.role,
                department=scope.department,
                access_level=scope.access_level,
                status="active",
                approval_status="indexed",
                min_trust_level="EXTERNAL",
            )
            reranked_chunks = rerank_rag_chunks(retrieved_chunks, limit=5)
            context = build_rag_context(reranked_chunks, query=query)
        except (RuntimeError, ValueError, OSError):
            return ""

        if context.abstained:
            return (
                "I don't have enough authorized, fresh evidence to answer that from the knowledge base.\n"
                f"Retrieval behavior: abstain. Reason: {context.reason}"
            )

        results = [f"Relevant authorized policy evidence for '{query}':", context.answer_context, "", "Citations:"]
        for citation in context.citations:
            results.append(
                f"- [{citation['citation_id']}] {citation['title']} "
                f"({citation['document_id']}, version {citation['version']}, "
                f"effective {citation['effective_date']}, source {citation['source']})"
            )
        return "\n".join(results)

    def _search_file_knowledge_base(self, query: str) -> str:
        if not self.documents:
            return "Knowledge base is not available at this time."

        query_terms = self._query_terms(query)
        matches = []
        for document in self.documents:
            matched_lines = self._matched_lines(document.content, query_terms)
            title_match = any(term in document.title.lower() for term in query_terms)
            if matched_lines or title_match:
                score = len(matched_lines) + (2 if title_match else 0)
                matches.append((score, document, matched_lines))

        if not matches:
            document_list = ", ".join(document.document_id for document in self.documents)
            return (
                f"No exact keyword match found for '{query}'. "
                f"Available knowledge documents: {document_list}."
            )

        matches.sort(key=lambda item: item[0], reverse=True)
        results = [f"Relevant store policy information for '{query}':"]
        for _, document, matched_lines in matches[:3]:
            results.append("")
            results.append(f"[{document.document_id}] {document.title}")
            lines = matched_lines or self._content_lines(document.content)[:4]
            results.extend(lines[:6])
        return "\n".join(results)

    def _load_documents(self) -> list[KnowledgeDocument]:
        if self.knowledge_base_dir.exists() and self.knowledge_base_dir.is_dir():
            documents = []
            for document_id in DOCUMENT_ORDER:
                path = self.knowledge_base_dir / f"{document_id}.md"
                if not path.exists():
                    continue
                raw_content = path.read_text(encoding="utf-8").strip()
                metadata, content = self._extract_front_matter(raw_content)
                documents.append(
                    KnowledgeDocument(
                        document_id=metadata.get("document_id", document_id),
                        title=metadata.get("title") or self._title_from_content(content, document_id),
                        path=path,
                        content=content,
                    )
                )
            if documents:
                return documents

        if self.knowledge_base_path.exists():
            content = self.knowledge_base_path.read_text(encoding="utf-8").strip()
            return [
                KnowledgeDocument(
                    document_id="legacy_knowledge_base",
                    title="Store Knowledge Base",
                    path=self.knowledge_base_path,
                    content=content,
                )
            ]

        return []

    def _matched_lines(self, content: str, query_terms: set[str]) -> list[str]:
        if not query_terms:
            return []

        matched = []
        for line in self._content_lines(content):
            line_lower = line.lower()
            if any(term in line_lower for term in query_terms):
                matched.append(line)
        return matched

    @staticmethod
    def _content_lines(content: str) -> list[str]:
        return [
            line.strip()
            for line in content.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    @staticmethod
    def _query_terms(query: str) -> set[str]:
        stopwords = {
            "a",
            "about",
            "after",
            "an",
            "and",
            "apa",
            "apakah",
            "bagaimana",
            "can",
            "business",
            "days",
            "do",
            "does",
            "for",
            "how",
            "i",
            "is",
            "it",
            "kalian",
            "long",
            "my",
            "of",
            "take",
            "takes",
            "the",
            "to",
            "what",
            "you",
            "your",
        }
        tokens = {
            token
            for token in query.lower().replace("?", " ").replace(",", " ").split()
            if len(token) > 2 and token not in stopwords
        }
        aliases = set(tokens)
        if "return" in tokens:
            aliases.add("return")
        if "refund" in tokens:
            aliases.add("refund")
        if "shipping" in tokens or "delivery" in tokens:
            aliases.update({"shipping", "shipment"})
        if "payment" in tokens or "payments" in tokens or "pay" in tokens:
            aliases.update({"payment", "payments"})
        if "warranty" in tokens or "defective" in tokens:
            aliases.update({"warranty", "defect"})
        if "operational" in tokens or "operating" in tokens or "hours" in tokens or "jam" in tokens:
            aliases.update({"hours", "operating"})
        return aliases

    @staticmethod
    def _title_from_content(content: str, fallback: str) -> str:
        for line in content.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return fallback.replace("_", " ").title()

    @staticmethod
    def _extract_front_matter(content: str) -> tuple[dict[str, str], str]:
        lines = content.splitlines()
        if not lines or lines[0].strip() != "---":
            return {}, content

        metadata = {}
        closing_index = None
        for index, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                closing_index = index
                break
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip().strip('"').strip("'")

        if closing_index is None:
            return {}, content
        return metadata, "\n".join(lines[closing_index + 1 :])


knowledge_service = KnowledgeService()
