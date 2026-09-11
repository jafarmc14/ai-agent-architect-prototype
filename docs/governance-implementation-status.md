# Governance implementation status (phases 51-60)

The runtime now includes the second governance implementation batch. Production
rollout and tuning still require real-company data and operational approval.
No paid model, high-risk mutation, extra autonomy, or production timer is enabled
by default.

| Phase | Implemented in this batch | Still required |
| --- | --- | --- |
| 51 Auditability | Decision snapshots, manager/admin reconstruction API, append-only runtime audit grants, atomic mutation audit | External tamper-resistant archive; read-trace persistence remains best-effort |
| 52 Retention | Dry-run/apply, legal holds, payload scrubbing, expired approval cleanup, transactional deletion-count audit, opt-in timers | Data-owner approval and lifecycle rules for backups/files/operational PII; scheduler activation |
| 53 Continuous evaluation | Durable unsampled backlog, delayed-feedback resampling, incident queue API and reviewed regression linkage | Reviewer frontend and production rollout |
| 54 Company abstraction | Profiles control tool/workflow permissions, policy categories, currency scope/format, response language, token/concurrency limits, routing tiers and optional autonomy | Populate real-company catalogs and approved policies; evaluate language/extraction quality |
| 55 Connectors | Product/order/support selectors and RAG resolve company adapters per request; inventory and document contracts | Additional external business-system adapters as needed; current adapters use PostgreSQL |
| 56 Tenant isolation | Request connections use non-bypass RLS; vector queries share that boundary; same-tenant FK constraints; tenant cart sessions; cache and prompt rollback partitioning | Validate historical references on each deployment; separate operator credentials from application credentials for further hardening |
| 57 Company evaluation | Shared platform plus demo/A/B contract datasets and runner; opt-in live catalog cases | Real-company policy facts/catalogs/terminology require reviewed gold labels; example profiles are not production datasets |
| 58 Advanced workflows | Opt-in versioned conditional planner, whole-plan schema/tool validation, bounded steps, execution conditions, stop at write checkpoint; deterministic simple routes preserved | Enable only after company/security evaluations and business approval |
| 59 Transactions | Durable expiring confirmations, independent manager approval for orders, mutation/audit/idempotency in one transaction, serialized cart writes, concurrent retry and rollback tests | External payment/shipping compensation requires business-system adapters; see strategy below |
| 60 Optimization | Company budgets/concurrency, scoped caches, measured query-plan CLI and evidence-based tuning gate | Production load measurements and candidate evaluations for chunking/reranker/routing/fallback; no automatic or unmeasured tuning |

## Audit reconstruction

Apply migrations before running the new code:

```powershell
py database/migrate_sqlite_to_postgres.py --schema-only
py database/validate_tenant_integrity.py --validate
py database/run_governance.py reconstruct --tenant default --request-id REQUEST_UUID
```

This CLI is a trusted operator tool requiring database credentials. It does not
authenticate a browser user. The repository requires a manager/admin request
context and constrains queries to its tenant. Do not expose the CLI as a public
API. The actor identifier is stored separately from the redacted snapshot.

Only execution facts are selected. Prompt text, conversation messages, reasoning
and analysis fields are not copied from model response metadata. Tool results and
the final visible answer are bounded/redacted, not guaranteed to be anonymized;
free-text PII detection has limits. A SHA-256 digest detects accidental changes,
not a privileged attacker who can also rewrite the digest. Duplicate request IDs
do not overwrite an existing snapshot. Trace deletion does not cascade to it.
Decision snapshot persistence errors set `decision_audit_persisted=false` and log
an error. Separately, mutation audit is part of the write transaction: its failure
rolls back the mutation and idempotency record. A later snapshot failure cannot
undo an already committed action.

## Retention policy

Defaults are technical starting points, not a legal/compliance determination.
Obtain approval from the data owner before enabling deletion.

| Data | Default / implemented behavior |
| --- | --- |
| Raw conversation | Configured maximum 30 days; messages removed after the stricter 7-day free-text PII deadline |
| LLM/request payloads and stale structured state | Content scrubbed after 7 days; numeric usage preserved |
| Trace spans | Removed after the stricter log/PII deadline (7 days) |
| LLM usage rows | At least 35 days, or configured log period if longer |
| Audit logs and decision records | 365 days; restricted audit evidence/actor IDs are an explicit exception to the 7-day payload policy |
| Evaluation results | Configured maximum 90 days; detailed rows removed after the stricter 7-day PII deadline |
| Expired approval payloads | Removed after the configured PII period following expiration |
| Operational identities/orders/tickets, aggregate metrics, incident queue, backups/files | Require separate approved lifecycle rules before claiming full retention coverage |

The job uses a transaction, advisory lock, tenant predicates and a bounded batch
(500 per target). Re-run until the backlog is drained. Dry-run reports eligible
rows without changing data. Retention is destructive; test backup/restore first.
It does not enable itself or alter `.env`.

```powershell
py database/run_governance.py retention --tenant default
py database/run_governance.py retention --tenant default --apply
```

An optional `--policy path.json` accepts validated `RetentionPolicy` fields.
A `retention_holds` row prevents the entire tenant's job from deleting/scrubbing
data. Operators adding/removing a hold must take the same transaction advisory
lock (`hashtext('retention:' || tenant_id)`) to serialize with a running job.
Filesystem reports and backups need their own retention configuration. Private
evaluation artifacts are excluded from both Git and Docker build context.

Templates under `ops/governance/` are **not installed/enabled**. Before installation,
change `/opt/ai-agent` and `--tenant default` for the deployment and verify Docker,
runtime secret paths and backups. Retention runs daily; review sampling hourly.
The templates use the backend's non-root user and do not print database secrets.

## Incident review

```powershell
py database/run_governance.py sample --tenant default
py database/run_governance.py link-regression --tenant default --incident-id INCIDENT_UUID --case-id EXISTING_CASE_ID --reviewer REVIEWER_ID
```

Sampling does not call an LLM. It creates `pending_review` incidents without
copying raw chat into a gold dataset. An operator must reproduce the incident,
add the expected behavior to `evaluation/datasets/regression/bugs.jsonl`, review
that change, and then link the existing case. Unknown case IDs and cross-tenant
incident updates are rejected. The scanner processes up to 500 pending requests
per run, oldest first, and marks them atomically. Repeated runs drain the backlog.
New or updated feedback makes a scanned request eligible again. Monitor backlog
age and increase scheduler frequency if needed.

## Verification

```powershell
py evaluation/test_governance_foundation.py
py evaluation/integration_governance.py
py evaluation/integration_tenant_transactions.py
py evaluation/test_company_workflows.py
py evaluation/run_company_evaluation.py --tenant company_a
py evaluation/run_regression.py --quick --areas authorization tools api prompt
```

Integration uses real PostgreSQL; tests roll back fixtures or explicitly clean
committed concurrency fixtures. CI applies migrations through V034 and validates
tenant foreign keys before running integration tests. Offline tests and contract
checks are not a substitute for production cross-tenant, concurrent mutation
and data-quality evaluations.

## Deployment boundary

Run pending migrations with an administrative migration connection: creating the
runtime role requires `CREATEROLE`/grant privileges. Request connections set a
transaction-local tenant/currency and `SET LOCAL ROLE ai_agent_runtime`; they
cannot bypass RLS or update/delete audit rows. Trusted operator scripts outside a
request context retain the migration connection's privileges. This protects
request execution, not a stolen administrator credential or arbitrary Python
code running in the process. Use separate operator/application credentials before
expanding the deployment's trust boundary.

V030 enforces new same-tenant references immediately and leaves historical
references `NOT VALID`. Run `validate_tenant_integrity.py --validate` before
multi-company rollout. It validates atomically and refuses invalid history;
it never guesses tenant ownership or moves existing records. Account provisioning
writes the actual `users.tenant_id` and refuses moving an existing account across
tenants. Example companies have no production catalog/policies seeded automatically.

## Approvals and compensation

Manager/admin endpoints, requiring the normal bearer token:

- `GET /api/v1/governance/approvals`
- `POST /api/v1/governance/approvals/{confirmation_id}/approve`
- `GET /api/v1/governance/incidents`
- `GET /api/v1/governance/decisions/{request_id}`

Order writes still require `HIGH_RISK_WRITE_ACTIONS_ENABLED` to be explicitly
enabled. The requesting user confirms the action, an independent manager/admin
approves it within 15 minutes, and the requesting user retries that confirmation.
Approval alone does not execute the mutation. The tenant, actor, action and
arguments are bound to the persisted key. Concurrent retries serialize and return
the first committed result; audit failures roll back the whole write. Cart writes
are additionally serialized per actor and recheck cumulative stock in PostgreSQL.
SQLite retains prototype-only confirmation behavior and is not the multi-company
production transaction backend.

Before commit, PostgreSQL rollback is the compensation mechanism. After commit,
an address correction must be a new explicitly confirmed/approved address update,
with the current shipping state revalidated. Do not automatically uncancel an
order or reverse a payment/shipment: this prototype has no payment/shipping
connector capable of proving that reversal is safe. Escalate for reconciliation
and link the original request/audit. Raw previous addresses are not retained in
mutation audit merely to enable an automatic reversal.

## Company evaluation and optimization

```powershell
py evaluation/run_company_evaluation.py --tenant default
py evaluation/run_company_evaluation.py --tenant company_a
py evaluation/run_company_evaluation.py --tenant company_b
py database/explain_company_queries.py --tenant default
py evaluation/run_optimization_review.py --baseline baseline.json --candidate candidate.json
```

The example company datasets cover configuration/permission/terminology contracts.
Add reviewed live `catalog` cases with `sku` and `expected` product-name lists and
use `--live` against prepared company data. They do not establish policy factual
accuracy for companies that have not supplied their policies.

Advanced planning remains off. When explicitly enabled in a company profile,
only the existing complex/agentic route uses `planner_v1`; simple deterministic
routes remain unchanged. Plans must be acyclic, fully validated before execution,
within the company's step budget and exposed tool set. Conditions mean execution
success/failure, not an LLM's interpretation of business success. Any write tool
stops the plan at its confirmation checkpoint. Human escalation uses the existing
dedicated workflow, not arbitrary planner-side ticket creation.

Concurrency limits are per process. Multiple backend workers need a distributed
admission controller before treating that number as a cluster-wide cap. The
optimization gate compares measured runs with matching dataset/sample counts,
zero critical failures and no quality loss. Unjustified increases above 20% warn
by failing eligibility; it never promotes or rewrites production configuration.
Query plans measured on the tiny demo fixture are not production performance
evidence. Production chunking/reranker/routing/fallback tuning remains a measured
operational exercise, not a claimed result of these tests.
