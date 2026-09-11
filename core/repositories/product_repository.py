from configs import get_settings
from core.repositories.postgres_product_repository import PostgresProductRepository
from core.repositories.sqlite_product_repository import SQLiteProductRepository


class ProductRepository:
    """Repository selector for product catalog data."""

    def __new__(cls):
        from core.connectors import ConnectorProxy
        return ConnectorProxy("catalog")
