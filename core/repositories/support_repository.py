from configs import get_settings
from core.repositories.postgres_support_repository import PostgresSupportRepository
from core.repositories.sqlite_support_repository import SQLiteSupportRepository


class SupportRepository:
    """Repository selector for support ticket data."""

    def __new__(cls):
        from core.connectors import ConnectorProxy
        return ConnectorProxy("support")
