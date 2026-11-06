-- Reference copy of the SQLite schema (the app creates it automatically). Generated from database.SCHEMA.
-- For the online Supabase database use supabase/schema.sql instead.
CREATE TABLE IF NOT EXISTS candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    work_authorisation TEXT NOT NULL DEFAULT '',
    position TEXT NOT NULL DEFAULT '',
    preferred_department TEXT NOT NULL DEFAULT '',
    highest_qualification TEXT NOT NULL DEFAULT '',
    field_of_study TEXT NOT NULL DEFAULT '',
    current_title TEXT NOT NULL DEFAULT '',
    current_employer TEXT NOT NULL DEFAULT '',
    years_experience TEXT NOT NULL DEFAULT '',
    notice_period TEXT NOT NULL DEFAULT '',
    available_from TEXT NOT NULL DEFAULT '',
    expected_salary TEXT NOT NULL DEFAULT '',
    work_arrangement TEXT NOT NULL DEFAULT '',
    linkedin_url TEXT NOT NULL DEFAULT '',
    portfolio_url TEXT NOT NULL DEFAULT '',
    referral_source TEXT NOT NULL DEFAULT '',
    cover_note TEXT NOT NULL DEFAULT '',
    cv_text TEXT NOT NULL DEFAULT '',
    cv_filename TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'web',
    consent_at TEXT NOT NULL DEFAULT '',
    stage TEXT NOT NULL DEFAULT 'Applied',
    stage_updated_at TEXT NOT NULL DEFAULT '',
    shortlist_email_sent_at TEXT NOT NULL DEFAULT '',
    interview_when TEXT NOT NULL DEFAULT '',
    meet_link TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS positions (
    name               TEXT PRIMARY KEY,
    min_years          REAL NOT NULL DEFAULT 0,
    min_education      TEXT NOT NULL DEFAULT 'Bachelor',
    required_keywords  TEXT NOT NULL DEFAULT '',
    preferred_keywords TEXT NOT NULL DEFAULT '',
    w_exp              REAL NOT NULL DEFAULT 0.25,
    w_edu              REAL NOT NULL DEFAULT 0.25,
    w_req              REAL NOT NULL DEFAULT 0.30,
    w_pref             REAL NOT NULL DEFAULT 0.20
);

CREATE TABLE IF NOT EXISTS screenings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    position     TEXT NOT NULL,
    score        REAL NOT NULL,
    status       TEXT NOT NULL,                -- Pass | Needs Review | Reject
    notes        TEXT DEFAULT '',
    breakdown    TEXT NOT NULL,                -- JSON
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS interviews (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id          INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    interviewer           TEXT NOT NULL,
    interview_date        TEXT NOT NULL DEFAULT '',
    skills_rating         INTEGER NOT NULL,    -- 1..5
    communication_rating  INTEGER NOT NULL,    -- 1..5
    culture_rating        INTEGER NOT NULL,    -- 1..5
    overall_rating        INTEGER NOT NULL,    -- 1..5 - the recruiter's personal ranking
    recommendation        TEXT NOT NULL,       -- Yes | Maybe | No  (right person for the job?)
    notes                 TEXT NOT NULL DEFAULT '',
    created_at            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS interns (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER NOT NULL UNIQUE REFERENCES candidates(id) ON DELETE CASCADE,
    department   TEXT NOT NULL,
    supervisor   TEXT NOT NULL DEFAULT '',
    start_date   TEXT NOT NULL DEFAULT '',
    token        TEXT NOT NULL UNIQUE,         -- secret key in the intern's personal link
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS intern_updates (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    intern_id  INTEGER NOT NULL REFERENCES interns(id) ON DELETE CASCADE,
    message    TEXT NOT NULL,
    author     TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS intern_courses (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    intern_id  INTEGER NOT NULL REFERENCES interns(id) ON DELETE CASCADE,
    title      TEXT NOT NULL,
    provider   TEXT NOT NULL DEFAULT '',
    link       TEXT NOT NULL DEFAULT '',
    note       TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS faq (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    question   TEXT NOT NULL,
    answer     TEXT NOT NULL,
    keywords   TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS chat_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    question   TEXT NOT NULL,
    matched    INTEGER NOT NULL,               -- 1 answered, 0 not understood
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS escalations (          -- chatbot "talk to a recruiter" requests (human hand-off)
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL,
    message     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'Open',  -- Open | Resolved
    note        TEXT NOT NULL DEFAULT '',      -- recruiter's resolution note
    created_at  TEXT NOT NULL,
    resolved_at TEXT NOT NULL DEFAULT '',
    channel     TEXT NOT NULL DEFAULT 'web',   -- web | whatsapp | api
    contact     TEXT NOT NULL DEFAULT ''       -- WhatsApp number / chat user id, when there is no email
);

CREATE TABLE IF NOT EXISTS bot_sessions (         -- where each WhatsApp / API user is in the chat (hand-off steps)
    channel    TEXT NOT NULL,
    user_id    TEXT NOT NULL,
    state      TEXT NOT NULL DEFAULT 'idle',     -- idle | ask_name | ask_email | ask_message
    data       TEXT NOT NULL DEFAULT '{}',       -- JSON: name, email, last_question, menu
    updated_at TEXT NOT NULL,
    PRIMARY KEY (channel, user_id)
);

CREATE TABLE IF NOT EXISTS bot_seen (             -- inbound message ids already handled (a chat provider may deliver one message twice)
    message_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usage_events (         -- website usage (no IP address, no full browser string, see usage.py)
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    day        TEXT NOT NULL,                  -- YYYY-MM-DD (UTC)
    event      TEXT NOT NULL,                  -- page_view | admin_view | application_submitted | chat_message | ...
    path       TEXT NOT NULL DEFAULT '',       -- the page, without the ?query
    status     INTEGER,                        -- HTTP status
    visitor    TEXT NOT NULL DEFAULT '',       -- daily-changing anonymous hash, counts unique visitors
    device     TEXT NOT NULL DEFAULT '',       -- mobile | tablet | desktop | bot
    browser    TEXT NOT NULL DEFAULT '',       -- Chrome | Safari | Firefox | Edge | Other
    referrer   TEXT NOT NULL DEFAULT '',       -- the site name only (e.g. google.com), never the full address
    channel    TEXT NOT NULL DEFAULT 'web',    -- web | whatsapp | api
    detail     TEXT NOT NULL DEFAULT ''        -- e.g. matched / unmatched for a chat message
);

CREATE TABLE IF NOT EXISTS integrations_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER,
    screening_id INTEGER,
    service      TEXT NOT NULL,                -- zapier | sheets | excel
    action       TEXT NOT NULL,                -- event name (application_received, shortlist_email, ...) | append | write
    success      INTEGER NOT NULL,
    status_code  INTEGER,
    detail       TEXT DEFAULT '',
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_screenings_candidate ON screenings(candidate_id);
CREATE INDEX IF NOT EXISTS idx_interviews_candidate ON interviews(candidate_id);
CREATE INDEX IF NOT EXISTS idx_log_screening ON integrations_log(screening_id);
CREATE INDEX IF NOT EXISTS idx_updates_intern ON intern_updates(intern_id);
CREATE INDEX IF NOT EXISTS idx_usage_day ON usage_events(day);
CREATE INDEX IF NOT EXISTS idx_usage_event_day ON usage_events(event, day);
