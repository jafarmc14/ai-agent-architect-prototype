# Production Deployment (VPS)

Deploys the full Ubichinon stack to a Hostinger VPS: Nginx (reverse proxy + TLS), FastAPI backend, Next.js frontend, PostgreSQL (pgvector), and lightweight Redis.

## Reference environment

| Item | Value |
|---|---|
| VPS | 2 vCPU, 8 GB RAM, Ubuntu (Hostinger) |
| Public IP | `<VPS-PUBLIC-IP>` |
| Domain | `ikarpedia.cloud` (DNS A record → `<VPS-PUBLIC-IP>`) |
| Repo | `https://github.com/jafarmc14/ai-agent-architect-prototype.git` (public) |
| Deploy dir | `/opt/ai-agent` |
| Compose project | `ai-agent` (`COMPOSE_PROJECT_NAME=ai-agent`) |

> The VPS previously hosted an older site (`kopi-kopi`). It is dormant and no web server is bound to ports 80/443, so the new stack can bind them directly. Leave the old project untouched.

## Architecture

```
Internet ──> Nginx (:80/:443)  ── /api/  ──> backend:8000
                               └── /     ──> frontend:3000
```

The frontend is built with an empty `NEXT_PUBLIC_API_BASE_URL`, so the browser calls same-origin `/api/v1/...` through Nginx (no CORS in normal use). Backend and frontend host ports bind to `127.0.0.1` only; only 80/443 are public.

## 1. Prerequisites (run as root)

```bash
apt update && apt upgrade -y
apt install -y docker.io docker-compose-v2
systemctl enable --now docker

# 2 GB swap as a safety margin
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# Firewall: SSH + web
ufw allow 22/tcp && ufw allow 80/tcp && ufw allow 443/tcp && ufw enable

# Confirm the public IP matches DNS
hostname -I
```

### Ollama for embeddings (must not be publicly reachable)

The backend reaches Ollama on the host via `host.docker.internal:11434`. Ollama has no authentication, so **bind it to loopback only** and block the port at the firewall:

```bash
apt install -y curl
curl -fsSL https://ollama.com/install.sh | sh
ollama pull nomic-embed-text
systemctl edit ollama      # add:  [Service]  Environment="OLLAMA_HOST=127.0.0.1:11434"
systemctl restart ollama
ufw deny 11434/tcp         # safety net if the service is ever misconfigured
```

## 2. Clone and configure

```bash
cd /opt
git clone https://github.com/jafarmc14/ai-agent-architect-prototype.git ai-agent
cd ai-agent
export COMPOSE_PROJECT_NAME=ai-agent
```

Generate secrets (8 files under `.secrets/`, chmod 600):

```bash
bash deploy/setup_prod_secrets.sh
```

Create the production `.env` (non-secret overrides; defaults already in the compose file):

```bash
cat > .env <<'EOF'
COMPOSE_PROJECT_NAME=ai-agent
NEXT_PUBLIC_API_BASE_URL=
API_CORS_ORIGINS=https://ikarpedia.cloud
API_BASE_URL=https://ikarpedia.cloud
LLM_PROVIDER=openrouter
OPENROUTER_MODEL=openrouter/free
EMBEDDING_API_BASE=http://host.docker.internal:11434/v1
EOF
```

### Recommended paid model config

`openrouter/free` is rate-limited (unsuitable for production). With paid OpenRouter credits, pin an affordable tool-calling model as primary and add GLM as a second OpenRouter fallback, then local Ollama:

```bash
cat >> .env <<'EOF'
OPENROUTER_MODEL=deepseek/deepseek-v4-flash-0731
PROVIDER_FALLBACK_ENABLED=true
PROVIDER_FALLBACK_CHAIN=openrouter:z-ai/glm-5.3-flash,ollama
EOF
```

> `PROVIDER_FALLBACK_CHAIN` accepts `provider` (model from that provider's env) or `provider:model` (pinned model), so `openrouter:z-ai/glm-5.3-flash` adds a second OpenRouter model after the primary. Apply with `docker compose -f docker-compose.prod.yml up -d backend` (no rebuild needed; env-only).

> `EMBEDDING_API_BASE` points at Ollama running on the host (`nomic-embed-text`, ~0.3 GB). The backend has `extra_hosts: ["host.docker.internal:host-gateway"]` to reach it. If you prefer an external embedding provider, set `EMBEDDING_API_BASE` accordingly.

## 3. Build and start (HTTP first)

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
curl http://localhost:8000/health
```

## 4. TLS (Let's Encrypt)

```bash
apt install -y certbot
mkdir -p deploy/certs deploy/certbot-webroot
certbot certonly --webroot -w /opt/ai-agent/deploy/certbot-webroot -d ikarpedia.cloud
```

Place the certificates where Nginx reads them:

```bash
cp /etc/letsencrypt/live/ikarpedia.cloud/fullchain.pem deploy/certs/fullchain.pem
cp /etc/letsencrypt/live/ikarpedia.cloud/privkey.pem  deploy/certs/privkey.pem
```

Activate TLS by copying the 443 server block into the Nginx conf.d mount, then reload:

```bash
# tls.conf is shipped as tls.conf.example so the HTTP-first bootstrap does not
# crash on missing certificates. Copy it into place only after certs exist.
cp deploy/nginx/tls.conf.example deploy/nginx/tls.conf
docker compose -f docker-compose.prod.yml restart nginx
```

Then force HTTPS: edit `deploy/nginx/default.conf` so port 80 only serves the ACME challenge and redirects everything else:

```bash
# In deploy/nginx/default.conf, replace the frontend proxy location with:
#   location / {
#       return 301 https://$host$request_uri;
#   }
# Keep the /.well-known/acme-challenge/ location for renewals.
docker compose -f docker-compose.prod.yml restart nginx
```

> For renewals, `certbot renew` with the webroot path keeps working because `deploy/certbot-webroot` is mounted into Nginx (`/.well-known/acme-challenge/`). Recommended: a weekly `certbot renew` cron plus a restart of the `nginx` service.

## 5. Provision the login account

```bash
docker compose -f docker-compose.prod.yml exec backend python database/provision_login_account.py
```

**Use a strong password for any real deployment** — the documented default `admin@example.local` / `Admin@2026!` is public in the README and must not be left in place:

```bash
docker compose -f docker-compose.prod.yml exec backend \
  python database/provision_login_account.py --email admin@example.local --password '<STRONG-PASSWORD>'
```

`POST /api/v1/auth/login` is rate-limited at Nginx (1 r/s, burst 5 per IP) and in-app (per-username lockout 5 failures/15 min; per-IP 20/hour). `POST /api/v1/config/llm` now requires a valid session token.

## 6. Verify

```bash
curl -I https://ikarpedia.cloud            # 200 via frontend
curl https://ikarpedia.cloud/health        # backend health through Nginx
curl http://localhost:8000/health          # backend direct (127.0.0.1)
```

Open `https://ikarpedia.cloud` in a browser, sign in, and send a chat message.

## 7. Backup & disaster recovery

The Phase 44 scripts run on the host against the Postgres container. Backup runs **weekly on Monday 02:00** with **30-day retention** (RPO ≤ 7 days). Add to root crontab:

```bash
crontab -e
# weekly on Monday at 02:00 (retention 30 days)
0 2 * * 1 cd /opt/ai-agent && PGPASSWORD=$(cat .secrets/postgres_password) && docker run --rm --network host -e PGHOST=127.0.0.1 -e PGPORT=5432 -e PGUSER=postgres -e PGPASSWORD="$PGPASSWORD" -e PGDATABASE=ai_agent -e BACKUP_DIR=/backups -e BACKUP_RETENTION_DAYS=30 -v /opt/ai-agent-backups:/backups -v /opt/ai-agent/scripts:/scripts:ro --entrypoint /bin/bash pgvector/pgvector:pg16@sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b /scripts/backup_postgres.sh
```

Run the mandatory restore test after each backup (add a second cron line, e.g. Monday 03:00) and after any retention change:

```bash
0 3 * * 1 cd /opt/ai-agent && PGPASSWORD=$(cat .secrets/postgres_password) && docker run --rm --network host -e PGHOST=127.0.0.1 -e PGPORT=5432 -e PGUSER=postgres -e PGPASSWORD="$PGPASSWORD" -e PGDATABASE=ai_agent -e BACKUP_DIR=/backups -v /opt/ai-agent-backups:/backups -v /opt/ai-agent/scripts:/scripts:ro --entrypoint /bin/bash pgvector/pgvector:pg16@sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b /scripts/test_backup_restore.sh
```

Full DR procedure and RPO/RTO are in `docs/disaster-recovery.md`.

## 8. Updating & rollback

Update:

```bash
cd /opt/ai-agent
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

Rollback to the previous image/tag:

```bash
docker compose -f docker-compose.prod.yml up -d --no-build frontend backend
# or rebuild from a pinned git tag
git checkout <previous-tag> && docker compose -f docker-compose.prod.yml up -d --build
```

## Notes and limitations

- The backend runs a single uvicorn process (no gunicorn/workers) with `mem_limit: 2g`.
- Login brute-force throttle and the provider circuit breaker are **in-memory, single-instance**; counters reset on restart. Not suitable for multi-replica deployments yet.
- Redis is provisioned with a 128 MB cap but is not consumed by the application runtime yet.
- Postgres data and Redis AOF live in named volumes (`ai_agent_postgres_prod_data`, `redis_prod_data`); back them up per Section 7.