CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY,
    json_profile TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,
    phone TEXT NOT NULL,
    string_session TEXT NOT NULL,
    agent_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    last_active TIMESTAMP,
    daily_sent_count INTEGER NOT NULL DEFAULT 0,
    daily_sent_date TIMESTAMP,
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    params TEXT NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    assigned_session_id INTEGER,
    status TEXT NOT NULL,
    error_message TEXT,
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE TABLE IF NOT EXISTS message_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    message_id INTEGER NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    UNIQUE(session_id, username),
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
