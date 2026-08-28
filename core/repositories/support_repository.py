from configs import get_settings
from core.repositories.postgres_support_repository import PostgresSupportRepository
from core.repositories.sqlite_support_repository import SQLiteSupportRepository


class SupportRepository:
    """Repository selector for support ticket data."""

    def __new__(cls):
        if get_settings().database_provider == "postgres":
            return PostgresSupportRepository()
        return SQLiteSupportRepository()
