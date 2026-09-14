"""Order action messages remain accurate without exposing other users' orders."""
import unittest
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.auth import AuthenticatedUser, RequestContext, request_context
from core.services.order_service import OrderService


class Orders:
    def __init__(self, status="Processing"):
        self.status = status
        self.owner_filter = None

    def find_order_for_update(self, order_id, user_id=None):
        self.owner_filter = user_id
        return {"id": order_id, "status": self.status} if self.status else None

    def list_orders_for_user(self, user_id):
        self.owner_filter = user_id
        return [{"id": "ORD005", "status": "Awaiting Payment"}]


class OrderActionExperienceTests(unittest.TestCase):
    def setUp(self):
        self.customer = RequestContext("session", user=AuthenticatedUser("customer-id"))

    def test_requires_sign_in(self):
        with request_context(RequestContext("anonymous")):
            result = OrderService(Orders()).action_availability("ORD001")
        self.assertFalse(result["actions"]["cancel"]["available"])
        self.assertIn("sign in", result["actions"]["cancel"]["reason"])

    def test_order_not_found_for_current_account(self):
        repo = Orders(status=None)
        with request_context(self.customer):
            result = OrderService(repo).action_availability("ORD001")
        self.assertEqual(repo.owner_filter, "customer-id")
        self.assertIsNone(result["status"])
        self.assertIn("your account", result["actions"]["cancel"]["reason"])

    def test_disabled_feature_and_shipped_status(self):
        with request_context(self.customer), patch("core.services.order_service.get_settings", return_value=SimpleNamespace(high_risk_write_actions_enabled=False)):
            result = OrderService(Orders()).action_availability("ORD001")
        self.assertIn("currently unavailable", result["actions"]["cancel"]["reason"])

        with request_context(self.customer), patch("core.services.order_service.get_settings", return_value=SimpleNamespace(high_risk_write_actions_enabled=True)):
            result = OrderService(Orders("Shipped")).action_availability("ORD001")
        self.assertFalse(result["actions"]["update_address"]["available"])
        self.assertIn("Shipped", result["actions"]["update_address"]["reason"])

    def test_completed_order_explains_each_action_even_when_feature_is_disabled(self):
        with request_context(self.customer), patch("core.services.order_service.get_settings", return_value=SimpleNamespace(high_risk_write_actions_enabled=False)):
            result = OrderService(Orders("Completed")).action_availability("ORD007")
        self.assertEqual(result["status"], "Completed")
        self.assertFalse(result["actions"]["cancel"]["available"])
        self.assertFalse(result["actions"]["update_address"]["available"])
        self.assertIn("Cannot cancel", result["actions"]["cancel"]["reason"])
        self.assertIn("Cannot change the shipping address", result["actions"]["update_address"]["reason"])
        self.assertIn("Completed", result["actions"]["cancel"]["reason"])
        self.assertIn("Completed", result["actions"]["update_address"]["reason"])

    def test_eligible_action_requires_independent_approval(self):
        with request_context(self.customer), patch("core.services.order_service.get_settings", return_value=SimpleNamespace(high_risk_write_actions_enabled=True)):
            result = OrderService(Orders()).action_availability("ORD001")
        self.assertTrue(result["actions"]["cancel"]["available"])
        self.assertIn("different manager or admin", result["actions"]["cancel"]["reason"])

    def test_shipped_and_completed_orders_reject_write_tools(self):
        for status in ("Shipped", "Completed"):
            with self.subTest(status=status):
                repo = Orders(status)
                with request_context(self.customer), patch("core.services.order_service.get_settings", return_value=SimpleNamespace(high_risk_write_actions_enabled=True)):
                    cancel = OrderService(repo).cancel_order("ORD001")
                    update = OrderService(repo).update_order_address("ORD001", "Jl. Sudirman No. 100, Jakarta")
                self.assertIn(f"Current status is '{status}'", cancel)
                self.assertIn(f"Current status is '{status}'", update)
                self.assertNotIn("confirm ", cancel + update)

    def test_my_orders_uses_authenticated_customer_identity(self):
        repo = Orders()
        with request_context(self.customer):
            orders = OrderService(repo).list_my_orders()
        self.assertEqual(repo.owner_filter, "customer-id")
        self.assertEqual(orders[0]["id"], "ORD005")

    def test_admin_cannot_use_customer_order_list(self):
        repo = Orders()
        admin = RequestContext("staff", user=AuthenticatedUser("admin-id", role="admin"))
        with request_context(admin):
            with self.assertRaises(PermissionError):
                OrderService(repo).list_my_orders()
        self.assertIsNone(repo.owner_filter)


if __name__ == "__main__":
    unittest.main()
