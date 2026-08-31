import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = PROJECT_ROOT / "evaluation" / "reports"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.auth import AuthenticatedUser, RequestContext, request_context  # noqa: E402
from core.privacy import redact_for_logs  # noqa: E402
from core.repositories.user_repository import UserRepository  # noqa: E402
from core.services.order_service import OrderService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic authorization evaluation.")
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    args = parser.parse_args()

    users = UserRepository().list_customer_users()
    users_by_name = {user["name"]: user for user in users}
    cases = [
        {"id": "authz_001", "actor": "Budi Santoso", "role": "customer", "order_id": "ORD001", "expected_allowed": True},
        {"id": "authz_002", "actor": "Siti Aminah", "role": "customer", "order_id": "ORD001", "expected_allowed": False},
        {"id": "authz_003", "actor": "Siti Aminah", "role": "customer", "order_id": "ORD002", "expected_allowed": True},
        {"id": "authz_004", "actor": "Budi Santoso", "role": "customer", "order_id": "ORD002", "expected_allowed": False},
        {"id": "authz_005", "actor": "Support Agent", "role": "support_agent", "order_id": "ORD001", "expected_allowed": True},
    ]

    service = OrderService()
    results = []
    for case in cases:
        if case["role"] == "support_agent":
            seed_user = next(iter(users))
            user_id = str(seed_user["id"])
            email = "support@example.local"
        else:
            seed_user = users_by_name[case["actor"]]
            user_id = str(seed_user["id"])
            email = seed_user["email"]

        user = AuthenticatedUser(
            user_id=user_id,
            email=email,
            name=case["actor"],
            role=case["role"],
        )
        with request_context(RequestContext(session_id=f"eval-{case['id']}", user=user)):
            response = service.check_order_status(case["order_id"])

        allowed = "Order Details" in response
        unauthorized_success = allowed and not case["expected_allowed"]
        result_case = {
            **case,
            "actor": redact_for_logs(case["actor"]),
            "actual_allowed": allowed,
            "pass": allowed == case["expected_allowed"],
            "unauthorized_success": unauthorized_success,
            "response_preview": redact_for_logs(response)[:200],
        }
        results.append(result_case)

    summary = {
        "total_cases": len(results),
        "passed": sum(1 for result in results if result["pass"]),
        "unauthorized_successes": sum(1 for result in results if result["unauthorized_success"]),
        "target": "0 successful unauthorized access",
        "target_pass": not any(result["unauthorized_success"] for result in results),
    }

    report = {
        "name": "authorization_report_v1",
        "created_at": datetime.now().isoformat(),
        "summary": summary,
        "results": results,
    }
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    latest_path = report_dir / "authorization_report_latest.json"
    latest_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("Authorization evaluation complete.")
    print(json.dumps(summary, indent=2))
    print(f"Report saved to: {latest_path}")
    return 0 if summary["target_pass"] and summary["passed"] == summary["total_cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
