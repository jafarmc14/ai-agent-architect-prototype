# Production quality, drift and model experiments (Phases 47-50)

## Defaults and scope

Monitoring records numeric/categorical signals in `production_quality_events`
after each request, including API and direct Streamlit traffic. PostgreSQL V026
is required. No candidate calls happen with `EXPERIMENT_MODE=off` (the default).
The free OpenRouter/Ollama configuration remains unchanged.

Experiments initially cover **RAG answer synthesis only**, after authorized
policy retrieval. Product/order responses remain deterministic and cart/order
mutations are never replayed. Intent, retrieval, authorization, business rules,
citations and the final hallucination checks remain the existing control path.
This is a response-model experiment, not a whole-agent experiment. No additional
LLM is invoked just to compare a deterministic response.

## Quality monitoring

```powershell
docker compose -f docker-compose.dev.yml exec -T backend python evaluation/run_production_monitoring.py report --tenant default --days 7
```

The report compares the current seven days with the preceding seven days and
includes a daily series. All time windows use UTC. Monitor:

| Signal | Interpretation |
| --- | --- |
| faithfulness | Mean human-reviewed evidence support score (0-1); null until reviewed |
| tool_accuracy | Correct tool and arguments according to reviewer; null when not assessed |
| claim_support_proxy | Existing claim checker's automatic indicator, not ground-truth faithfulness |
| tool_validation_rate | Schema/security validation success, not semantic tool accuracy |
| abstention_rate | Claim guard or explicit RAG insufficient-evidence abstention |
| escalation_rate | Requests with a successful escalation-tool ticket result; UI human requests are separate feedback/tickets |
| negative_feedback_rate | Thumbs-down or wrong-answer requests divided by rated requests |
| tokens, latency, cost | Request averages, including missing accounting counts |

Token/cost aggregates are null when any recorded LLM call lacks usage/cost or
expected call records are missing. Zero-LLM requests have zero LLM tokens/cost.
Ollama's recorded API cost excludes hardware/electricity. Provider invoices
remain authoritative. Shadow usage is separate from user-facing request cost.

Alerts require at least 30 requests in each window. Token/latency/cost increases
above 20%, distribution divergence above 0.10, or quality/rate changes above
5 percentage points trigger alerts. Review/rating metrics also require 30
reviewed/rated samples per window. These are operational alerts, not proof of
causality. Catalog/pricing changes and traffic mix can explain changes.

Continuous monitoring (foreground worker, one per tenant):

```powershell
docker compose -f docker-compose.dev.yml exec -T backend python evaluation/run_production_monitoring.py watch --tenant default --days 7 --interval-seconds 3600 --output evaluation/private/monitoring_latest.json
```

The worker logs reports and refreshes drift snapshots hourly. Supervise this
command using your deployment scheduler/process manager; it does not start
automatically with the normal application. No webhook or pager is configured.

Manager/admin API routes (Bearer token, tenant taken only from verified identity):

- `GET /api/v1/monitoring/quality?days=7`
- `POST /api/v1/monitoring/reviews/{request_id}`
- `GET /api/v1/monitoring/experiments/{experiment_id}?days=30`

A review body:

```json
{"correct": true, "faithfulness": 1.0, "tool_accuracy": true, "critical_failure": false}
```

Review against the authorized database/tool results and cited evidence. Leave
`tool_accuracy` null when not applicable. Do not treat the model's self-reported
confidence or its own generated answer as a reference label.

## Drift and dataset refresh

Query distribution uses intent and length buckets. Language distribution is an
English/Indonesian heuristic with an explicit `unknown` bucket; it is not a
general multilingual language classifier. Jensen-Shannon divergence compares
current and previous distributions without an extra LLM call.

```powershell
docker compose -f docker-compose.dev.yml exec -T backend python evaluation/run_production_monitoring.py snapshot --tenant default
```

Snapshots hash tenant-scoped catalog/variants, inventory, policy metadata and
chunk contents, current policy effectiveness, and business-rule/security/prompt
source files plus the high-risk-write setting. The first snapshot establishes a
baseline; subsequent snapshots report changed categories. A changed hash means
content/configuration changed, not necessarily degraded quality. These checks
do not detect behavior changes in third-party systems or uncaptured settings.

```powershell
docker compose -f docker-compose.dev.yml exec -T backend python evaluation/run_production_monitoring.py dataset --tenant default --days 7 --limit 100 --output evaluation/private/dataset_candidates.jsonl
```

Candidate cases are sampled proportionally across observed intent/language
strata, using the latest at most 10,000 requests. Existing PII redaction is
applied, but manual privacy review is still required. `evaluation/private/` is
gitignored. Every case is marked `review_required`; expected tool/arguments and
answers are intentionally unset. Correct labels, deduplicate, add underrepresented
security/edge cases, and review before adding cases to the golden dataset. No
production conversation is automatically published or accepted as ground truth.

## Shadow testing

Set backend environment values and restart the backend:

```dotenv
EXPERIMENT_MODE=shadow
EXPERIMENT_ID=rag-candidate-v1
EXPERIMENT_CANDIDATE_PROVIDER=ollama
EXPERIMENT_CANDIDATE_MODEL=llama3.1
EXPERIMENT_TENANTS=default
EXPERIMENT_PERCENTAGE=10
SHADOW_DAILY_JOBS=20
SHADOW_TIMEOUT_SECONDS=30
SHADOW_MAX_INPUT_TOKENS=3000
SHADOW_MAX_OUTPUT_TOKENS=500
```

Select a genuinely different candidate model for meaningful comparisons. No paid
API is required for an Ollama experiment, but the model must already be pulled.
DeepSeek/Kimi/OpenRouter candidates require their configured credentials and any
provider charges apply. Do not enable an external candidate without authorizing
that tenant's data processing.

The control answers normally. For sampled accounts, the redacted query/prompt
and already-authorized evidence are queued. The candidate response is never
returned to chat or conversation state. The queue is bounded to 20 jobs per
tenant per rolling day by default, including failures. A separate worker runs:

```powershell
docker compose -f docker-compose.dev.yml exec -T backend python evaluation/run_production_monitoring.py shadow-work --tenant default --limit 5
docker compose -f docker-compose.dev.yml exec -T backend python evaluation/run_production_monitoring.py shadow-report --tenant default --experiment-id rag-candidate-v1
```

The worker has no tools or mutation executor. Tool proposals are rejected. Its
async timeout and output/input caps bound work; SDK-level retry behavior remains
subject to that timeout. No orchestration fallback is used. Jobs older than 15
minutes are expired on worker polling, running jobs are not retried, and prompt
payloads are cleared on completion/error/expiry. If the worker is stopped, expiry
cleanup waits until its next polling run. The worker checks current experiment,
tenant, candidate and workflow configuration before executing a queued job.
Disable the experiment to stop new jobs; existing jobs are not executed under a
different experiment configuration.

The report pairs control/candidate latency, known cost and automatic claim
support/hallucination indicators. Candidate text is redacted and stored only in
the restricted shadow report, never shown to customers. Unknown cost stays null.
These proxy comparisons alone cannot approve promotion. Redaction may make a
shadow prompt differ from a local control prompt; inspect comparability before
drawing conclusions. Queue limits bound volume, not an absolute invoice total.

## A/B testing and promotion

After offline/security evaluation and shadow review, use a **new experiment ID**:

```dotenv
EXPERIMENT_MODE=ab
EXPERIMENT_ID=rag-candidate-ab-v1
EXPERIMENT_PERCENTAGE=10
```

SHA-256 assignment uses experiment ID + tenant + authenticated user ID. A user
stays in one arm across sessions/workers. Candidate exposure is capped at 10%;
control receives approximately 90% over enough distinct users, not exactly 90%
of requests. Only eligible RAG model calls are affected. Response cache bypass
applies to both arms to prevent cross-arm cached answers. The shared gateway is
never reconfigured globally; a candidate gets an isolated gateway using existing
request limits, cost governance, fallback and final claim validation.

```powershell
docker compose -f docker-compose.dev.yml exec -T backend python evaluation/run_production_monitoring.py promotion-check --tenant default --experiment-id rag-candidate-ab-v1 --days 30
```

The gate exits nonzero unless it has at least 100 fully reviewed users per arm,
complete cost/token/latency accounting, no critical failures or fallback/model
contamination, no mixed experiment/prompt configuration, and demonstrated quality
improvement using non-overlapping 95% user-level Wilson intervals. Repeated
requests by one user do not count as independent users. Candidate faithfulness
and reviewed tool accuracy must not regress; average tokens, latency and cost
must stay within a 20% regression budget. Negative feedback, escalation,
abstention or errors increasing by more than
5 percentage points block promotion (at least 30 rated requests per arm are
required). Model aliases resolving differently
and enabled routing/fallback conservatively block promotion analysis.

The gate returns a recommendation only. It never automatically deploys or
changes the control model. Promote through the existing versioned provider
configuration and CI quality/security gates only after this check passes. Start
a new experiment after any model/prompt/configuration change. Roll back candidate
traffic with `EXPERIMENT_MODE=off` and restart backend. Run experiments over a
predefined observation period to avoid interpreting repeated peeking as a valid
statistical result.

## Verification

```powershell
py evaluation/test_production_monitoring.py
py evaluation/integration_production_monitoring.py
```

Unit tests use fake providers and never call a paid API. Integration tests use
PostgreSQL, check tenant scoping, queue admission/claiming, usage missingness and
dataset staging, and roll back their fixtures. Both are wired into CI.
