"""Test-only helpers: run the whole test suite against a REAL Postgres server (the same engine Supabase uses).

    TEST_POSTGRES=1 python -m unittest discover -s tests

It needs the Postgres server programs (initdb, pg_ctl) and the libpq library on this computer (on Ubuntu/Debian:
`apt install postgresql`). It starts a throw-away server on a temporary folder, and talks to it through libpq with a
tiny driver written here, so it does not need the psycopg package. Without TEST_POSTGRES the tests use SQLite as before.

Fidelity notes: like psycopg, the driver sends Python ints as integer types, floats as float8, strings as untyped
text, and starts a transaction on the first statement, so type mistakes that psycopg would reject are rejected here too.
"""
from __future__ import annotations

import atexit
import ctypes
import glob
import os
import re
import shutil
import subprocess
import tempfile
from decimal import Decimal

PORT = 54329
_server: dict = {}


# ----------------------------------------------------------------------------------------- the driver
def _load_libpq():
    for name in ("libpq.so.5", "libpq.so", "libpq.5.dylib", "libpq.dll"):
        try:
            return ctypes.CDLL(name)
        except OSError:
            continue
    return None


_lib = _load_libpq()
if _lib is not None:
    P = ctypes.c_void_p
    _lib.PQconnectdb.restype, _lib.PQconnectdb.argtypes = P, [ctypes.c_char_p]
    _lib.PQstatus.restype, _lib.PQstatus.argtypes = ctypes.c_int, [P]
    _lib.PQerrorMessage.restype, _lib.PQerrorMessage.argtypes = ctypes.c_char_p, [P]
    _lib.PQfinish.restype, _lib.PQfinish.argtypes = None, [P]
    _lib.PQexec.restype, _lib.PQexec.argtypes = P, [P, ctypes.c_char_p]
    _lib.PQexecParams.restype = P
    _lib.PQexecParams.argtypes = [P, ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(ctypes.c_uint),
                                  ctypes.POINTER(ctypes.c_char_p), ctypes.POINTER(ctypes.c_int),
                                  ctypes.POINTER(ctypes.c_int), ctypes.c_int]
    _lib.PQresultStatus.restype, _lib.PQresultStatus.argtypes = ctypes.c_int, [P]
    _lib.PQresultErrorMessage.restype, _lib.PQresultErrorMessage.argtypes = ctypes.c_char_p, [P]
    _lib.PQclear.restype, _lib.PQclear.argtypes = None, [P]
    _lib.PQntuples.restype, _lib.PQntuples.argtypes = ctypes.c_int, [P]
    _lib.PQnfields.restype, _lib.PQnfields.argtypes = ctypes.c_int, [P]
    _lib.PQfname.restype, _lib.PQfname.argtypes = ctypes.c_char_p, [P, ctypes.c_int]
    _lib.PQftype.restype, _lib.PQftype.argtypes = ctypes.c_uint, [P, ctypes.c_int]
    _lib.PQgetvalue.restype, _lib.PQgetvalue.argtypes = ctypes.c_char_p, [P, ctypes.c_int, ctypes.c_int]
    _lib.PQgetisnull.restype, _lib.PQgetisnull.argtypes = ctypes.c_int, [P, ctypes.c_int, ctypes.c_int]
    _lib.PQcmdTuples.restype, _lib.PQcmdTuples.argtypes = ctypes.c_char_p, [P]

_TOKEN = re.compile(r"%%|%s|%\((\w+)\)s")


class PgError(Exception):
    pass


def _dollar(sql: str, params):
    """%s / %(name)s placeholders (psycopg style) -> $1, $2 ... and the list of values in that order."""
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


def _encode(v):
    """-> (text value or None, type oid) the way psycopg sends it."""
    if v is None:
        return None, 0
    if isinstance(v, bool):
        return ("t" if v else "f"), 16
    if isinstance(v, int):
        return str(v), (21 if -2**15 <= v < 2**15 else 23 if -2**31 <= v < 2**31 else 20)
    if isinstance(v, float):
        return repr(v), 701
    return str(v), 0


def _decode(text: str | None, oid: int):
    if text is None:
        return None
    if oid == 16:
        return text == "t"
    if oid in (20, 21, 23, 26):
        return int(text)
    if oid in (700, 701):
        return float(text)
    if oid == 1700:
        return Decimal(text)
    return text


class LibpqRaw:
    """Same four methods as pgcompat.PsycopgRaw (run, commit, rollback, close)."""

    def __init__(self, conninfo: str):
        if _lib is None:
            raise RuntimeError("libpq is not installed")
        self.c = _lib.PQconnectdb((conninfo + " client_encoding=UTF8").encode())
        if _lib.PQstatus(self.c) != 0:
            raise PgError(_lib.PQerrorMessage(self.c).decode(errors="replace"))
        self.in_tx = False

    def _exec(self, sql: str):
        res = _lib.PQexec(self.c, sql.encode())
        status = _lib.PQresultStatus(res)
        if status not in (1, 2):
            msg = _lib.PQresultErrorMessage(res).decode(errors="replace")
            _lib.PQclear(res)
            raise PgError(msg.strip())
        _lib.PQclear(res)

    def run(self, sql: str, params):
        if not self.in_tx:
            self._exec("BEGIN")
            self.in_tx = True
        if params is None:
            res = _lib.PQexec(self.c, sql.encode())
        else:
            text_sql, values = _dollar(sql, params)
            enc = [_encode(v) for v in values]
            n = len(enc)
            types = (ctypes.c_uint * n)(*[t for _v, t in enc])
            vals = (ctypes.c_char_p * n)(*[None if v is None else v.encode() for v, _t in enc])
            res = _lib.PQexecParams(self.c, text_sql.encode(), n, types, vals, None, None, 0)
        status = _lib.PQresultStatus(res)
        try:
            if status not in (1, 2):                      # COMMAND_OK, TUPLES_OK
                raise PgError(_lib.PQresultErrorMessage(res).decode(errors="replace").strip())
            rows = []
            if status == 2:
                names = [_lib.PQfname(res, j).decode() for j in range(_lib.PQnfields(res))]
                oids = [_lib.PQftype(res, j) for j in range(len(names))]
                for i in range(_lib.PQntuples(res)):
                    row = {}
                    for j, name in enumerate(names):
                        text = None if _lib.PQgetisnull(res, i, j) else _lib.PQgetvalue(res, i, j).decode()
                        row[name] = _decode(text, oids[j])
                    rows.append(row)
            tuples = _lib.PQcmdTuples(res)
            rowcount = int(tuples) if tuples else len(rows)
            return rows, rowcount
        finally:
            _lib.PQclear(res)

    def commit(self):
        if self.in_tx:
            self.in_tx = False
            self._exec("COMMIT")

    def rollback(self):
        if self.in_tx:
            self.in_tx = False
            self._exec("ROLLBACK")

    def close(self):
        _lib.PQfinish(self.c)


# ----------------------------------------------------------------------------------------- the server
def _bin(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    hits = sorted(glob.glob(f"/usr/lib/postgresql/*/bin/{name}"))
    return hits[-1] if hits else None


def available() -> bool:
    return _lib is not None and bool(_bin("initdb")) and bool(_bin("pg_ctl"))


def start_server() -> str:
    """Start (once) a throw-away Postgres and return its libpq connection string."""
    if _server:
        return _server["conninfo"]
    if not available():
        raise RuntimeError("TEST_POSTGRES needs the Postgres server programs (initdb, pg_ctl) and libpq")
    root = tempfile.mkdtemp(prefix="pgtest")
    os.chmod(root, 0o777)
    data = os.path.join(root, "data")
    as_user = []
    if os.geteuid() == 0:                                  # Postgres refuses to run as root
        as_user = ["runuser", "-u", "postgres", "--"]
    subprocess.run(as_user + [_bin("initdb"), "-D", data, "-A", "trust", "-U", "postgres"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(as_user + [_bin("pg_ctl"), "-D", data, "-o", f"-p {PORT} -k {root} -c listen_addresses=''",
                              "-l", os.path.join(root, "log"), "-w", "start"], check=True, stdout=subprocess.DEVNULL)
    conninfo = f"host={root} port={PORT} user=postgres dbname=postgres options='-c client_min_messages=warning'"
    _server.update(root=root, data=data, conninfo=conninfo, as_user=as_user)
    atexit.register(stop_server)
    return conninfo


def stop_server() -> None:
    if not _server:
        return
    subprocess.run(_server["as_user"] + [_bin("pg_ctl"), "-D", _server["data"], "-m", "immediate", "stop"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shutil.rmtree(_server["root"], ignore_errors=True)
    _server.clear()


def reset(conninfo: str) -> None:
    """An empty public schema (a clean database) - what a brand-new Supabase project looks like."""
    raw = LibpqRaw(conninfo)
    try:
        raw.run("DROP SCHEMA public CASCADE", None)
        raw.run("CREATE SCHEMA public", None)
        raw.commit()
    finally:
        raw.close()


# ----------------------------------------------------------------------------------------- Supabase web API (fake)
def apply_schema_file(conninfo: str) -> None:
    """Run supabase/schema.sql the way you would in the Supabase SQL editor (Supabase's roles are created first)."""
    raw = LibpqRaw(conninfo)
    try:
        for role in ("anon", "authenticated", "service_role"):
            try:
                raw.run(f"CREATE ROLE {role}", None)
                raw.commit()
            except PgError:
                raw.rollback()
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "supabase", "schema.sql")
        with open(path, encoding="utf-8") as f:
            raw.run(f.read(), None)
        raw.commit()
    finally:
        raw.close()


class _Reply:
    def __init__(self, status: int, payload):
        self.status_code = status
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class FakeSupabaseApi:
    """Stands in for Supabase's HTTPS API: POST .../rest/v1/rpc/portal_sql runs the function on the real Postgres,
    one transaction per call, like PostgREST does. Also checks the key header, like Supabase does."""
    calls = 0

    def __init__(self, conninfo: str, key: str = "test-secret-key"):
        self.raw = LibpqRaw(conninfo)
        self.key = key

    def post(self, url, json=None, headers=None, timeout=None):
        import json as jsonlib
        FakeSupabaseApi.calls += 1
        if (headers or {}).get("apikey") != self.key:
            return _Reply(401, {"message": "Invalid API key"})
        if not url.endswith("/rest/v1/rpc/portal_sql"):
            return _Reply(404, {"message": "not found"})
        try:
            rows, _n = self.raw.run("SELECT public.portal_sql(%s, %s::jsonb, %s) AS r",
                                    [json["q"], jsonlib.dumps(json["args"]), json["mode"]])
            self.raw.commit()
        except PgError as exc:
            self.raw.rollback()
            return _Reply(400, {"code": "P0001", "message": str(exc)})
        out = rows[0]["r"]
        return _Reply(200, jsonlib.loads(out) if isinstance(out, str) else out)

    def close(self):
        self.raw.close()
