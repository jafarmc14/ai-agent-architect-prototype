ALTER TABLE llm_requests
    ADD COLUMN IF NOT EXISTS task_type TEXT,
    ADD COLUMN IF NOT EXISTS system_prompt_tokens INTEGER,
    ADD COLUMN IF NOT EXISTS user_tokens INTEGER,
    ADD COLUMN IF NOT EXISTS conversation_tokens INTEGER,
    ADD COLUMN IF NOT EXISTS retrieval_tokens INTEGER,
    ADD COLUMN IF NOT EXISTS tool_schema_tokens INTEGER,
    ADD COLUMN IF NOT EXISTS estimated_output_tokens INTEGER,
    ADD COLUMN IF NOT EXISTS input_budget INTEGER,
    ADD COLUMN IF NOT EXISTS output_limit INTEGER,
    ADD COLUMN IF NOT EXISTS context_utilization_ratio NUMERIC(10, 6),
    ADD COLUMN IF NOT EXISTS within_token_budget BOOLEAN,
    ADD COLUMN IF NOT EXISTS provider_prompt_cache_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS cache_read_tokens INTEGER,
    ADD COLUMN IF NOT EXISTS cache_creation_tokens INTEGER;

CREATE INDEX IF NOT EXISTS idx_llm_requests_task_created
    ON llm_requests (task_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_llm_requests_budget_violation
    ON llm_requests (created_at DESC)
    WHERE within_token_budget = FALSE;
