"""Persistence for the recruitment portal: SQLite on your computer, or Postgres (Supabase) online.

Set DATABASE_URL in .env to use Supabase (see supabase/README.md); leave it blank to keep using the SQLite file.
Both backends run the same SQL through the same small interface (see pgcompat.py).

Tables: candidates, positions, screenings, interviews, interns, intern_updates,
intern_courses, faq, chat_log, escalations, bot_sessions, bot_seen, usage_events, integrations_log, settings.
"""
from __future__ import annotations

import json
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

import config
import pgcompat

# Every application field stored on a candidate. Used both to create the table and to add
# any missing column to an older database automatically (see _ensure_columns).
CANDIDATE_FIELDS: list[tuple[str, str]] = [
    ("name", "TEXT NOT NULL DEFAULT ''"),
    ("email", "TEXT NOT NULL DEFAULT ''"),
    ("phone", "TEXT NOT NULL DEFAULT ''"),
    ("location", "TEXT NOT NULL DEFAULT ''"),
    ("work_authorisation", "TEXT NOT NULL DEFAULT ''"),
    ("position", "TEXT NOT NULL DEFAULT ''"),
    ("preferred_department", "TEXT NOT NULL DEFAULT ''"),
    ("highest_qualification", "TEXT NOT NULL DEFAULT ''"),
    ("field_of_study", "TEXT NOT NULL DEFAULT ''"),
    ("current_title", "TEXT NOT NULL DEFAULT ''"),
    ("current_employer", "TEXT NOT NULL DEFAULT ''"),
    ("years_experience", "TEXT NOT NULL DEFAULT ''"),   # as declared by the applicant
    ("notice_period", "TEXT NOT NULL DEFAULT ''"),
    ("available_from", "TEXT NOT NULL DEFAULT ''"),
    ("expected_salary", "TEXT NOT NULL DEFAULT ''"),
    ("work_arrangement", "TEXT NOT NULL DEFAULT ''"),
    ("linkedin_url", "TEXT NOT NULL DEFAULT ''"),
    ("portfolio_url", "TEXT NOT NULL DEFAULT ''"),
    ("referral_source", "TEXT NOT NULL DEFAULT ''"),
    ("cover_note", "TEXT NOT NULL DEFAULT ''"),
    ("cv_text", "TEXT NOT NULL DEFAULT ''"),
    ("cv_filename", "TEXT NOT NULL DEFAULT ''"),
    ("source", "TEXT NOT NULL DEFAULT 'web'"),
    ("consent_at", "TEXT NOT NULL DEFAULT ''"),
    ("stage", "TEXT NOT NULL DEFAULT 'Applied'"),
    ("stage_updated_at", "TEXT NOT NULL DEFAULT ''"),
    ("shortlist_email_sent_at", "TEXT NOT NULL DEFAULT ''"),
    ("interview_when", "TEXT NOT NULL DEFAULT ''"),     # free text shown in the invitation
    ("meet_link", "TEXT NOT NULL DEFAULT ''"),
]
CANDIDATE_COLUMNS = {c for c, _ in CANDIDATE_FIELDS}


def _candidates_sql() -> str:
    cols = ",\n    ".join(f"{c} {t}" for c, t in CANDIDATE_FIELDS)
    return ("CREATE TABLE IF NOT EXISTS candidates (\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n    "
            + cols + ",\n    created_at TEXT NOT NULL\n);")


SCHEMA = _candidates_sql() + """

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
"""


def backend() -> str:
    """"postgres" when Supabase is configured (DATABASE_URL, or SUPABASE_URL + SUPABASE_SERVICE_KEY), otherwise "sqlite"."""
    return "postgres" if (config.DATABASE_URL or use_rest()) else "sqlite"


def use_rest() -> bool:
    """True when the portal should talk to Supabase over HTTPS (the web API) instead of a direct database connection."""
    return bool(config.SUPABASE_URL and config.SUPABASE_SERVICE_KEY)


def pg_schema(*, with_revoke: bool = False) -> str:
    """The same tables for Postgres. Row Level Security is switched ON for every table and no policy is created, so
    Supabase's public REST API (anon / authenticated keys) can read or write NOTHING; only this server, connecting
    with the database password, can. `with_revoke` also removes the Supabase API roles' table privileges (the SQL
    file you paste into the Supabase SQL editor uses it)."""
    ddl = SCHEMA.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    tables = re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", SCHEMA)
    out = [ddl] + [f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;" for t in tables]
    if with_revoke:
        out += ["REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;",
                "REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;"]
    return "\n".join(out)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_conn(path: str | None = None):
    """A connection with sqlite3-like methods. An explicit `path` always means SQLite (used by tools and tests)."""
    if path is None and use_rest():
        return pgcompat.connect_rest(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
    if path is None and config.DATABASE_URL:
        return pgcompat.connect(config.DATABASE_URL)
    conn = sqlite3.connect(path or config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _ensure_columns(conn) -> None:
    """Add any column missing from an older SQLite file."""
    have = {r["name"] for r in conn.execute("PRAGMA table_info(candidates)")}
    for col, decl in CANDIDATE_FIELDS:
        if col not in have:
            conn.execute(f"ALTER TABLE candidates ADD COLUMN {col} {decl}")
    have = {r["name"] for r in conn.execute("PRAGMA table_info(escalations)")}
    for col, decl in (("channel", "TEXT NOT NULL DEFAULT 'web'"), ("contact", "TEXT NOT NULL DEFAULT ''")):
        if col not in have:
            conn.execute(f"ALTER TABLE escalations ADD COLUMN {col} {decl}")


def _prepare_postgres(conn) -> None:
    """Create the tables (if missing), switch on Row Level Security and close the Supabase API roles out.
    A lock makes several workers starting at once take turns. SKIP_SCHEMA_SETUP=true skips this when you created
    the tables yourself with supabase/schema.sql."""
    if getattr(conn, "rest", False):
        # Over the web API the tables are made by supabase/schema.sql (the SQL editor); here we only check they are there.
        try:
            conn.execute("SELECT 1 FROM candidates LIMIT 1")
            conn.execute("SELECT 1 FROM usage_events LIMIT 1")
        except RuntimeError as exc:
            if "does not exist" in str(exc) and not str(exc).startswith("The database function"):
                raise RuntimeError("The tables are missing in Supabase. Paste supabase/schema.sql into the Supabase SQL "
                                   f"editor and Run it, then start the portal again. ({exc})") from exc
            raise
        return
    conn.execute("SELECT pg_advisory_xact_lock(727274)")        # released at commit
    if config.env_bool("SKIP_SCHEMA_SETUP"):
        return
    conn.executescript(pg_schema())
    have = {r["column_name"] for r in conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() "
        "AND table_name = 'candidates'")}
    for col, decl in CANDIDATE_FIELDS:
        if col not in have:
            conn.execute(f"ALTER TABLE candidates ADD COLUMN IF NOT EXISTS {col} {decl}")
    for col, decl in (("channel", "TEXT NOT NULL DEFAULT 'web'"), ("contact", "TEXT NOT NULL DEFAULT ''")):
        conn.execute(f"ALTER TABLE escalations ADD COLUMN IF NOT EXISTS {col} {decl}")
    roles = {r["rolname"] for r in conn.execute("SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')")}
    for role in sorted(roles):                                   # only exist on Supabase
        conn.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {role}")
        conn.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {role}")


def init_db(path: str | None = None) -> None:
    """Create tables and seed default positions, settings and FAQ on first run."""
    conn = get_conn(path)
    try:
        if getattr(conn, "backend", "sqlite") == "postgres":
            _prepare_postgres(conn)
        else:
            conn.executescript(SCHEMA)
            _ensure_columns(conn)
        existing = {r["name"] for r in conn.execute("SELECT name FROM positions")}
        if not existing:
            for p in config.DEFAULT_POSITIONS:
                upsert_position(conn, p)
        elif config.INTERN_POSITION not in existing and "Research Fellow" in existing:
            # Upgrading a database created before the Intern option existed.
            intern = next(p for p in config.DEFAULT_POSITIONS if p["name"] == config.INTERN_POSITION)
            upsert_position(conn, intern)
        for k, v in config.DEFAULT_SETTINGS.items():
            conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))
        if conn.execute("SELECT COUNT(*) FROM faq").fetchone()[0] == 0:
            for i, (q, a, kw) in enumerate(config.DEFAULT_FAQ, start=1):
                conn.execute("INSERT INTO faq(question, answer, keywords, sort_order) VALUES (?, ?, ?, ?)",
                             (q, a, kw, i))
        purge_usage(conn)
        conn.commit()
    finally:
        conn.close()


# --- positions / settings -----------------------------------------------------
def list_positions(conn) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM positions ORDER BY name")]


def get_position(conn, name: str) -> dict | None:
    r = conn.execute("SELECT * FROM positions WHERE name = ?", (name,)).fetchone()
    return dict(r) if r else None


def upsert_position(conn, p: dict) -> None:
    conn.execute(
        """INSERT INTO positions(name, min_years, min_education, required_keywords,
                                 preferred_keywords, w_exp, w_edu, w_req, w_pref)
           VALUES (:name, :min_years, :min_education, :required_keywords,
                   :preferred_keywords, :w_exp, :w_edu, :w_req, :w_pref)
           ON CONFLICT(name) DO UPDATE SET
             min_years=excluded.min_years, min_education=excluded.min_education,
             required_keywords=excluded.required_keywords,
             preferred_keywords=excluded.preferred_keywords,
             w_exp=excluded.w_exp, w_edu=excluded.w_edu,
             w_req=excluded.w_req, w_pref=excluded.w_pref""", p)
    conn.commit()


def delete_position(conn, name: str) -> None:
    conn.execute("DELETE FROM positions WHERE name = ?", (name,))
    conn.commit()


def get_settings(conn) -> dict:
    out = dict(config.DEFAULT_SETTINGS)
    for r in conn.execute("SELECT key, value FROM settings WHERE key != 'secret_key'"):
        out[r["key"]] = r["value"]
    return out


def set_setting(conn, key: str, value: str) -> None:
    conn.execute("INSERT INTO settings(key, value) VALUES (?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
    conn.commit()


# --- candidates -----------------------------------------------------------------
def add_candidate(conn, **fields) -> int:
    data = {k: ("" if v is None else str(v)) for k, v in fields.items() if k in CANDIDATE_COLUMNS}
    ts = now_iso()
    data.setdefault("stage", "Applied")
    data["stage_updated_at"] = ts
    cols = list(data)
    cur = conn.execute(
        f"INSERT INTO candidates({', '.join(cols)}, created_at) VALUES ({', '.join('?' for _ in cols)}, ?)",
        [data[c] for c in cols] + [ts])
    conn.commit()
    return cur.lastrowid


def get_candidate(conn, candidate_id: int) -> dict | None:
    r = conn.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,)).fetchone()
    return dict(r) if r else None


def update_candidate(conn, candidate_id: int, **fields) -> None:
    data = {k: ("" if v is None else str(v)) for k, v in fields.items() if k in CANDIDATE_COLUMNS}
    if not data:
        return
    if "stage" in data:
        data["stage_updated_at"] = now_iso()
    conn.execute(f"UPDATE candidates SET {', '.join(f'{k} = ?' for k in data)} WHERE id = ?",
                 list(data.values()) + [candidate_id])
    conn.commit()


def add_screening(conn, candidate_id: int, position: str, result: dict) -> int:
    cur = conn.execute(
        """INSERT INTO screenings(candidate_id, position, score, status, notes, breakdown, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (candidate_id, position, result["score"], result["status"], result["notes"],
         json.dumps(result), now_iso()))
    conn.commit()
    return cur.lastrowid


_LATEST_SQL = """
  SELECT s.id AS screening_id, s.candidate_id, c.name, c.email, c.phone, c.location,
         c.stage, c.preferred_department, c.highest_qualification, c.shortlist_email_sent_at,
         c.created_at AS applied_at, s.position, s.score, s.status, s.notes,
         s.created_at AS screened_at, s.created_at,
         (SELECT CAST(ROUND(AVG(overall_rating), 1) AS REAL) FROM interviews i WHERE i.candidate_id = c.id) AS avg_rating,
         (SELECT COUNT(*) FROM interviews i WHERE i.candidate_id = c.id) AS interview_count,
         (SELECT COUNT(*) FROM interviews i WHERE i.candidate_id = c.id AND i.recommendation = 'Yes') AS rec_yes,
         (SELECT COUNT(*) FROM interviews i WHERE i.candidate_id = c.id AND i.recommendation = 'Maybe') AS rec_maybe,
         (SELECT COUNT(*) FROM interviews i WHERE i.candidate_id = c.id AND i.recommendation = 'No') AS rec_no
  FROM screenings s
  JOIN candidates c ON c.id = s.candidate_id
  WHERE s.id = (SELECT MAX(id) FROM screenings WHERE candidate_id = s.candidate_id)
"""


def latest_screenings(conn, *, status=None, position=None, stage=None, search=None) -> list[dict]:
    """One row per candidate (their most recent screening), newest first."""
    sql, params = _LATEST_SQL, []  # type: str, list[Any]
    if status:
        sql += " AND s.status = ?"
        params.append(status)
    if position:
        sql += " AND s.position = ?"
        params.append(position)
    if stage:
        sql += " AND c.stage = ?"
        params.append(stage)
    if search:
        sql += " AND (LOWER(c.name) LIKE LOWER(?) OR LOWER(c.email) LIKE LOWER(?))"
        params += [f"%{search}%", f"%{search}%"]
    sql += " ORDER BY s.id DESC"
    return [dict(r) for r in conn.execute(sql, params)]


def screening_history(conn, candidate_id: int) -> list[dict]:
    out = []
    for r in conn.execute("SELECT * FROM screenings WHERE candidate_id = ? ORDER BY id DESC", (candidate_id,)):
        d = dict(r)
        d["breakdown"] = json.loads(d["breakdown"])
        out.append(d)
    return out


def status_counts(conn) -> dict:
    counts = {"Pass": 0, "Needs Review": 0, "Reject": 0}
    for r in latest_screenings(conn):
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return counts


def stage_counts(conn) -> dict:
    counts = {s: 0 for s in config.STAGES}
    for r in conn.execute("SELECT stage, COUNT(*) AS n FROM candidates GROUP BY stage"):
        counts[r["stage"]] = r["n"]
    return counts


# --- interviews ---------------------------------------------------------------------
def add_interview(conn, candidate_id: int, d: dict) -> int:
    cur = conn.execute(
        """INSERT INTO interviews(candidate_id, interviewer, interview_date, skills_rating,
               communication_rating, culture_rating, overall_rating, recommendation, notes, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (candidate_id, d["interviewer"], d.get("interview_date", ""), d["skills_rating"],
         d["communication_rating"], d["culture_rating"], d["overall_rating"], d["recommendation"],
         d.get("notes", ""), now_iso()))
    conn.commit()
    return cur.lastrowid


def list_interviews(conn, candidate_id: int | None = None) -> list[dict]:
    if candidate_id is None:
        rows = conn.execute("""SELECT i.*, c.name AS candidate_name, c.position
                               FROM interviews i JOIN candidates c ON c.id = i.candidate_id
                               ORDER BY i.id DESC""")
    else:
        rows = conn.execute("""SELECT i.*, c.name AS candidate_name, c.position
                               FROM interviews i JOIN candidates c ON c.id = i.candidate_id
                               WHERE i.candidate_id = ? ORDER BY i.id DESC""", (candidate_id,))
    return [dict(r) for r in rows]


def delete_interview(conn, interview_id: int) -> None:
    conn.execute("DELETE FROM interviews WHERE id = ?", (interview_id,))
    conn.commit()


# --- interns --------------------------------------------------------------------------
def get_intern(conn, intern_id: int) -> dict | None:
    r = conn.execute("""SELECT n.*, c.name, c.email, c.phone, c.stage, c.preferred_department
                        FROM interns n JOIN candidates c ON c.id = n.candidate_id WHERE n.id = ?""",
                     (intern_id,)).fetchone()
    return dict(r) if r else None


def get_intern_by_candidate(conn, candidate_id: int) -> dict | None:
    r = conn.execute("SELECT id FROM interns WHERE candidate_id = ?", (candidate_id,)).fetchone()
    return get_intern(conn, r["id"]) if r else None


def get_intern_by_token(conn, token: str) -> dict | None:
    r = conn.execute("SELECT id FROM interns WHERE token = ?", (token,)).fetchone()
    return get_intern(conn, r["id"]) if r else None


def list_interns(conn) -> list[dict]:
    rows = conn.execute("""SELECT n.*, c.name, c.email, c.stage,
                             (SELECT COUNT(*) FROM intern_updates u WHERE u.intern_id = n.id) AS update_count,
                             (SELECT COUNT(*) FROM intern_courses k WHERE k.intern_id = n.id) AS course_count
                           FROM interns n JOIN candidates c ON c.id = n.candidate_id
                           ORDER BY n.department, c.name""")
    return [dict(r) for r in rows]


def upsert_intern(conn, candidate_id: int, department: str, supervisor: str, start_date: str) -> tuple[int, bool]:
    """Create or update an intern placement. Returns (intern_id, created)."""
    row = conn.execute("SELECT id FROM interns WHERE candidate_id = ?", (candidate_id,)).fetchone()
    if row:
        conn.execute("UPDATE interns SET department = ?, supervisor = ?, start_date = ? WHERE id = ?",
                     (department, supervisor, start_date, row["id"]))
        conn.commit()
        return row["id"], False
    cur = conn.execute(
        "INSERT INTO interns(candidate_id, department, supervisor, start_date, token, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (candidate_id, department, supervisor, start_date, secrets.token_urlsafe(24), now_iso()))
    conn.commit()
    return cur.lastrowid, True


def add_intern_update(conn, intern_id: int, message: str, author: str) -> None:
    conn.execute("INSERT INTO intern_updates(intern_id, message, author, created_at) VALUES (?, ?, ?, ?)",
                 (intern_id, message, author, now_iso()))
    conn.commit()


def list_intern_updates(conn, intern_id: int) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM intern_updates WHERE intern_id = ? ORDER BY id DESC", (intern_id,))]


def delete_intern_update(conn, update_id: int) -> None:
    conn.execute("DELETE FROM intern_updates WHERE id = ?", (update_id,))
    conn.commit()


def add_intern_course(conn, intern_id: int, title: str, provider: str = "", link: str = "", note: str = "") -> None:
    conn.execute("INSERT INTO intern_courses(intern_id, title, provider, link, note, created_at) "
                 "VALUES (?, ?, ?, ?, ?, ?)", (intern_id, title, provider, link, note, now_iso()))
    conn.commit()


def list_intern_courses(conn, intern_id: int) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM intern_courses WHERE intern_id = ? ORDER BY id", (intern_id,))]


def delete_intern_course(conn, course_id: int) -> None:
    conn.execute("DELETE FROM intern_courses WHERE id = ?", (course_id,))
    conn.commit()


# --- FAQ chatbot ------------------------------------------------------------------------
def list_faq(conn) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM faq ORDER BY sort_order, id")]


def save_faq(conn, faq_id: int | None, question: str, answer: str, keywords: str, sort_order: int) -> None:
    if faq_id:
        conn.execute("UPDATE faq SET question = ?, answer = ?, keywords = ?, sort_order = ? WHERE id = ?",
                     (question, answer, keywords, sort_order, faq_id))
    else:
        conn.execute("INSERT INTO faq(question, answer, keywords, sort_order) VALUES (?, ?, ?, ?)",
                     (question, answer, keywords, sort_order))
    conn.commit()


def delete_faq(conn, faq_id: int) -> None:
    conn.execute("DELETE FROM faq WHERE id = ?", (faq_id,))
    conn.commit()


def log_chat(conn, question: str, matched: bool) -> None:
    conn.execute("INSERT INTO chat_log(question, matched, created_at) VALUES (?, ?, ?)",
                 (question[:300], 1 if matched else 0, now_iso()))
    conn.commit()


def unanswered_chats(conn, limit: int = 25) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT MIN(question) AS question, COUNT(*) AS times, MAX(created_at) AS last_asked FROM chat_log "
        "WHERE matched = 0 GROUP BY lower(question) ORDER BY last_asked DESC LIMIT ?", (limit,))]


# --- human escalation (chatbot -> recruiter) ----------------------------------------------
def add_escalation(conn, name: str, email: str, message: str, channel: str = "web", contact: str = "") -> int:
    cur = conn.execute("INSERT INTO escalations(name, email, message, created_at, channel, contact) "
                       "VALUES (?, ?, ?, ?, ?, ?)", (name, email, message, now_iso(), channel, contact))
    conn.commit()
    return cur.lastrowid


def list_escalations(conn, status: str | None = None) -> list[dict]:
    sql, params = "SELECT * FROM escalations", []
    if status:
        sql += " WHERE status = ?"
        params.append(status)
    return [dict(r) for r in conn.execute(sql + " ORDER BY id DESC", params)]


def resolve_escalation(conn, escalation_id: int, note: str) -> None:
    conn.execute("UPDATE escalations SET status = 'Resolved', note = ?, resolved_at = ? WHERE id = ?",
                 (note, now_iso(), escalation_id))
    conn.commit()


def count_open_escalations(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM escalations WHERE status = 'Open'").fetchone()[0]


# --- integrations log ---------------------------------------------------------------------
def log_integration(conn, *, candidate_id=None, screening_id=None, service, action,
                    success: bool, status_code=None, detail="") -> None:
    conn.execute(
        """INSERT INTO integrations_log(candidate_id, screening_id, service, action,
                                        success, status_code, detail, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (candidate_id, screening_id, service, action, 1 if success else 0,
         status_code, (detail or "")[:1000], now_iso()))
    conn.commit()


def last_success(conn, candidate_id: int, actions) -> dict | None:
    """The newest SUCCESSFUL integrations_log row of this candidate for any of these events (or None)."""
    actions = list(actions)
    marks = ", ".join("?" for _ in actions)
    r = conn.execute(f"SELECT * FROM integrations_log WHERE candidate_id = ? AND success = 1 AND action IN ({marks}) "
                     f"ORDER BY id DESC LIMIT 1", [candidate_id] + actions).fetchone()
    return dict(r) if r else None


def recent_integration_logs(conn, limit: int = 100, candidate_id: int | None = None) -> list[dict]:
    if candidate_id is not None:
        rows = conn.execute("SELECT * FROM integrations_log WHERE candidate_id = ? ORDER BY id DESC LIMIT ?",
                            (candidate_id, limit))
    else:
        rows = conn.execute("SELECT * FROM integrations_log ORDER BY id DESC LIMIT ?", (limit,))
    return [dict(r) for r in rows]


# --- chat sessions (WhatsApp / API hand-off conversation) ---------------------------------
def get_bot_session(conn, channel: str, user_id: str) -> dict:
    row = conn.execute("SELECT state, data, updated_at FROM bot_sessions WHERE channel = ? AND user_id = ?",
                       (channel, user_id)).fetchone()
    if not row:
        return {"state": "idle", "data": {}, "updated_at": ""}
    try:
        data = json.loads(row["data"] or "{}")
    except ValueError:
        data = {}
    return {"state": row["state"], "data": data, "updated_at": row["updated_at"]}


def save_bot_session(conn, channel: str, user_id: str, state: str, data: dict) -> None:
    conn.execute("INSERT INTO bot_sessions(channel, user_id, state, data, updated_at) VALUES (?, ?, ?, ?, ?) "
                 "ON CONFLICT(channel, user_id) DO UPDATE SET state = excluded.state, data = excluded.data, "
                 "updated_at = excluded.updated_at", (channel, user_id, state, json.dumps(data), now_iso()))
    conn.commit()


def first_time_seen(conn, message_id: str) -> bool:
    """True the first time a message id is seen (and remembers it), False for a duplicate delivery.
    Ids older than 7 days are forgotten."""
    cur = conn.execute("INSERT OR IGNORE INTO bot_seen(message_id, created_at) VALUES (?, ?)", (message_id, now_iso()))
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(timespec="seconds")
    conn.execute("DELETE FROM bot_seen WHERE created_at < ?", (cutoff,))
    conn.commit()
    return cur.rowcount == 1


# --- website usage ------------------------------------------------------------------------
USAGE_COLUMNS = ("day", "event", "path", "status", "visitor", "device", "browser", "referrer", "channel", "detail")


def add_usage_event(conn, **fields) -> None:
    data = {k: fields.get(k, "") for k in USAGE_COLUMNS}
    data["day"] = data["day"] or now_iso()[:10]
    data["status"] = fields.get("status")
    conn.execute(f"INSERT INTO usage_events(created_at, {', '.join(USAGE_COLUMNS)}) "
                 f"VALUES (?, {', '.join('?' for _ in USAGE_COLUMNS)})",
                 [now_iso()] + [data[c] for c in USAGE_COLUMNS])
    conn.commit()


def purge_usage(conn) -> None:
    """Forget usage events older than USAGE_RETENTION_DAYS (default 400)."""
    try:
        days = int(config.env("USAGE_RETENTION_DAYS", "400"))
    except ValueError:
        days = 400
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    conn.execute("DELETE FROM usage_events WHERE created_at < ?", (cutoff,))
