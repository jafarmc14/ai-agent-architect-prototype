import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.embeddings import OpenAICompatibleEmbeddingProvider
from core.repositories.postgres_vector_repository import PostgresVectorRepository


REQUIRED_DOCUMENT_METADATA = [
    "document_id",
    "title",
    "version",
    "effective_date",
    "expires_at",
    "status",
    "superseded_by",
    "source",
    "category",
    "tenant_id",
    "access_level",
    "trust_level",
    "approval_status",
]

ALLOWED_DOCUMENT_EXTENSIONS = {".md", ".txt"}
APPROVAL_STATUSES = {"uploaded", "reviewed", "approved", "indexed"}
INDEXABLE_APPROVAL_STATUSES = {"approved", "indexed"}
MAX_DOCUMENT_BYTES = 1_000_000
SUSPICIOUS_CONTENT_PATTERNS = [
    (re.compile(r"ignore\s+all\s+rules", re.IGNORECASE), "prompt_injection_ignore_all_rules"),
    (re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE), "prompt_injection_ignore_previous"),
    (re.compile(r"disregard\s+(all\s+)?(system|developer|previous)\s+instructions", re.IGNORECASE), "prompt_injection_disregard_instructions"),
    (re.compile(r"reveal\s+(the\s+)?(system\s+prompt|developer\s+message|secrets?)", re.IGNORECASE), "secret_exfiltration_instruction"),
    (re.compile(r"(api[_-]?key|password|jwt[_-]?secret)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{12,}", re.IGNORECASE), "possible_secret"),
    (re.compile(r"<\s*script\b", re.IGNORECASE), "script_tag"),
    (re.compile(r"javascript\s*:", re.IGNORECASE), "javascript_uri"),
    (re.compile(r"\b(eval|exec|subprocess|powershell|cmd\.exe)\s*\(", re.IGNORECASE), "executable_code"),
]


@dataclass(frozen=True)
class ParsedDocument:
    document_id: str
    title: str
    source: str
    source_type: str
    content: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class DocumentChunk:
    document_id: str
    chunk_index: int
    content: str
    token_count: int
    metadata: dict[str, Any]


@dataclass(frozen=True)
class DocumentValidation:
    valid: bool
    findings: list[str]


class DocumentIngestionPipeline:
    """Parse, clean, chunk, embed, and store knowledge documents."""

    def __init__(
        self,
        embedding_provider: OpenAICompatibleEmbeddingProvider | None = None,
        vector_repository: PostgresVectorRepository | None = None,
        chunk_size: int = 140,
        chunk_overlap: int = 25,
    ):
        if chunk_size <= 0:
            raise ValueError("chunk_size must be greater than 0.")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be at least 0 and smaller than chunk_size.")

        self.embedding_provider = embedding_provider or OpenAICompatibleEmbeddingProvider()
        self.vector_repository = vector_repository or PostgresVectorRepository()
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def parse(self, source_dir: Path) -> list[ParsedDocument]:
        documents = []
        for path in sorted(item for item in source_dir.iterdir() if item.is_file()):
            validation = self.validate_file(path)
            if not validation.valid:
                documents.append(
                    ParsedDocument(
                        document_id=path.stem,
                        title=path.stem.replace("_", " ").title(),
                        source=str(path.as_posix()),
                        source_type=path.suffix.lower().lstrip(".") or "unknown",
                        content="",
                        metadata=self._document_metadata(
                            document_id=path.stem,
                            title=path.stem.replace("_", " ").title(),
                            source=str(path.as_posix()),
                            path=path,
                            front_matter={},
                            validation=validation,
                        ),
                    )
                )
                continue

            raw_content = path.read_text(encoding="utf-8")
            front_matter, body = self._extract_front_matter(raw_content)
            title = front_matter.get("title") or self._extract_title(body, path.stem)
            document_id = front_matter.get("document_id") or path.stem
            source = front_matter.get("source") or str(path.as_posix())
            scan = self.scan_content(raw_content)
            combined_findings = [*validation.findings, *scan.findings]
            metadata = self._document_metadata(
                document_id=document_id,
                title=title,
                source=source,
                path=path,
                front_matter=front_matter,
                validation=DocumentValidation(valid=validation.valid and scan.valid, findings=combined_findings),
            )
            documents.append(
                ParsedDocument(
                    document_id=document_id,
                    title=title,
                    source=source,
                    source_type=front_matter.get("source_type", "markdown"),
                    content=body,
                    metadata=metadata,
                )
            )
        return documents

    def validate_file(self, path: Path) -> DocumentValidation:
        findings = []
        if path.suffix.lower() not in ALLOWED_DOCUMENT_EXTENSIONS:
            findings.append(f"unsupported_file_type:{path.suffix.lower() or 'none'}")
        try:
            size = path.stat().st_size
        except OSError:
            findings.append("file_stat_failed")
            size = 0
        if size > MAX_DOCUMENT_BYTES:
            findings.append(f"file_too_large:{size}")
        return DocumentValidation(valid=not findings, findings=findings)

    def scan_content(self, content: str) -> DocumentValidation:
        findings = []
        for pattern, finding in SUSPICIOUS_CONTENT_PATTERNS:
            if pattern.search(content):
                findings.append(finding)
        return DocumentValidation(valid=not findings, findings=findings)

    def clean(self, document: ParsedDocument) -> ParsedDocument:
        metadata = self._validate_metadata(document.metadata)
        if not metadata.get("security_valid", False):
            return ParsedDocument(
                document_id=document.document_id,
                title=document.title,
                source=document.source,
                source_type=document.source_type,
                content="",
                metadata=metadata,
            )

        lines = []
        for line in document.content.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                continue
            stripped = re.sub(r"\s+", " ", stripped)
            lines.append(stripped)
        return ParsedDocument(
            document_id=document.document_id,
            title=document.title,
            source=document.source,
            source_type=document.source_type,
            content="\n".join(lines),
            metadata=metadata,
        )

    def chunk(self, document: ParsedDocument) -> list[DocumentChunk]:
        tokens = document.content.split()
        if not tokens:
            return []

        chunks = []
        start = 0
        chunk_index = 0
        step = self.chunk_size - self.chunk_overlap
        while start < len(tokens):
            chunk_tokens = tokens[start : start + self.chunk_size]
            content = " ".join(chunk_tokens)
            chunks.append(
                DocumentChunk(
                    document_id=document.document_id,
                    chunk_index=chunk_index,
                    content=content,
                    token_count=len(chunk_tokens),
                    metadata={
                        **document.metadata,
                        "chunk_size": self.chunk_size,
                        "chunk_overlap": self.chunk_overlap,
                        "chunk_index": chunk_index,
                    },
                )
            )
            if start + self.chunk_size >= len(tokens):
                break
            start += step
            chunk_index += 1
        return chunks

    def embed(self, chunk: DocumentChunk) -> list[float]:
        return self.embedding_provider.embed_text(chunk.content)

    def store(
        self,
        document: ParsedDocument,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]],
        replace_existing_chunks: bool = True,
    ) -> dict[str, Any]:
        metadata = {
            **document.metadata,
            "approval_status": "indexed",
        }
        document_uuid = self.vector_repository.upsert_document(
            title=document.title,
            source=document.source,
            source_type=document.source_type,
            version=document.metadata.get("version"),
            language="en",
            metadata=metadata,
            tenant_id=document.metadata.get("tenant_id", "default"),
            effective_date=document.metadata.get("effective_date"),
            expires_at=document.metadata.get("expires_at"),
            status=document.metadata.get("status", "active"),
            superseded_by=document.metadata.get("superseded_by"),
            approval_status="indexed",
        )

        deleted_chunks = 0
        if replace_existing_chunks:
            deleted_chunks = self.vector_repository.delete_document_chunks(document_uuid)

        chunk_ids = []
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            chunk_ids.append(
                self.vector_repository.upsert_chunk(
                    document_id=document_uuid,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    embedding=embedding,
                    token_count=chunk.token_count,
                    metadata={**chunk.metadata, "approval_status": "indexed"},
                    tenant_id=chunk.metadata.get("tenant_id", "default"),
                )
            )

        return {
            "document_id": document.document_id,
            "document_uuid": document_uuid,
            "chunks_stored": len(chunk_ids),
            "chunks_deleted": deleted_chunks,
        }

    def ingest(self, source_dir: Path, dry_run: bool = False) -> dict[str, Any]:
        parsed_documents = self.parse(source_dir)
        results = []
        for parsed_document in parsed_documents:
            cleaned_document = self.clean(parsed_document)
            chunks = self.chunk(cleaned_document)
            can_index = self._can_index(cleaned_document.metadata)
            if dry_run:
                results.append(
                    {
                        "document_id": cleaned_document.document_id,
                        "title": cleaned_document.title,
                        "source": cleaned_document.source,
                        "metadata": cleaned_document.metadata,
                        "security_valid": cleaned_document.metadata.get("security_valid", False),
                        "security_findings": cleaned_document.metadata.get("security_findings", []),
                        "approval_status": cleaned_document.metadata.get("approval_status"),
                        "indexable": can_index,
                        "chunks": len(chunks),
                        "tokens": sum(chunk.token_count for chunk in chunks),
                    }
                )
                continue

            if not can_index:
                results.append(
                    {
                        "document_id": cleaned_document.document_id,
                        "title": cleaned_document.title,
                        "source": cleaned_document.source,
                        "metadata": cleaned_document.metadata,
                        "skipped": True,
                        "skip_reason": self._skip_reason(cleaned_document.metadata),
                        "chunks_stored": 0,
                        "chunks_deleted": 0,
                    }
                )
                continue

            embeddings = [self.embed(chunk) for chunk in chunks]
            results.append(self.store(cleaned_document, chunks, embeddings))

        return {
            "documents": len(parsed_documents),
            "chunks": sum(result.get("chunks", result.get("chunks_stored", 0)) for result in results),
            "indexed_documents": sum(1 for result in results if result.get("chunks_stored", 0) > 0),
            "skipped_documents": sum(1 for result in results if result.get("skipped")),
            "dry_run": dry_run,
            "results": results,
        }

    @staticmethod
    def _extract_title(content: str, fallback: str) -> str:
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
            metadata[key.strip()] = DocumentIngestionPipeline._metadata_value(value)

        if closing_index is None:
            return {}, content

        return metadata, "\n".join(lines[closing_index + 1 :])

    @staticmethod
    def _document_metadata(
        document_id: str,
        title: str,
        source: str,
        path: Path,
        front_matter: dict[str, str],
        validation: DocumentValidation | None = None,
    ) -> dict[str, Any]:
        validation = validation or DocumentValidation(valid=True, findings=[])
        approval_status = (front_matter.get("approval_status") or "uploaded").lower()
        if approval_status not in APPROVAL_STATUSES:
            validation = DocumentValidation(
                valid=False,
                findings=[*validation.findings, f"invalid_approval_status:{approval_status}"],
            )
            approval_status = "uploaded"
        trust_level = (front_matter.get("trust_level") or "USER_GENERATED").upper()
        return {
            "document_id": document_id,
            "title": title,
            "version": front_matter.get("version", "v1"),
            "effective_date": front_matter.get("effective_date", "2026-08-29"),
            "expires_at": front_matter.get("expires_at"),
            "status": front_matter.get("status", "active"),
            "superseded_by": front_matter.get("superseded_by"),
            "source": source,
            "category": front_matter.get("category", document_id),
            "tenant_id": front_matter.get("tenant_id", "default"),
            "access_level": front_matter.get("access_level", "public"),
            "trust_level": trust_level,
            "approval_status": approval_status,
            "security_valid": validation.valid,
            "security_findings": validation.findings,
            "filename": path.name,
            "pipeline": "document_ingestion_v2_security",
        }

    @staticmethod
    def _validate_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
        missing = [key for key in REQUIRED_DOCUMENT_METADATA if key not in metadata]
        if missing:
            raise ValueError(f"Document metadata is missing required fields: {', '.join(missing)}")
        return metadata

    @staticmethod
    def _can_index(metadata: dict[str, Any]) -> bool:
        return (
            metadata.get("security_valid") is True
            and metadata.get("approval_status") in INDEXABLE_APPROVAL_STATUSES
        )

    @staticmethod
    def _skip_reason(metadata: dict[str, Any]) -> str:
        if not metadata.get("security_valid", False):
            findings = metadata.get("security_findings") or ["unknown_security_finding"]
            return "security_scan_failed:" + ",".join(findings)
        return f"approval_status_not_indexable:{metadata.get('approval_status')}"

    @staticmethod
    def _metadata_value(raw_value: str) -> str | None:
        value = raw_value.strip().strip('"').strip("'")
        if value.lower() in {"", "null", "none"}:
            return None
        return value
