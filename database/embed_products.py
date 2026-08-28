import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from configs import get_settings  # noqa: E402
from core.embeddings import OpenAICompatibleEmbeddingProvider  # noqa: E402
from core.repositories import PostgresProductEmbeddingRepository  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate PostgreSQL pgvector embeddings for products.")
    parser.add_argument("--only-missing", action="store_true", help="Embed only products without embeddings.")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of products processed.")
    parser.add_argument("--dry-run", action="store_true", help="Print product embedding source text without API calls.")
    args = parser.parse_args()

    settings = get_settings()
    if settings.database_provider != "postgres":
        print("Product embeddings require DATABASE_PROVIDER=postgres.", file=sys.stderr)
        return 1

    repository = PostgresProductEmbeddingRepository()
    products = repository.list_embedding_sources(only_missing=args.only_missing)
    if args.limit > 0:
        products = products[: args.limit]

    if args.dry_run:
        print(f"Product embedding dry run: {len(products)} product(s)")
        print(f"Relevant fields only. Excludes price, stock, SKU, IDs, currency, and timestamps.")
        for product in products:
            print("")
            print(f"[{product['id']}] {product['name']}")
            print(product["embedding_text"])
        return 0

    provider = OpenAICompatibleEmbeddingProvider()
    try:
        for index, product in enumerate(products, start=1):
            source_text = product["embedding_text"]
            if not source_text.strip():
                print(f"[{index}/{len(products)}] skipped empty source text: {product['name']}")
                continue

            print(f"[{index}/{len(products)}] embedding {product['name']}")
            embedding = provider.embed_text(source_text)
            repository.upsert_product_embedding(
                product_id=str(product["id"]),
                embedding=embedding,
                source_text=source_text,
                embedding_model=settings.embedding_model,
            )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Product embedding complete: {len(products)} product(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
