CREATE TABLE IF NOT EXISTS pack_notes_entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name  TEXT NOT NULL,
    text        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pack_notes_agent_created
    ON pack_notes_entries(agent_name, created_at DESC);
