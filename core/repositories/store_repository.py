from core.repositories.cart_repository import CartRepository
from core.repositories.order_repository import OrderRepository
from core.repositories.product_repository import ProductRepository
from core.repositories.support_repository import SupportRepository


class StoreRepository:
    """Compatibility facade that combines all domain repositories."""

    def __init__(self):
        self.product_repository = ProductRepository()
        self.order_repository = OrderRepository()
        self.cart_repository = CartRepository()
        self.support_repository = SupportRepository()

    def __getattr__(self, name: str):
        for repository in (
            self.product_repository,
            self.order_repository,
            self.cart_repository,
            self.support_repository,
        ):
            if hasattr(repository, name):
                return getattr(repository, name)
        raise AttributeError(name)
