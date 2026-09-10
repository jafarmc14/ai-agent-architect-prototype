# Production pilot (Phase 46)

Start with 5-10 invited internal testers and one manager. Provision individual
accounts using `database/provision_login_account.py`; never share a login.
Keep OpenRouter free and Ollama settings unchanged. Paid providers are optional.

## Enable

Apply the pending migration without re-importing SQLite:

```powershell
py database/migrate_sqlite_to_postgres.py --schema-only
```

Set these non-secret values in the backend environment, then restart it:

```dotenv
PILOT_ENABLED=true
PILOT_ALLOWED_ACCOUNTS=default:USER_UUID_1,default:USER_UUID_2,default:MANAGER_UUID
```

Replace each UUID with the actual `users.id`. Each entry is an exact tenant/user
pair. Empty allowlists deny everyone, including admins. The check runs at login,
each chat, feedback, report request, and runtime configuration update. Existing
JWTs do not bypass removal from the list. Direct Streamlit runtime also checks
pilot membership. Runtime configuration is manager/admin-only during pilot.
The default is disabled to preserve development access. Do not expose an enabled
pilot until the allowlist and PostgreSQL migrations are ready.

## Feedback

Each completed API answer has Helpful, Not helpful, Wrong answer, Report issue,
and Request human icon buttons. Feedback is stored in `pilot_feedback`, linked
to an owned `request_traces.request_id`. Anonymous, foreign-tenant, foreign-user,
and unfinished requests cannot receive feedback. A repeated submission is
idempotent; changing thumbs replaces the prior rating. Issue reports and human
requests create an open support ticket in the same database transaction. Tickets
link to the request for authorized investigation. They do not promise a response
time or send an external notification; assign staff to monitor open tickets.
No extra free-text PII or conversation copies are collected by the feedback UI.

## Observe real usage

An invited manager/admin can open **Details > Pilot usage**, select 7/30/90 days,
and click refresh. `GET /api/v1/pilot/usage?days=7` provides the same tenant-scoped
report using a Bearer token. It includes daily request/tester counts and p95
latency, plus LLM input/output tokens, recorded cost, cost source, and missing
measurement counts grouped by provider/model/workflow. Requests are marked at
creation with `request_traces.metadata.pilot=true`; non-pilot traffic is excluded.
Period boundaries use a rolling interval and daily buckets use UTC.

Unknown cost is not zero. Known costs may be provider-reported or estimated;
use `cost_source` and unknown counts before comparing with invoices. Report data
comes from existing request/LLM persistence, so missing telemetry must also be
investigated. No real usage patterns are claimed until testers generate traffic.

Review wrong answers, open tickets, latency, unknown accounting, and cost daily.
Pause expansion for critical security failures or repeated incorrect business
facts. Turn off exposed ingress to pause the pilot; setting PILOT_ENABLED=false
removes its membership restriction and is not a shutdown switch.

## Manual checks

1. An invited account can log in and chat; a non-invited account cannot.
2. Ask a stock/policy question and submit each feedback type.
3. Retry Request human; verify the same ticket number and one database row.
4. Switch Helpful to Not helpful; verify one current rating.
5. Try another user's request ID via API; expect 404 and no ticket.
6. Load the manager report after several real chats. A customer receives 403.
7. Remove a tester from the allowlist and restart; their existing token is denied.
