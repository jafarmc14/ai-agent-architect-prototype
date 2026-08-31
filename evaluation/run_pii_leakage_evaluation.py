import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = PROJECT_ROOT / "evaluation" / "reports"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.auth import AuthenticatedUser, RequestContext, request_context  # noqa: E402
from core.privacy import PII_INVENTORY, detect_pii, redact_for_logs, redact_text  # noqa: E402
from core.services.order_service import OrderService  # noqa: E402


class FakeOrderRepository:
    def find_order_with_product(self, order_id: str, user_id: str | None = None):
        return {
            "id": order_id,
            "customer_name": "Budi Santoso",
            "product_name": "Nike Air Max Shoes",
            "quantity": 2,
            "total_price": 2400000,
            "status": "Processing",
            "shipping_address": "Jl. Melati No. 7, Jakarta",
            "order_date": "2026-08-01",
            "estimated_arrival": "2026-08-05",
        }

    def find_order_for_update(self, order_id: str, user_id: str | None = None):
        return {
            "id": order_id,
            "status": "Processing",
            "customer_name": "Budi Santoso",
            "shipping_address": "Jl. Melati No. 7, Jakarta",
        }

    def update_order_shipping_address(self, order_id: str, new_address: str, user_id: str | None = None):
        return None


def raw_cases() -> list[dict[str, Any]]:
    return [
        {
            "id": "pii_001",
            "surface": "external_llm_payload",
            "input": "Customer: Budi Santoso, email budi@example.com, phone +6281234567890",
        },
        {
            "id": "pii_002",
            "surface": "tool_trace",
            "input": {
                "tool": "update_shipping_address",
                "args": {
                    "order_id": "ORD005",
                    "new_address": "Jl. Sudirman No. 100, Jakarta",
                    "customer_id": "11111111-1111-1111-1111-111111111111",
                },
            },
        },
        {
            "id": "pii_003",
            "surface": "payment_metadata",
            "input": "payment_reference=PAY-123 transaction_id=TXN-987 card_last4=4242",
        },
    ]


def order_service_cases() -> list[dict[str, Any]]:
    user = AuthenticatedUser(
        user_id="11111111-1111-1111-1111-111111111111",
        email="budi@example.local",
        name="Budi Santoso",
        role="customer",
    )
    service = OrderService(repository=FakeOrderRepository())
    with request_context(RequestContext(session_id="pii-eval", user=user)):
        status_response = service.check_order_status("ORD001")
        update_response = service.update_order_address("ORD001", "Jl. Baru No. 10, Jakarta")

    return [
        {
            "id": "pii_004",
            "surface": "order_status_response",
            "input": status_response,
        },
        {
            "id": "pii_005",
            "surface": "order_address_update_response",
            "input": update_response,
        },
    ]


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    redacted = redact_for_logs(case["input"])
    findings = detect_pii(redacted)
    return {
        "id": case["id"],
        "surface": case["surface"],
        "redacted_preview": redact_text(json.dumps(redacted, ensure_ascii=False))[:300],
        "pii_findings": findings,
        "pass": not findings,
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    exposure_count = sum(len(result["pii_findings"]) for result in results)
    failed = [result for result in results if not result["pass"]]
    return {
        "total_cases": len(results),
        "passed": sum(1 for result in results if result["pass"]),
        "failed": len(failed),
        "unintended_pii_exposures": exposure_count,
        "target": "0 unintended PII exposure",
        "target_pass": exposure_count == 0 and not failed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic PII leakage evaluation.")
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    args = parser.parse_args()

    cases = raw_cases() + order_service_cases()
    results = [evaluate_case(case) for case in cases]
    report = {
        "name": "pii_leakage_report_v1",
        "created_at": datetime.now().isoformat(),
        "pii_inventory": PII_INVENTORY,
        "summary": summarize(results),
        "results": results,
    }

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    latest_path = report_dir / "pii_leakage_report_latest.json"
    latest_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("PII leakage evaluation complete.")
    print(json.dumps(report["summary"], indent=2))
    print(f"Report saved to: {latest_path}")
    return 0 if report["summary"]["target_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
