CREATE TABLE workspaces (
    id TEXT PRIMARY KEY,
    auth_user_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    legacy_imported_at TEXT
) STRICT;

CREATE TABLE quota_policies (
    workspace_id TEXT PRIMARY KEY REFERENCES workspaces(id) ON DELETE RESTRICT,
    daily_success_limit INTEGER NOT NULL CHECK (daily_success_limit >= 0),
    max_concurrent_runs INTEGER NOT NULL CHECK (max_concurrent_runs >= 1),
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE usage_reservations (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    operation TEXT NOT NULL,
    units INTEGER NOT NULL CHECK (units > 0),
    idempotency_key TEXT NOT NULL UNIQUE,
    state TEXT NOT NULL CHECK (state IN ('reserved', 'consumed', 'released')),
    root_run_id TEXT,
    usage_day_utc TEXT NOT NULL,
    created_at TEXT NOT NULL,
    finalized_at TEXT,
    reason TEXT
) STRICT;

CREATE TABLE runs (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    task_id TEXT NOT NULL,
    purpose TEXT NOT NULL CHECK (purpose IN ('problem', 'diagram')),
    status TEXT NOT NULL CHECK (
        status IN ('queued', 'running', 'completed', 'failed', 'cancelled', 'timed_out')
    ),
    retry_of TEXT REFERENCES runs(id) ON DELETE RESTRICT,
    quota_reservation_id TEXT REFERENCES usage_reservations(id) ON DELETE RESTRICT,
    queued_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}'
) STRICT;

CREATE INDEX runs_workspace_status_idx ON runs(workspace_id, status);
CREATE INDEX runs_workspace_task_idx ON runs(workspace_id, task_id);
CREATE INDEX usage_workspace_day_state_idx
    ON usage_reservations(workspace_id, usage_day_utc, state);
