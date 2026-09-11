def build_connectors():
    from configs import get_settings
    from core.repositories.postgres_product_repository import PostgresProductRepository
    from core.repositories.postgres_order_repository import PostgresOrderRepository
    from core.repositories.postgres_support_repository import PostgresSupportRepository
    from core.repositories.postgres_vector_repository import PostgresVectorRepository
    from core.repositories.sqlite_product_repository import SQLiteProductRepository
    from core.repositories.sqlite_order_repository import SQLiteOrderRepository
    from core.repositories.sqlite_support_repository import SQLiteSupportRepository
    postgres = get_settings().database_provider == "postgres"
    return {"catalog": PostgresProductRepository() if postgres else SQLiteProductRepository(),
            "inventory": PostgresProductRepository() if postgres else SQLiteProductRepository(),
            "orders": PostgresOrderRepository() if postgres else SQLiteOrderRepository(),
            "support": PostgresSupportRepository() if postgres else SQLiteSupportRepository(),
            "documents": PostgresVectorRepository()}
