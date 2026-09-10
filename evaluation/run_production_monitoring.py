"""Operator CLI. Reads PostgreSQL; never invokes an LLM except explicit shadow-work."""
import argparse
import json
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.privacy import redact_for_logs
from core.repositories.postgres_connection import get_postgres_connection
from core.repositories.production_monitoring_repository import ProductionMonitoringRepository
from core.services.production_metrics import monitoring_report, promotion_gate
from core.services.production_drift import current_fingerprints


def dataset_candidates(tenant, days, limit):
    with get_postgres_connection() as conn:
        rows = conn.execute("""SELECT q.request_id, r.request_input, q.metrics FROM production_quality_events q
                            JOIN request_traces r USING (request_id) WHERE q.tenant_id = %s
                            AND q.created_at >= now() - %s * interval '1 day' ORDER BY q.created_at DESC LIMIT 10000""",
                            (tenant, days)).fetchall()
    strata = defaultdict(list)
    for row in rows:
        strata[(row["metrics"].get("intent"), row["metrics"].get("language_heuristic"))].append(row)
    total = len(rows)
    target = min(limit, total)
    allocations = {key: int(len(values)*target/total) for key, values in strata.items()} if total else {}
    for key in sorted(strata, key=lambda key: len(strata[key])*target/total - allocations[key], reverse=True)[:target-sum(allocations.values())]:
        allocations[key] += 1
    rng = random.Random(47)
    selected = [row for key, values in strata.items() for row in rng.sample(values, allocations[key])]
    return [{"id": f"production_{row['request_id']}", "query": redact_for_logs(row["request_input"] or ""),
             "intent_stratum": row["metrics"].get("intent"), "language_stratum": row["metrics"].get("language_heuristic"),
             "review_required": True, "expected_tool": None, "expected_arguments": None,
             "expected_answer": None, "source_window_days": days} for row in selected]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["report", "watch", "snapshot", "dataset", "shadow-work", "shadow-report", "promotion-check"])
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--days", type=int, default=7, choices=range(1,91), metavar="1-90")
    parser.add_argument("--limit", type=int, default=100, choices=range(1,501), metavar="1-500")
    parser.add_argument("--experiment-id", default="")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--interval-seconds", type=int, default=3600)
    args = parser.parse_args()
    repo = ProductionMonitoringRepository()
    if args.command == "watch":
        if args.interval_seconds < 60:
            parser.error("Monitoring interval must be at least 60 seconds")
        try:
            while True:
                fingerprints = current_fingerprints(args.tenant)
                previous = repo.snapshot(args.tenant, fingerprints)
                result = monitoring_report(*repo.rows(args.tenant, args.days))
                result["snapshot_changes"] = [key for key in fingerprints if previous and previous.get(key) != fingerprints[key]]
                rendered = json.dumps(result, default=str, indent=2)
                if args.output:
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_text(rendered + "\n", encoding="utf-8")
                print(rendered, flush=True)
                time.sleep(args.interval_seconds)
        except KeyboardInterrupt:
            return 0
    if args.command == "report":
        result = monitoring_report(*repo.rows(args.tenant, args.days))
    elif args.command == "snapshot":
        current = current_fingerprints(args.tenant)
        previous = repo.snapshot(args.tenant, current)
        result = {"baseline_available": previous is not None, "fingerprints": current,
                  "changed": [key for key in current if previous and previous.get(key) != current[key]]}
    elif args.command == "dataset":
        if not args.output:
            parser.error("dataset requires --output in a private review directory")
        result = dataset_candidates(args.tenant, args.days, args.limit)
    elif args.command == "shadow-work":
        from core.services.shadow_worker import drain
        result = drain(args.tenant, args.limit)
    elif args.command == "shadow-report":
        result = repo.shadow_report(args.tenant, args.experiment_id)
    else:
        if not args.experiment_id:
            parser.error("promotion-check requires --experiment-id")
        _, rows = repo.rows(args.tenant, args.days)
        result = promotion_gate(rows, args.experiment_id)
    rendered = "\n".join(json.dumps(row, default=str) for row in result) if args.command == "dataset" else json.dumps(result, default=str, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print(f"Saved {args.command} to {args.output}")
    else:
        print(rendered)
    return 1 if args.command == "promotion-check" and not result["promotable"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
