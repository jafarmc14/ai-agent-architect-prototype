# Evaluation

Baseline evaluation assets for the Store AI-Agent Architect prototype.

## Dataset

Baseline cases live in:

```text
evaluation/datasets/baseline/
```

Each JSONL row uses this shape:

```json
{
  "id": "stock_001",
  "query": "Do you have Nike shoes?",
  "expected_tool": "check_stock",
  "expected_arguments": {
    "product_name": "Nike"
  }
}
```

For no-tool cases, `expected_tool` is `null`. For multi-step cases, `expected_tool` and `expected_arguments` are arrays in expected call order.

## Run Baseline

```bash
py evaluation/run_baseline.py
```

Run only the first few cases for a smoke test:

```bash
py evaluation/run_baseline.py --limit 3
```

Run a specific dataset file:

```bash
py evaluation/run_baseline.py --files stock
```

Run in batches:

```bash
py evaluation/run_baseline.py --offset 0 --limit 10
py evaluation/run_baseline.py --offset 10 --limit 10
```

Add delay between cases to reduce per-minute rate limit errors:

```bash
py evaluation/run_baseline.py --limit 10 --delay-seconds 5
```

The report is saved to:

```text
evaluation/reports/baseline_report_latest.json
```

The report includes the active `provider` and `model`, based on `LLM_PROVIDER` and the selected provider-specific model setting.

## Metrics

The v1 runner records:

- tool selection
- tool argument accuracy
- whether a response was returned
- exceptions
- latency in milliseconds
- skipped cases caused by rate limits

The runner resets `toko.db` to the original dummy data before creating the evaluation baseline snapshot, restores that clean snapshot before each case, then restores the user's original `toko.db` after the run. This keeps write-tool evaluations repeatable without permanently mutating the local database.

When OpenRouter free-tier rate limits are reached, the runner stops early by default and marks the remaining cases as skipped. This keeps rate-limit failures from being counted as agent accuracy failures. Use `--continue-on-rate-limit` only when you intentionally want to keep retrying after rate-limit errors.
