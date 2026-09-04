-- V024: Add login credentials to users.
-- Supports the frontend login gate (Phase 45). Passwords are stored as bcrypt
-- hashes only; plaintext passwords are never persisted.

ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;

CREATE INDEX IF NOT EXISTS idx_users_password_hash_lookup
    ON users (email) WHERE password_hash IS NOT NULL;