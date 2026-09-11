"""Trusted operator CLI. This is not an end-user authentication boundary."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.auth import AuthenticatedUser, RequestContext, request_context
from configs.retention import RetentionPolicy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("reconstruct", "retention", "sample", "link-regression"))
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--request-id")
    parser.add_argument("--incident-id")
    parser.add_argument("--case-id")
    parser.add_argument("--reviewer")
    parser.add_argument("--apply", action="store_true", help="Apply bounded retention deletion; default is dry-run")
    parser.add_argument("--policy", type=Path, help="Optional approved retention policy JSON")
    args = parser.parse_args()
    if args.apply and args.command != "retention":
        parser.error("--apply is only valid for retention")
    if args.command == "reconstruct":
        if not args.request_id:
            parser.error("reconstruct requires --request-id")
        from uuid import UUID
        UUID(args.request_id)
        from core.repositories.decision_audit_repository import DecisionAuditRepository
        user = AuthenticatedUser(user_id="operator", role="admin", tenant_id=args.tenant)
        with request_context(RequestContext(session_id="operator", tenant_id=args.tenant, user=user)):
            result = DecisionAuditRepository().reconstruct(args.request_id)
        if result is None:
            print("Decision not found for this tenant.")
            return 1
    elif args.command == "retention":
        from core.services.retention import run_retention
        policy = RetentionPolicy.model_validate_json(args.policy.read_text()) if args.policy else RetentionPolicy()
        result = run_retention(args.tenant, policy=policy, apply=args.apply)
    elif args.command == "sample":
        from core.services.continuous_evaluation import sample_requests
        result = sample_requests(args.tenant)
    else:
        if not all((args.incident_id, args.case_id, args.reviewer)):
            parser.error("link-regression requires --incident-id, --case-id and --reviewer")
        from core.services.continuous_evaluation import link_regression
        result = {"linked": link_regression(args.tenant, args.incident_id, args.case_id, args.reviewer)}
    print(json.dumps(result, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
