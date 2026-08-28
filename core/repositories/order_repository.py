from configs import get_settings
from core.repositories.postgres_order_repository import PostgresOrderRepository
from core.repositories.sqlite_order_repository import SQLiteOrderRepository


class OrderRepository:
    """Repository selector for order data."""

    def __new__(cls):
        if get_settings().database_provider == "postgres":
            return PostgresOrderRepository()
        return SQLiteOrderRepository()
