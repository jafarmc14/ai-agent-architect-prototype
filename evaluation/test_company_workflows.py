import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import ValidationError
from core.auth import RequestContext, request_context
from core.companies import company_config
from core.optimization.tuning import tuning_gate
from core.workflows.conditional_plan import ConditionalPlan, execute_plan
from evaluation.run_company_evaluation import evaluate


class FakeTool:
    def __init__(self):
        self.calls = []

    def invoke(self, arguments):
        self.calls.append(arguments)
        return "Confirmation required. No mutation performed."


class CompanyWorkflowTests(unittest.TestCase):
    def test_company_contract_datasets(self):
        for tenant in ("default", "company_a", "company_b"):
            report = evaluate(tenant)
            self.assertEqual(report["passed"], report["total"], report)

    def test_cycles_and_unknown_fields_are_rejected(self):
        for plan in ({"steps": [{"id": "one", "tool": "check_stock", "arguments": {}, "depends_on": ["one"]}]},
                     {"steps": [], "reasoning": "private"}):
            with self.assertRaises(ValidationError):
                ConditionalPlan.model_validate(plan)

    def test_plan_disabled_by_default(self):
        with self.assertRaises(PermissionError):
            execute_plan({"steps": []}, {}, lambda _: None, {})

    def test_all_steps_validated_before_execution(self):
        profile = company_config("default").model_copy(update={"autonomy_enabled": True})
        tool = FakeTool()
        plan = {"steps": [
            {"id": "one", "tool": "check_stock", "arguments": {"product_name": "Nike"}},
            {"id": "two", "tool": "execute_sql", "arguments": {}}]}
        with patch("core.workflows.conditional_plan.company_config", return_value=profile):
            with self.assertRaises(PermissionError):
                execute_plan(plan, {"check_stock": tool}, lambda _: None, {})
        self.assertEqual(tool.calls, [])

    def test_write_checkpoint_stops_following_steps(self):
        profile = company_config("default").model_copy(update={"autonomy_enabled": True})
        cart, stock = FakeTool(), FakeTool()
        plan = {"steps": [
            {"id": "cart", "tool": "add_product_to_cart", "arguments": {"product_name": "Nike", "quantity": 1}},
            {"id": "stock", "tool": "check_stock", "arguments": {"product_name": "Nike"}}]}
        with request_context(RequestContext("plan")), patch("core.workflows.conditional_plan.company_config", return_value=profile):
            result = execute_plan(plan, {"check_stock": stock, "add_product_to_cart": cart}, lambda _: None, {})
        self.assertEqual(result["cart"]["status"], "approval_required")
        self.assertEqual(len(cart.calls), 1)
        self.assertEqual(stock.calls, [])

    def test_tuning_requires_improvement_and_zero_critical_failures(self):
        baseline = {"dataset_version": "v1", "samples": 50, "correct_rate": .95, "critical_failures": 0,
                    "avg_tokens": 100, "p95_latency_ms": 1000, "cost_per_correct_answer": 0}
        self.assertFalse(tuning_gate(baseline, baseline)["eligible_for_review"])
        self.assertFalse(tuning_gate(baseline, {**baseline, "avg_tokens": 130})["eligible_for_review"])
        self.assertFalse(tuning_gate(baseline, {**baseline, "avg_tokens": 90, "critical_failures": 1})["eligible_for_review"])
        self.assertTrue(tuning_gate(baseline, {**baseline, "avg_tokens": 90})["eligible_for_review"])


if __name__ == "__main__":
    unittest.main()
