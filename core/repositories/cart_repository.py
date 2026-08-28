from configs import get_settings
from core.repositories.postgres_cart_repository import PostgresCartRepository
from core.repositories.sqlite_cart_repository import SQLiteCartRepository


class CartRepository:
    """Repository selector for shopping cart data."""

    def __new__(cls):
        if get_settings().database_provider == "postgres":
            return PostgresCartRepository()
        return SQLiteCartRepository()
