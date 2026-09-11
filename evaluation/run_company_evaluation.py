"""Offline company contracts, with opt-in database catalog cases. No LLM calls."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.auth import AuthenticatedUser, RequestContext, authorize_tool, request_context
from core.companies import company_config, company_key, money
from core.optimization.token_accounting import task_budget
from core.workflows.intent_router import classify_intent

ROOT = Path(__file__).resolve().parents[1]


def evaluate(tenant, *, live=False):
    profile = company_config(tenant)
    paths = [ROOT / "evaluation/datasets/company/platform.jsonl", ROOT / "companies" / profile.id / "evaluation.jsonl"]
    results = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            case = json.loads(line)
            user = AuthenticatedUser("company-evaluation", role=case.get("role", "customer"), tenant_id=tenant)
            with request_context(RequestContext("company-evaluation", tenant, user)):
                kind = case["kind"]
                if kind == "intent":
                    actual = classify_intent(case["query"]).value
                elif kind == "permission":
                    actual = authorize_tool(case["tool"], RequestContext("eval", tenant, user)).allowed
                elif kind == "currency":
                    actual = money(case["amount"])
                elif kind == "policy_scope":
                    actual = not profile.policy_categories or case["category"] in profile.policy_categories
                elif kind == "output_budget":
                    actual = task_budget(case["task"]).output_limit
                elif kind == "catalog":
                    if not live:
                        raise ValueError("Catalog cases require --live and a prepared PostgreSQL dataset")
                    from core.connectors import ConnectorProxy
                    actual = sorted(row["name"] for row in ConnectorProxy("catalog").find_products_by_filter(sku=case["sku"]))
                else:
                    raise ValueError(f"Unknown evaluation kind: {kind}")
                results.append({"id": case["id"], "pass": actual == case["expected"], "actual": actual})
    with request_context(RequestContext("eval", tenant)):
        version = company_key()
    return {"tenant": tenant, "company_key": version, "mode": "database" if live else "offline_contracts",
            "total": len(results), "passed": sum(row["pass"] for row in results), "results": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", default="default")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    result = evaluate(args.tenant, live=args.live)
    print(json.dumps(result, indent=2))
    return 0 if result["total"] == result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
