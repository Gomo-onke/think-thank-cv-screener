"""Use Postgres (Supabase) through the same small interface the portal already uses with SQLite.

The portal's SQL was written for sqlite3 (`?` placeholders, rows you can read by name or number, `cursor.lastrowid`,
`INSERT OR IGNORE`). This module wraps a Postgres connection so that code keeps working unchanged:

    conn = pgcompat.connect(database_url)
    conn.execute("SELECT * FROM faq WHERE id = ?", (3,)).fetchone()["question"]

What it does for each statement:
    ?            -> %s                      (and :name -> %(name)s when parameters are a dict)
    INSERT OR IGNORE INTO ...  -> INSERT INTO ... ON CONFLICT DO NOTHING
    INSERT INTO <table with an id column> ...  -> ... RETURNING id, so `cursor.lastrowid` works
    rows         -> Row (a dict that can also be indexed by position, like sqlite3.Row)
    any error    -> rollback first (Postgres refuses further statements in a failed transaction, SQLite does not)

A second way to reach the same database: `connect_rest(url, key)` talks to Supabase over HTTPS (the web API) by calling
one database function, portal_sql (created by supabase/schema.sql), which runs the statement. Use it where the database
port is blocked. Each statement is then its own transaction (commit/rollback do nothing).

The actual database driver is `psycopg` (pip install "psycopg[binary]"). It is imported only when a Postgres
connection is made, so nothing changes for people who keep using SQLite. `set_driver()` lets tests plug in another
driver with the same four methods (run, commit, rollback, close).
"""
from __future__ import annotations

import re
from typing import Any, Callable

# Tables whose primary key is a SERIAL column called id (INSERTs into them return it as cursor.lastrowid).
ID_TABLES = frozenset({"candidates", "screenings", "interviews", "interns", "intern_updates", "intern_courses",
                       "faq", "chat_log", "escalations", "integrations_log", "usage_events"})

_NAMED = re.compile(r"(?<![:\w]):([A-Za-z_]\w*)")
_INSERT = re.compile(r"^\s*INSERT\s+(OR\s+IGNORE\s+)?INTO\s+([A-Za-z_]\w*)", re.IGNORECASE)


class Row(dict):
    """A result row: row["name"] and row[0] both work, and dict(row) works (like sqlite3.Row)."""
    __slots__ = ()

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


def translate(sql: str, params: Any) -> tuple[str, Any, bool]:
    """Turn one SQLite-style statement into Postgres/psycopg style. Returns (sql, params, wants_id)."""
    wants_id = False
    m = _INSERT.match(sql)
    if m:
        body = sql.rstrip().rstrip(";")
        if m.group(1):                                             # INSERT OR IGNORE INTO t ... -> ... ON CONFLICT DO NOTHING
            body = re.sub(r"^(\s*INSERT)\s+OR\s+IGNORE\s+(INTO)", r"\1 \2", body, count=1, flags=re.IGNORECASE)
            body += " ON CONFLICT DO NOTHING"
        elif m.group(2).lower() in ID_TABLES and "returning" not in body.lower():
            body += " RETURNING id"
            wants_id = True
        sql = body
    if params is None or (not isinstance(params, dict) and len(params) == 0):
        return sql, None, wants_id                                 # no parameters: leave the text exactly as written
    sql = sql.replace("%", "%%")                                   # a literal % must be doubled once parameters are used
    if isinstance(params, dict):
        sql = _NAMED.sub(lambda mo: f"%({mo.group(1)})s", sql)
        return sql, params, wants_id
    return sql.replace("?", "%s"), tuple(params), wants_id


class Cursor:
    def __init__(self, rows: list[dict], rowcount: int, lastrowid: int | None):
        self._rows = [Row(r) for r in rows]
        self._i = 0
        self.rowcount = rowcount
        self.lastrowid = lastrowid

    def fetchone(self):
        if self._i >= len(self._rows):
            return None
        self._i += 1
        return self._rows[self._i - 1]

    def fetchall(self):
        rest, self._i = self._rows[self._i:], len(self._rows)
        return rest

    def __iter__(self):
        return iter(self.fetchall())


class Connection:
    """The sqlite3.Connection methods the portal uses: execute, executescript, commit, rollback, close."""
    backend = "postgres"

    def __init__(self, raw):
        self.raw = raw

    def execute(self, sql: str, params: Any = None) -> Cursor:
        sql, params, wants_id = translate(sql, params)
        try:
            rows, rowcount = self.raw.run(sql, params)
        except Exception:
            self.raw.rollback()
            raise
        lastrowid = None
        if wants_id:
            lastrowid = rows[0]["id"] if rows else None
            rows = []
        return Cursor(rows, rowcount, lastrowid)

    def executescript(self, script: str) -> None:
        """Run several statements separated by semicolons (comments allowed, no semicolons inside strings)."""
        for statement in _split_script(script):
            self.execute(statement)

    def commit(self) -> None:
        self.raw.commit()

    def rollback(self) -> None:
        self.raw.rollback()

    def close(self) -> None:
        try:
            self.raw.rollback()
        finally:
            self.raw.close()


def _split_script(script: str) -> list[str]:
    no_comments = "\n".join(line.split("--", 1)[0] for line in script.splitlines())
    return [s.strip() for s in no_comments.split(";") if s.strip()]


# ---------------------------------------------------------------------------------------------- drivers
class PsycopgRaw:
    """The real driver: psycopg 3. `prepare_threshold=None` because Supabase's connection pooler (transaction mode)
    does not support server-side prepared statements."""

    def __init__(self, url: str):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - exercised only on a machine without psycopg
            raise RuntimeError('DATABASE_URL is set, so the Postgres driver is needed:  pip install "psycopg[binary]"') from exc
        self.conn = psycopg.connect(url, row_factory=dict_row, prepare_threshold=None, connect_timeout=10)

    def run(self, sql: str, params):
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall() if cur.description else []
            return rows, cur.rowcount

    def commit(self) -> None:
        self.conn.commit()

    def rollback(self) -> None:
        self.conn.rollback()

    def close(self) -> None:
        self.conn.close()


_driver: Callable[[str], Any] = PsycopgRaw


def set_driver(factory: Callable[[str], Any] | None) -> None:
    """Replace the database driver (used by the tests); None restores psycopg."""
    global _driver
    _driver = factory or PsycopgRaw


def connect(url: str) -> Connection:
    return Connection(_driver(url))


# ----------------------------------------------------------------------------------------- Supabase over HTTPS
_TOKEN = re.compile(r"%%|%s|%\((\w+)\)s")


def dollar(sql: str, params) -> tuple[str, list]:
    """psycopg-style placeholders (%s, %(name)s, %%) -> $1, $2 ... and the values in that order."""
    values: list = []
    names: dict = {}

    def sub(m):
        tok = m.group(0)
        if tok == "%%":
            return "%"
        if m.group(1):
            if m.group(1) not in names:
                values.append(params[m.group(1)])
                names[m.group(1)] = len(values)
            return f"${names[m.group(1)]}"
        values.append(params[len(values)])
        return f"${len(values)}"

    return _TOKEN.sub(sub, sql), values


def _mode(sql: str) -> str:
    s = sql.lstrip(" \t\r\n(").lower()
    if s.startswith(("select", "with")):
        return "rows"
    if re.search(r"\breturning\b", s):
        return "returning"
    return "exec"


class RestRaw:
    """Same four methods as PsycopgRaw, but over HTTPS: POST {url}/rest/v1/rpc/portal_sql with the secret key."""
    rest = True

    def __init__(self, url: str, key: str):
        import requests
        self.url = url.rstrip("/") + "/rest/v1/rpc/portal_sql"
        self.session = _rest_session() if _rest_session else requests.Session()
        headers = {"apikey": key, "Content-Type": "application/json"}
        if not key.startswith("sb_"):                    # a legacy JWT key is also sent as the bearer token
            headers["Authorization"] = f"Bearer {key}"
        self.headers = headers

    def run(self, sql: str, params):
        if params is None:
            values = []
        else:
            sql, values = dollar(sql, params)
        body = {"q": sql, "args": values, "mode": _mode(sql)}
        try:
            r = self.session.post(self.url, json=body, headers=self.headers, timeout=30)
        except Exception as exc:  # noqa: BLE001 - requests' own errors, or a test transport's
            raise RuntimeError(f"Could not reach Supabase over HTTPS ({type(exc).__name__}: {exc}). "
                               "Check SUPABASE_URL and your internet connection.") from exc
        if r.status_code >= 400:
            try:
                info = r.json()
            except ValueError:
                info = {}
            msg = info.get("message") or r.text[:300]
            if info.get("code") == "PGRST202" or r.status_code == 404:
                msg = ("The database function portal_sql does not exist (or the URL is wrong). Run supabase/schema.sql in the "
                       "Supabase SQL editor. Details: " + msg)
            elif r.status_code in (401, 403):
                msg = "Supabase refused the key. Use the service_role (secret) key, not the anon/public key. " + msg
            raise RuntimeError(msg)
        data = r.json()
        return data.get("rows") or [], int(data.get("rowcount") or 0)

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        self.session.close()


_rest_session: Callable[[], Any] | None = None


def set_rest_session(factory: Callable[[], Any] | None) -> None:
    """Replace the HTTP session (used by the tests)."""
    global _rest_session
    _rest_session = factory


def connect_rest(url: str, key: str) -> Connection:
    conn = Connection(RestRaw(url, key))
    conn.rest = True
    return conn


# The database function the web API calls. Only the service_role key may run it (everyone else is revoked).
# Values are substituted on the server with quote_literal, in one pass over the statement, so a value can never
# be mistaken for SQL or for another placeholder.
REST_SETUP_SQL = r"""-- Lets the portal run its SQL over Supabase's HTTPS API (used when the database port is blocked).
CREATE OR REPLACE FUNCTION public.portal_sql(q text, args jsonb DEFAULT '[]'::jsonb, mode text DEFAULT 'exec')
RETURNS json
LANGUAGE plpgsql
SET search_path = public
AS $fn$
DECLARE
  sql text := '';
  piece text[];
  v jsonb;
  res json;
  n bigint := 0;
BEGIN
  FOR piece IN SELECT regexp_matches(q, '(\$[0-9]+)|([^$]+)|(\$)', 'g') LOOP
    IF piece[1] IS NOT NULL THEN
      v := args -> (substr(piece[1], 2)::int - 1);
      sql := sql || CASE
        WHEN v IS NULL OR jsonb_typeof(v) = 'null' THEN 'NULL'
        WHEN jsonb_typeof(v) = 'number' THEN '(' || (v #>> '{}') || ')'
        WHEN jsonb_typeof(v) = 'boolean' THEN (v #>> '{}')
        ELSE quote_literal(v #>> '{}') END;
    ELSE
      sql := sql || coalesce(piece[2], piece[3]);
    END IF;
  END LOOP;
  sql := regexp_replace(sql, ';\s*$', '');
  IF mode = 'rows' THEN
    EXECUTE format('SELECT coalesce(json_agg(row_to_json(portal_q)), ''[]''::json) FROM (%s) portal_q', sql) INTO res;
    RETURN json_build_object('rows', res, 'rowcount', json_array_length(res));
  ELSIF mode = 'returning' THEN
    EXECUTE format('WITH portal_q AS (%s) SELECT coalesce(json_agg(row_to_json(portal_q)), ''[]''::json) FROM portal_q', sql) INTO res;
    RETURN json_build_object('rows', res, 'rowcount', json_array_length(res));
  END IF;
  EXECUTE sql;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN json_build_object('rows', '[]'::json, 'rowcount', n);
END
$fn$;

REVOKE ALL ON FUNCTION public.portal_sql(text, jsonb, text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.portal_sql(text, jsonb, text) TO service_role;
"""
