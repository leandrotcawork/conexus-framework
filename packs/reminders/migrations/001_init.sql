CREATE TABLE IF NOT EXISTS pack_reminders_jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name  TEXT NOT NULL,
    cron        TEXT NOT NULL,
    message     TEXT NOT NULL,
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pack_reminders_active
    ON pack_reminders_jobs(agent_name, active);
