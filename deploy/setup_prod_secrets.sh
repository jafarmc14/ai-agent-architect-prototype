#!/usr/bin/env bash
set -euo pipefail

# Generates the production Docker secrets under PRODUCTION_SECRETS_DIR (default ./.secrets).
# Run once on the deployment host before `docker compose up`. Files are chmod 600.

SECRETS_DIR="${PRODUCTION_SECRETS_DIR:-./.secrets}"
mkdir -p "$SECRETS_DIR"
umask 077

random_secret() {
  openssl rand -hex 32
}

read_secret() {
  local name="$1" prompt="$2"
  local value="${!name:-}"
  if [ -z "$value" ]; then
    if [ -t 0 ]; then
      read -r -p "$prompt: " value
    else
      echo "[setup] $name not set; leaving empty (non-interactive run)." >&2
    fi
  fi
  printf '%s' "$value"
}

POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-$(random_secret)}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-ai_agent}"
POSTGRES_HOST="${POSTGRES_HOST:-postgres}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"

echo "[setup] writing secrets to $SECRETS_DIR"

printf '%s' "$POSTGRES_PASSWORD" > "$SECRETS_DIR/postgres_password"
printf 'postgresql://%s:%s@%s:%s/%s' \
  "$POSTGRES_USER" "$POSTGRES_PASSWORD" "$POSTGRES_HOST" "$POSTGRES_PORT" "$POSTGRES_DB" \
  > "$SECRETS_DIR/database_url"
printf '%s' "$(random_secret)" > "$SECRETS_DIR/jwt_secret_current"
printf '%s' "$(random_secret)" > "$SECRETS_DIR/jwt_secret_previous"

openrouter_key="$(read_secret OPENROUTER_API_KEY "OpenRouter API key (optional)")"
printf '%s' "$openrouter_key" > "$SECRETS_DIR/openrouter_api_key"

deepseek_key="$(read_secret DEEPSEEK_API_KEY "DeepSeek API key (optional)")"
printf '%s' "$deepseek_key" > "$SECRETS_DIR/deepseek_api_key"

kimi_key="$(read_secret KIMI_API_KEY "Kimi API key (optional)")"
printf '%s' "$kimi_key" > "$SECRETS_DIR/kimi_api_key"

embedding_key="$(read_secret EMBEDDING_API_KEY "Embedding API key (default 'ollama')")"
[ -z "$embedding_key" ] && embedding_key="ollama"
printf '%s' "$embedding_key" > "$SECRETS_DIR/embedding_api_key"

chmod 600 "$SECRETS_DIR"/*
echo "[setup] done. Files are chmod 600. Keep $SECRETS_DIR out of version control."