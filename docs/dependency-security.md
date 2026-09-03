# Dependency and Supply-Chain Security

## Policy

- Direct Python and npm dependencies are pinned to exact versions.
- Python transitive dependencies are locked in `requirements.txt` generated from `requirements.in`.
- npm transitive dependencies are locked in `frontend/package-lock.json` and installed with `npm ci`.
- Third-party Docker images are pinned by immutable digest in Dockerfiles, Compose files, and CI.
- `HIGH` and `CRITICAL` vulnerabilities fail CI unless the scanner explicitly reports them as unfixed and an approved exception exists.
- Dependency upgrades require review of release notes, advisories, license changes, and transitive changes.

## High-Risk Review

| Package family | Risk | Review controls |
|---|---|---|
| `langchain*`, `langgraph*`, `langsmith` | Executes orchestration and handles untrusted model/retrieval data | Keep tool exposure and prompt-injection tests enabled; review execution and serialization changes |
| `langchain-openai`, `openai` | Sends application context to external providers | Preserve PII redaction and provider allow-list tests; review endpoint and transport changes |
| `fastapi`, `starlette`, `uvicorn` | Internet-facing HTTP boundary | Run API authorization, CORS, and request validation tests after upgrades |
| `next`, `react`, `react-dom` | Browser-facing rendering and build pipeline | Run `npm audit`, production build, and review framework security advisories |
| `streamlit` | Development UI with local runtime access | Keep development-only usage and avoid exposing it as the production boundary |
| `psycopg` | Database connectivity and SQL execution | Review protocol/parameterization changes and run PostgreSQL integration tests |

## Upgrade Procedure

1. Update `requirements.in` or `frontend/package.json` intentionally.
2. Regenerate the corresponding lockfile.
3. Run `pip-audit`, `npm audit`, and image scans.
4. Run the application and security evaluation suites.
5. Record any accepted exception with package, advisory, impact, owner, mitigation, and expiry date.

Docker base image digests should be refreshed deliberately and reviewed like dependency upgrades. Dependabot is configured to open update pull requests for these ecosystems.
