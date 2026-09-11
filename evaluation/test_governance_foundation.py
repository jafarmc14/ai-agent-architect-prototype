"""Offline contracts for audit, retention policy and company/cache boundaries."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import ValidationError
from configs.retention import RetentionPolicy
from core.auth import AuthenticatedUser, RequestContext, request_context
from core.companies import company_config
from core.connectors import ConnectorProxy
from core.optimization.cache import TTLCache
from core.repositories.decision_audit_repository import DecisionAuditRepository
from core.services.decision_audit import digest, review_categories, snapshot


class GovernanceTests(unittest.TestCase):
    def test_audit_excludes_private_reasoning_and_redacts(self):
        value = snapshot(RequestContext("s"), {
            "request_id": "request", "analysis": "private thoughts",
            "prompt": {"version": "v1", "content": "secret system instructions"},
            "tool_calls": [{"name": "update_shipping_address", "args": {
                "new_address": "123 Main Street", "email": "customer@example.com"},
                "output": "Contact customer@example.com", "reasoning": "private thoughts"}],
            "lifecycle": [{"stage": "llm", "name": "llm.generate", "attributes": {
                "model": "local", "response": "private thoughts", "reasoning": "private thoughts"}}],
        }, "Contact customer@example.com", "success")
        serialized = json.dumps(value)
        for forbidden in ("private thoughts", "secret system instructions", "123 Main Street", "customer@example.com"):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(value["prompt_version"]["version"], "v1")
        self.assertEqual(digest(value), digest(json.loads(json.dumps(value))))
        self.assertNotEqual(digest(value), digest({**value, "status": "error"}))

    def test_reconstruction_denies_customer_before_database(self):
        with patch("core.repositories.decision_audit_repository.get_postgres_connection") as connect:
            with self.assertRaises(PermissionError):
                DecisionAuditRepository().reconstruct("request")
            connect.assert_not_called()

    def test_audit_rejects_forged_tenant_before_database(self):
        with patch("core.repositories.decision_audit_repository.get_postgres_connection") as connect:
            with self.assertRaises(PermissionError):
                DecisionAuditRepository().record({"tenant": "other"})
            connect.assert_not_called()

    def test_cache_isolates_tenant_user_role_and_anonymous_session(self):
        cache = TTLCache()
        owner = RequestContext("a", tenant_id="company_a",
                               user=AuthenticatedUser("u1", role="customer", tenant_id="company_a"))
        with request_context(owner):
            cache.set("same-key", ["private"])
            self.assertEqual(cache.get("same-key"), ["private"])
        contexts = [
            RequestContext("a", "company_b", AuthenticatedUser("u1", tenant_id="company_b")),
            RequestContext("a", "company_a", AuthenticatedUser("u2", tenant_id="company_a")),
            RequestContext("a", "company_a", AuthenticatedUser("u1", role="manager", tenant_id="company_a")),
        ]
        for context in contexts:
            with request_context(context):
                self.assertIsNone(cache.get("same-key"))
        with request_context(RequestContext("anon-a")):
            cache.set("same-key", "anonymous data")
        with request_context(RequestContext("anon-b")):
            self.assertIsNone(cache.get("same-key"))

    def test_unconfigured_company_and_unisolated_adapters_fail_closed(self):
        with self.assertRaises(PermissionError):
            company_config("unknown")
        for tenant in ("company_a", "company_b"):
            with request_context(RequestContext("s", tenant)):
                with self.assertRaises(PermissionError):
                    ConnectorProxy("catalog").find_products_by_name("shoes")
        self.assertIn("search_products", company_config("default").tools)

    def test_retention_validation(self):
        for kwargs in ({"pii_days": 0}, {"batch_size": 5001}, {"unexpected": 1}):
            with self.assertRaises(ValidationError):
                RetentionPolicy(**kwargs)

    def test_review_signals_are_deterministic(self):
        metrics = {"escalated": True, "tool_validations": [True, False], "security_alert": True}
        result = review_categories("request", metrics, tokens=9000, negative_feedback=True)
        self.assertTrue({"escalation", "tool_failure", "security_alert", "high_tokens", "negative_feedback"} <= set(result))
        self.assertEqual(result, review_categories("request", metrics, tokens=9000, negative_feedback=True))
        self.assertNotIn("high_tokens", review_categories("request", {}, tokens=None))


if __name__ == "__main__":
    unittest.main()
