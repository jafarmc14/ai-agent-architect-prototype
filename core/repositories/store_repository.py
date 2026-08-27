from core.repositories.cart_repository import CartRepository
from core.repositories.order_repository import OrderRepository
from core.repositories.product_repository import ProductRepository
from core.repositories.support_repository import SupportRepository


class StoreRepository(ProductRepository, OrderRepository, CartRepository, SupportRepository):
    """Compatibility facade that combines all domain repositories."""
