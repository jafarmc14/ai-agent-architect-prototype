from importlib import import_module
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ProductCatalogConnector(Protocol):
    def find_products_by_name(self, product_name: str) -> Any: ...
    def find_products_by_filter(self, category: str, max_price: float, min_price: float, **kwargs) -> Any: ...


@runtime_checkable
class InventoryConnector(Protocol):
    def find_products_by_name(self, product_name: str) -> Any: ...


@runtime_checkable
class OrderConnector(Protocol):
    def find_order_with_product(self, order_id: str, user_id: str | None = None) -> Any: ...
    def find_order_for_update(self, order_id: str, user_id: str | None = None) -> Any: ...


@runtime_checkable
class SupportConnector(Protocol):
    def insert_support_ticket(self, customer_message: str, *args, **kwargs) -> str: ...


@runtime_checkable
class DocumentConnector(Protocol):
    def search_chunks(self, **kwargs) -> Any: ...


class ConnectorProxy:
    """Resolve per request, never cache one tenant's adapter globally."""
    def __init__(self, kind):
        self.kind = kind

    def __getattr__(self, name):
        from core.companies import company_config
        config = company_config()
        factory = import_module(f"companies.{config.id}.adapters").build_connectors
        adapter = factory()[self.kind]
        return getattr(adapter, name)
