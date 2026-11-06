"""Copy the data of an existing SQLite portal database into your Supabase (Postgres) database.

    set DATABASE_URL=postgresql://...            (Windows: set / PowerShell: $env:DATABASE_URL="...")
    python tools/migrate_sqlite_to_supabase.py                    copies recruitment.db (config.DB_PATH)
    python tools/migrate_sqlite_to_supabase.py path/to/other.db   copies another file
    python tools/migrate_sqlite_to_supabase.py --dry-run          only counts what would be copied

Safe to run twice: rows that already exist (same id / key) are skipped, so nothing is duplicated.
The settings, positions and FAQ answers (configuration, which a new online database already holds as defaults) replace
those defaults ONLY while the online database is still new (no candidates or requests in it yet); after that they are
left alone so changes made online are never overwritten.
Ids are kept, so links such as interview -> candidate and the private intern links keep working. The id counters
(sequences) are moved forward afterwards so new rows do not clash with copied ones.
"""
import argparse
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config  # noqa: E402
import database as db  # noqa: E402
import pgcompat  # noqa: E402

# parents before children
CONFIG = ["settings", "positions", "faq"]
ORDER = ["settings", "positions", "faq", "candidates", "screenings", "interviews", "interns", "intern_updates",
         "intern_courses", "chat_log", "escalations", "integrations_log", "bot_sessions", "bot_seen", "usage_events"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sqlite_file", nargs="?", default=config.DB_PATH)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if db.backend() != "postgres":
        sys.exit("Supabase is not configured. Set DATABASE_URL (or SUPABASE_URL + SUPABASE_SERVICE_KEY) first, see supabase/README.md.")
    if not os.path.exists(args.sqlite_file):
        sys.exit(f"No SQLite file at {args.sqlite_file}")

    src = sqlite3.connect(args.sqlite_file)
    src.row_factory = sqlite3.Row
    have = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    dst = None
    if not args.dry_run:
        db.init_db()                       # makes sure the tables exist online
        dst = db.get_conn()
    unknown = sorted(have - set(ORDER) - {"sqlite_sequence"})
    if unknown:
        print("Warning: tables in the SQLite file that are NOT copied:", ", ".join(unknown))

    fresh = bool(dst) and all(dst.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"] == 0
                              for t in ("candidates", "escalations", "interns"))
    total = 0
    for table in ORDER:
        if table not in have:
            continue
        rows = src.execute(f"SELECT * FROM {table}").fetchall()
        if dst and table in CONFIG:
            if not fresh:
                print(f"{table:<18} {len(rows):>5} found, left alone (the online database already has data)")
                continue
            if rows:
                dst.execute(f"DELETE FROM {table}")      # drop the defaults, keep the portal's own configuration
        if args.dry_run:
            print(f"{table:<18} {len(rows)} row(s) would be copied")
            continue
        copied = 0
        for r in rows:
            cols = list(r.keys())
            cur = dst.execute(f"INSERT OR IGNORE INTO {table}({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                              [r[c] for c in cols])
            copied += 1 if cur.rowcount else 0
        dst.commit()
        if table in pgcompat.ID_TABLES:
            dst.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE((SELECT MAX(id) FROM {table}), 1), "
                        f"(SELECT MAX(id) FROM {table}) IS NOT NULL)")
            dst.commit()
        print(f"{table:<18} {len(rows):>5} found, {copied:>5} copied, {len(rows) - copied:>5} already there")
        total += copied
    src.close()
    if dst:
        dst.close()
        print(f"Done. {total} row(s) copied to Supabase.")


if __name__ == "__main__":
    main()
