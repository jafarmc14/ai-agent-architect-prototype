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

Activate TLS by adding the 443 server block into the Nginx conf.d mount, then reload:

```bash
# Ship tls.conf alongside default.conf and restart nginx
docker compose -f docker-compose.prod.yml restart nginx
```

> For renewals, `certbot renew` with the webroot path keeps working because `deploy/certbot-webroot` is mounted into Nginx (`/.well-known/acme-challenge/`). Recommended: a weekly `certbot renew` cron plus a restart of the `nginx` service.

## 5. Provision the login account

```bash
docker compose -f docker-compose.prod.yml exec backend python database/provision_login_account.py
```

Defaults: `admin@example.local` / `Admin@2026!` (role `admin`). Override via env `LOGIN_USERNAME` / `LOGIN_PASSWORD` or `--email` / `--password`. Change the default password for any real deployment.

## 6. Verify

```bash
curl -I https://ikarpedia.cloud            # 200 via frontend
curl https://ikarpedia.cloud/health        # backend health through Nginx
curl http://localhost:8000/health          # backend direct (127.0.0.1)
```

Open `https://ikarpedia.cloud` in a browser, sign in, and send a chat message.

## 7. Backup & disaster recovery

The Phase 44 scripts run on the host against the Postgres container. Add to root crontab:

```bash
crontab -e
# daily at 02:00
0 2 * * * cd /opt/ai-agent && PGHOST=localhost PGPORT=5432 PGUSER=postgres PGPASSWORD=<postgres-password> PGDATABASE=ai_agent BACKUP_DIR=/opt/ai-agent-backups BACKUP_RETENTION_DAYS=14 docker run --rm --network host -e PGHOST=localhost -e PGPORT=5432 -e PGUSER=postgres -e PGPASSWORD=<postgres-password> -e PGDATABASE=ai_agent -e BACKUP_DIR=/backups -e BACKUP_RETENTION_DAYS=14 -v /opt/ai-agent-backups:/backups -v /opt/ai-agent/scripts:/scripts:ro --entrypoint /bin/bash pgvector/pgvector:pg16@sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b /scripts/backup_postgres.sh
```

Run the mandatory restore test after each backup and after any retention change:

```bash
docker run --rm --network host -e PGHOST=localhost -e PGPORT=5432 -e PGUSER=postgres -e PGPASSWORD=<postgres-password> -e PGDATABASE=ai_agent -e BACKUP_DIR=/backups -v /opt/ai-agent-backups:/backups -v /opt/ai-agent/scripts:/scripts:ro --entrypoint /bin/bash pgvector/pgvector:pg16@sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b /scripts/test_backup_restore.sh
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