import argparse
import json
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_REPORT_DIR = PROJECT_ROOT / "evaluation" / "loadtest"
DEFAULT_USERS = [1, 5, 10, 25, 50]

DEFAULT_MESSAGE_POOL = [
    "What is the return policy?",
    "Find black shoes size 42 under Rp500,000",
    "What is the status of order ORD001?",
    "Compare Nike Air Max and Adidas Ultraboost",
    "Add 2 Nike shoes to my cart",
    "What payment methods do you accept?",
    "How do I claim warranty?",
    "What are your store operating hours?",
    "Track my order ORD006",
    "Cancel my order ORD002",
]


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((percent / 100.0) * len(ordered))))
    return round(ordered[index], 2)


def summarize_distribution(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"samples": 0, "avg": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}
    return {
        "samples": len(values),
        "avg": round(sum(values) / len(values), 2),
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
        "p99": percentile(values, 99),
        "max": round(max(values), 2),
    }


def find_target_processes() -> list[psutil.Process]:
    targets = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = " ".join(proc.info.get("cmdline") or [])
            if "api.main" in cmdline and "uvicorn" in cmdline:
                targets.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return targets


def sample_processes(targets: list[psutil.Process]) -> dict[str, float]:
    cpu_percent = 0.0
    memory_mb = 0.0
    count = 0
    for proc in targets:
        try:
            cpu_percent += proc.cpu_percent(interval=None)
            memory_mb += proc.memory_info().rss / (1024 * 1024)
            count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return {"cpu_percent": round(cpu_percent, 2), "memory_mb": round(memory_mb, 2), "processes": count}


def sample_db_connections(database_url: str | None) -> int | None:
    if not database_url:
        return None
    try:
        import psycopg

        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
                )
                row = cursor.fetchone()
        total = int(row[0]) if row else 0
        return max(0, total - 1)
    except Exception:
        return None


class SystemSampler(threading.Thread):
    def __init__(self, database_url: str | None, sample_interval: float):
        super().__init__(daemon=True)
        self.database_url = database_url
        self.sample_interval = sample_interval
        self._stop = threading.Event()
        self.cpu_samples: list[float] = []
        self.memory_samples: list[float] = []
        self.db_samples: list[int] = []
        self.targets = find_target_processes()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        for proc in self.targets:
            try:
                proc.cpu_percent(interval=None)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        while not self._stop.is_set():
            metrics = sample_processes(self.targets)
            self.cpu_samples.append(metrics["cpu_percent"])
            self.memory_samples.append(metrics["memory_mb"])
            db_count = sample_db_connections(self.database_url)
            if db_count is not None:
                self.db_samples.append(db_count)
            self._stop.wait(self.sample_interval)


def send_request(
    base_url: str,
    message: str,
    session_id: str,
    timeout: float,
) -> dict[str, Any]:
    started = time.perf_counter()
    payload = {"message": message, "session_id": session_id}
    try:
        response = requests.post(
            f"{base_url.rstrip('/')}/api/v1/chat",
            json=payload,
            timeout=timeout,
        )
        http_latency_ms = round((time.perf_counter() - started) * 1000, 2)
        status_code = response.status_code
        body = response.json() if response.content else {}
    except requests.RequestException as exc:
        return {
            "session_id": session_id,
            "http_status_code": 0,
            "http_latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "error": True,
            "error_message": str(exc),
        }

    token_usage = body.get("token_usage") or {}
    app_latency_ms = body.get("request_latency_ms")
    has_error = status_code >= 400 or bool(body.get("exception")) or body.get("request_status") == "error"
    return {
        "session_id": session_id,
        "http_status_code": status_code,
        "http_latency_ms": http_latency_ms,
        "app_latency_ms": app_latency_ms,
        "llm_latency_ms": token_usage.get("llm_latency_ms"),
        "llm_calls": token_usage.get("llm_calls"),
        "provider_fallbacks": token_usage.get("provider_fallbacks", 0),
        "fallback_used": (token_usage.get("provider_fallbacks") or 0) > 0,
        "providers": token_usage.get("providers") or [],
        "models": token_usage.get("models") or [],
        "error": has_error,
        "error_message": body.get("exception"),
        "request_status": body.get("request_status"),
    }


def run_level(
    base_url: str,
    users: int,
    iterations_per_user: int,
    message_pool: list[str],
    database_url: str | None,
    sample_interval: float,
    timeout: float,
    seed: int,
) -> dict[str, Any]:
    rng = random.Random(seed)
    total_tasks = users * iterations_per_user
    started = time.perf_counter()

    sampler = SystemSampler(database_url, sample_interval)
    sampler.start()

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=users) as executor:
        futures = []
        for index in range(total_tasks):
            message = rng.choice(message_pool)
            session_id = f"load-u{users}-{index}"
            futures.append(executor.submit(send_request, base_url, message, session_id, timeout))
        for future in as_completed(futures):
            results.append(future.result())

    sampler.stop()
    sampler.join(timeout=5)
    duration_seconds = round(time.perf_counter() - started, 3)

    http_latencies = [r["http_latency_ms"] for r in results]
    app_latencies = [r["app_latency_ms"] for r in results if isinstance(r.get("app_latency_ms"), (int, float))]
    llm_latencies = [r["llm_latency_ms"] for r in results if isinstance(r.get("llm_latency_ms"), (int, float))]
    errors = [r for r in results if r["error"]]
    fallbacks = [r for r in results if r["fallback_used"]]

    cpu_summary = summarize_distribution(sampler.cpu_samples) if sampler.cpu_samples else None
    memory_summary = summarize_distribution(sampler.memory_samples) if sampler.memory_samples else None
    db_summary = summarize_distribution([float(v) for v in sampler.db_samples]) if sampler.db_samples else None

    return {
        "concurrent_users": users,
        "total_requests": len(results),
        "duration_seconds": duration_seconds,
        "requests_per_second": round(len(results) / duration_seconds, 2) if duration_seconds else 0.0,
        "error_count": len(errors),
        "error_rate": round(len(errors) / len(results), 4) if results else 0.0,
        "fallback_count": len(fallbacks),
        "fallback_rate": round(len(fallbacks) / len(results), 4) if results else 0.0,
        "latency_http_ms": summarize_distribution(http_latencies),
        "latency_app_ms": summarize_distribution(app_latencies),
        "latency_llm_ms": summarize_distribution(llm_latencies),
        "cpu": cpu_summary,
        "memory_mb": memory_summary,
        "db_connections": db_summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 43 load test: concurrency, latency percentiles, and system metrics.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--users", default="1,5,10,25,50", help="Comma-separated concurrency levels.")
    parser.add_argument("--iterations-per-user", type=int, default=15)
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--message-pool", default=None, help="Path to JSON file with a list of messages.")
    parser.add_argument("--database-url", default=None, help="PostgreSQL URL for pg_stat_activity sampling.")
    parser.add_argument("--sample-interval", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--seed", type=int, default=20260904)
    args = parser.parse_args()

    users = [int(value) for value in args.users.split(",") if value.strip()]
    message_pool = list(DEFAULT_MESSAGE_POOL)
    if args.message_pool:
        message_pool = json.loads(Path(args.message_pool).read_text(encoding="utf-8"))

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    print("Phase 43 load test")
    print(f"  base URL        : {args.base_url}")
    print(f"  concurrency     : {users}")
    print(f"  iterations/user : {args.iterations_per_user}")
    print(f"  total requests  : {sum(users) * args.iterations_per_user}")
    print("Note: raise USER_RATE_LIMIT_REQUESTS and TENANT_DAILY_REQUEST_QUOTA or rotate session_id to avoid quota blocks.")
    print("")

    levels = []
    for user_count in users:
        print(f"[load] concurrency={user_count} running...")
        level = run_level(
            args.base_url,
            user_count,
            args.iterations_per_user,
            message_pool,
            args.database_url,
            args.sample_interval,
            args.timeout,
            args.seed + user_count,
        )
        levels.append(level)
        print(f"[load] concurrency={user_count} done: rps={level['requests_per_second']} "
              f"p50={level['latency_http_ms']['p50']}ms p95={level['latency_http_ms']['p95']}ms "
              f"p99={level['latency_http_ms']['p99']}ms error={level['error_rate']} fallback={level['fallback_rate']}")

    report = {
        "name": "load_test_report_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "base_url": args.base_url,
            "iterations_per_user": args.iterations_per_user,
            "message_pool_size": len(message_pool),
            "sample_interval_seconds": args.sample_interval,
        },
        "levels": levels,
    }
    report_path = report_dir / "load_test_report_latest.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("")
    print(f"Report saved to: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())