import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from configs import get_settings  # noqa: E402
from core.workflows import DocumentIngestionPipeline  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest knowledge base documents into PostgreSQL pgvector.")
    parser.add_argument("--source-dir", default=None, help="Directory containing Markdown knowledge documents.")
    parser.add_argument("--dry-run", action="store_true", help="Parse, clean, and chunk without embedding or storing.")
    parser.add_argument("--chunk-size", type=int, default=140)
    parser.add_argument("--chunk-overlap", type=int, default=25)
    args = parser.parse_args()

    settings = get_settings()
    if settings.database_provider != "postgres":
        print("Document ingestion requires DATABASE_PROVIDER=postgres.", file=sys.stderr)
        return 1

    source_dir = Path(args.source_dir) if args.source_dir else settings.knowledge_base_dir
    if not source_dir.is_absolute():
        source_dir = PROJECT_ROOT / source_dir
    if not source_dir.exists() or not source_dir.is_dir():
        print(f"Knowledge source directory not found: {source_dir}", file=sys.stderr)
        return 1

    pipeline = DocumentIngestionPipeline(
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )
    try:
        result = pipeline.ingest(source_dir=source_dir, dry_run=args.dry_run)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print("Knowledge ingestion complete." if not args.dry_run else "Knowledge ingestion dry run complete.")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
