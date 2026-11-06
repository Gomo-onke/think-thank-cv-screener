"""Usage tracking and Supabase (Postgres) support. SQLite by default; TEST_POSTGRES=1 runs them on a real Postgres."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_portal as tp  # noqa: E402

import pgcompat  # noqa: E402
import usage  # noqa: E402


class UsageTests(tp.FlaskBase):
    def events(self):
        return [dict(r) for r in self.conn.execute("SELECT * FROM usage_events ORDER BY id")]

    def kinds(self):
        return [e["event"] for e in self.events()]

    def test_page_view_is_counted_without_personal_data(self):
        self.client.get("/", headers={"User-Agent": "Mozilla/5.0 (iPhone) Mobile Safari", "Referer": "https://www.google.com/search?q=secret"},
                        environ_base={"REMOTE_ADDR": "203.0.113.77"})
        (e,) = self.events()
        self.assertEqual((e["event"], e["path"], e["device"], e["browser"], e["referrer"]), ("page_view", "/", "mobile", "Safari", "google.com"))
        blob = " ".join(str(v) for v in e.values())
        self.assertNotIn("203.0.113.77", blob)
        self.assertNotIn("secret", blob)
        self.assertEqual(len(e["visitor"]), 16)

    def test_not_counted_healthz_static_or_do_not_track(self):
        self.client.get("/healthz")
        self.client.get("/static/style.css")
        self.client.get("/", headers={"DNT": "1"})
        self.client.get("/", headers={"Sec-GPC": "1"})
        self.assertEqual(self.events(), [])

    def test_tracking_can_be_switched_off(self):
        with mock.patch.dict(os.environ, {"TRACK_USAGE": "false"}):
            self.client.get("/")
        self.assertEqual(self.events(), [])

    def test_same_visitor_same_day_is_one_visitor_new_day_is_new(self):
        h1 = usage.visitor_hash("s", "2026-01-01", "1.2.3.4", "ua")
        self.assertEqual(h1, usage.visitor_hash("s", "2026-01-01", "1.2.3.4", "ua"))
        self.assertNotEqual(h1, usage.visitor_hash("s", "2026-01-02", "1.2.3.4", "ua"))
        self.assertNotEqual(h1, usage.visitor_hash("s", "2026-01-01", "1.2.3.5", "ua"))

    def test_application_events(self):
        self.submit()
        self.submit(email="not-an-email")
        self.assertEqual([k for k in self.kinds()], ["application_submitted", "application_rejected"])

    def test_chat_events_and_detail(self):
        self.client.get("/api/chat/suggestions")
        self.client.post("/api/chat", json={"message": "How do I apply?"})
        self.client.post("/api/chat", json={"message": "zzzz qqqq xxxx"})
        ev = self.events()
        self.assertEqual([e["event"] for e in ev], ["chat_opened", "chat_message", "chat_message"])
        self.assertEqual([e["detail"] for e in ev[1:]], ["matched", "unmatched"])

    def test_login_and_admin_events(self):
        self.login(password="wrong")
        self.login()
        self.client.get("/admin")
        kinds = self.kinds()
        self.assertIn("login_failed", kinds)
        self.assertIn("login_success", kinds)
        self.assertIn("admin_view", kinds)

    def test_private_link_tokens_are_not_stored(self):
        out = self.db.get_candidate  # noqa: F841 - just proves the db helper exists
        self.client.get("/intern/some-secret-token-123")
        for e in self.events():
            self.assertNotIn("some-secret-token-123", e["path"])

    def test_bots_are_counted_separately(self):
        self.client.get("/", headers={"User-Agent": "Googlebot/2.1"})
        self.client.get("/")
        s = usage.summary(self.conn, 7)
        self.assertEqual(s["bots"], 1)
        self.assertEqual(s["totals"]["page_view"], 1)

    def test_summary_numbers(self):
        self.client.get("/", headers={"User-Agent": "Mozilla/5.0 Chrome/120"})
        self.client.get("/", headers={"User-Agent": "Mozilla/5.0 Chrome/120"})
        self.client.get("/", headers={"User-Agent": "Mozilla/5.0 Firefox/120"}, environ_base={"REMOTE_ADDR": "198.51.100.9"})
        self.submit()
        s = usage.summary(self.conn, 7)
        self.assertEqual(s["totals"]["page_view"], 3)
        self.assertEqual(s["visitors"], 2)
        self.assertEqual(s["totals"]["application_submitted"], 1)
        self.assertEqual(s["candidates_saved_total"], 1)
        self.assertEqual(len(s["series"]), 7)
        self.assertEqual(s["series"][-1]["views"], 3)
        self.assertEqual({d["name"] for d in s["browsers"]}, {"Chrome", "Firefox"})
        self.assertEqual(s["conversion"], 50.0)

    def test_usage_page_needs_login_and_renders(self):
        self.assertIn(self.client.get("/admin/usage").status_code, (302, 401))
        self.login()
        for q in ("", "?days=7", "?days=90", "?days=abc", "?days=99999"):
            r = self.client.get("/admin/usage" + q)
            self.assertEqual(r.status_code, 200, q)
        html = self.client.get("/admin/usage").get_data(as_text=True)
        self.assertIn("Website usage", html)
        self.assertIn("Candidates saved", html)

    def test_tracking_failure_never_breaks_the_page(self):
        with mock.patch.object(self.db, "add_usage_event", side_effect=RuntimeError("db down")), \
                self.assertLogs("usage", "ERROR"):
            self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/").status_code, 200)    # the connection still works afterwards

    def test_old_events_are_purged(self):
        self.conn.execute("INSERT INTO usage_events(created_at, day, event) VALUES ('2000-01-01T00:00:00', '2000-01-01', 'page_view')")
        self.conn.commit()
        self.db.purge_usage(self.conn)
        self.conn.commit()
        self.assertEqual(self.events(), [])

    def test_whatsapp_and_api_events_store_no_browser_info(self):
        with mock.patch.object(config_module(), "BOT_API_KEY", "k"):
            self.client.post("/api/bot/message", json={"channel": "api", "user_id": "u1", "text": "hello"},
                             headers={"X-Api-Key": "k", "Authorization": "Bearer k"})
        for e in self.events():
            if e["event"] == "api_bot_message":
                self.assertEqual((e["visitor"], e["device"], e["channel"]), ("", "", "api"))

    def test_health_reports_backend(self):
        self.assertEqual(self.client.get("/healthz").get_json()["database"], self.db.backend())


def config_module():
    import config
    return config


class TranslateTests(unittest.TestCase):
    def test_placeholders_and_insert_or_ignore(self):
        sql, p, wid = pgcompat.translate("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", ("a", "b"))
        self.assertEqual(sql, "INSERT INTO settings(key, value) VALUES (%s, %s) ON CONFLICT DO NOTHING")
        self.assertFalse(wid)

    def test_insert_into_id_table_returns_id(self):
        sql, p, wid = pgcompat.translate("INSERT INTO faq(question) VALUES (?)", ("q",))
        self.assertTrue(sql.endswith("RETURNING id"))
        self.assertTrue(wid)

    def test_percent_and_named(self):
        sql, p, _ = pgcompat.translate("SELECT * FROM t WHERE a LIKE '%x%' AND b = :b", {"b": 1})
        self.assertEqual(sql, "SELECT * FROM t WHERE a LIKE '%%x%%' AND b = %(b)s")
        sql, p, _ = pgcompat.translate("SELECT '%' AS p", ())
        self.assertEqual(sql, "SELECT '%' AS p")
        self.assertIsNone(p)

    def test_row_supports_name_and_index(self):
        r = pgcompat.Row({"a": 1, "b": 2})
        self.assertEqual((r["a"], r[1], dict(r)), (1, 2, {"a": 1, "b": 2}))


@unittest.skipUnless(os.environ.get("TEST_POSTGRES"), "needs TEST_POSTGRES=1")
class PostgresOnlyTests(tp.Base):
    def test_every_table_has_row_level_security_and_no_policies(self):
        rows = self.conn.execute("SELECT c.relname AS t, c.relrowsecurity AS rls FROM pg_class c JOIN pg_namespace n "
                                 "ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relkind = 'r'").fetchall()
        self.assertGreaterEqual(len(rows), 12)
        self.assertEqual([r["t"] for r in rows if not r["rls"]], [])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) AS n FROM pg_policies WHERE schemaname='public'").fetchone()["n"], 0)

    def test_setup_is_repeatable(self):
        self.db.init_db()
        self.db.init_db()
        self.assertEqual(self.conn.execute("SELECT COUNT(*) AS n FROM faq").fetchone()["n"] > 0, True)

    def test_bad_statement_does_not_poison_the_connection(self):
        with self.assertRaises(Exception):
            self.conn.execute("SELECT * FROM no_such_table")
        self.assertEqual(self.conn.execute("SELECT 1 AS x").fetchone()["x"], 1)


@unittest.skipUnless(os.environ.get("TEST_POSTGRES"), "needs TEST_POSTGRES=1")
class SupabaseFilesTests(tp.Base):
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def test_schema_sql_file_runs_on_a_supabase_like_database(self):
        import pg_support
        url = pg_support.start_server()
        pg_support.reset(url)
        raw = pg_support.LibpqRaw(url)
        for role in ("anon", "authenticated"):          # Supabase has these roles; plain Postgres does not
            try:
                raw.run(f"CREATE ROLE {role}", None)
                raw.commit()
            except Exception:  # noqa: BLE001 - role exists from an earlier test
                raw.rollback()
        raw.close()
        with open(os.path.join(self.ROOT, "supabase", "schema.sql"), encoding="utf-8") as f:
            sql = f.read()
        raw = pg_support.LibpqRaw(url)
        raw.run(sql, None)                               # like pasting it into the Supabase SQL editor
        raw.commit()
        raw.run(sql, None)                               # second run: nothing breaks
        raw.commit()
        raw.close()
        conn = pgcompat.connect(url)
        self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                                      "WHERE n.nspname='public' AND c.relkind='r' AND NOT c.relrowsecurity").fetchone()["n"], 0)
        conn.close()
        with mock.patch.dict(os.environ, {"SKIP_SCHEMA_SETUP": "1"}):
            import config
            with mock.patch.object(config, "env_bool", side_effect=lambda k, d=False: True if k == "SKIP_SCHEMA_SETUP" else d):
                self.db.init_db()                        # server start-up against a database made from schema.sql

    def test_migration_copies_sqlite_data_and_keeps_ids(self):
        import sqlite3
        import sys
        import config
        import tools_path  # noqa: F401
        import migrate_sqlite_to_supabase as mig
        path = os.path.join(self.tmp.name, "old.db")
        with mock.patch.object(config, "DATABASE_URL", ""):
            self.db.init_db(path)
            old = self.db.get_conn(path)
            cid = self.db.add_candidate(old, **{k: v for k, v in tp.FORM.items() if k in ("name", "email", "phone", "location", "position")},
                                        cv_text=tp.GOOD_CV)
            old.execute("UPDATE faq SET answer = 'CHANGED OFFLINE' WHERE id = 1")
            old.commit()
            old.close()
        with mock.patch.object(sys, "argv", ["migrate", path]):
            mig.main()
            mig.main()                                   # twice: no duplicates
        got = self.conn.execute("SELECT id, name FROM candidates").fetchall()
        self.assertEqual([(r["id"], r["name"]) for r in got], [(cid, tp.FORM["name"])])
        self.assertEqual(self.conn.execute("SELECT answer FROM faq WHERE id = 1").fetchone()["answer"], "CHANGED OFFLINE")
        new_id = self.db.add_candidate(self.conn, name="Next", email="n@example.org", phone="0821234567",
                                       location="x", position="Data Analyst", cv_text=tp.GOOD_CV)
        self.assertGreater(new_id, cid)


@unittest.skipUnless(os.environ.get("TEST_POSTGRES"), "needs TEST_POSTGRES=1")
class RestApiTests(unittest.TestCase):
    """The Supabase HTTPS route: pgcompat.RestRaw -> (fake PostgREST) -> the real portal_sql function on Postgres."""

    def setUp(self):
        import pg_support
        self.pg = pg_support
        self.url = pg_support.start_server()
        pg_support.reset(self.url)
        pg_support.apply_schema_file(self.url)
        pgcompat.set_rest_session(lambda: pg_support.FakeSupabaseApi(self.url))
        self.addCleanup(pgcompat.set_rest_session, None)
        self.conn = pgcompat.connect_rest("https://fake.supabase.co", "test-secret-key")
        self.addCleanup(self.conn.close)

    def test_values_are_never_run_as_sql_or_as_placeholders(self):
        nasty = ["Robert'); DROP TABLE faq;--", "costs $1 and $2", "semi; colon", "100% sure", "back\\slash", "naïve 日本語", ""]
        for i, text in enumerate(nasty, start=1):
            self.conn.execute("INSERT INTO faq(question, answer, keywords, sort_order) VALUES (?, ?, ?, ?)", (text, text + "$1", "k", i))
        got = [r["question"] for r in self.conn.execute("SELECT question FROM faq ORDER BY sort_order")]
        self.assertEqual(got, nasty)
        self.assertEqual(self.conn.execute("SELECT answer FROM faq WHERE sort_order = 2").fetchone()["answer"], "costs $1 and $2$1")

    def test_types_nulls_rowcount_and_lastrowid(self):
        cur = self.conn.execute("INSERT INTO faq(question, answer, keywords, sort_order) VALUES (?, ?, ?, ?)", ("q", "a", "k", 7))
        self.assertIsInstance(cur.lastrowid, int)
        self.assertEqual(self.conn.execute("UPDATE faq SET answer = ? WHERE id = ?", ("new", cur.lastrowid)).rowcount, 1)
        self.assertEqual(self.conn.execute("UPDATE faq SET answer = 'x' WHERE id = ?", (999999,)).rowcount, 0)
        r = self.conn.execute("SELECT ? AS i, ? AS f, ? AS b, ? AS n", (5, 2.5, True, None)).fetchone()
        self.assertEqual((r["i"], r["f"], r["b"], r["n"]), (5, 2.5, True, None))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM faq").fetchone()[0], 1)           # by position
        self.assertEqual(list(self.conn.execute("SELECT 1 AS zeta, 2 AS alpha").fetchone().keys()), ["zeta", "alpha"])  # column order kept
        self.assertEqual(self.conn.execute("DELETE FROM faq WHERE id = ?", (cur.lastrowid,)).rowcount, 1)

    def test_error_is_reported_and_later_statements_still_work(self):
        with self.assertRaises(RuntimeError):
            self.conn.execute("SELECT * FROM no_such_table")
        self.assertEqual(self.conn.execute("SELECT 1 AS x").fetchone()["x"], 1)

    def test_wrong_key_gets_a_clear_message(self):
        bad = pgcompat.connect_rest("https://fake.supabase.co", "not-the-key")
        with self.assertRaises(RuntimeError) as ctx:
            bad.execute("SELECT 1")
        self.assertIn("service_role", str(ctx.exception))

    def test_missing_function_gets_a_clear_message(self):
        raw = self.pg.LibpqRaw(self.url)
        raw.run("DROP FUNCTION public.portal_sql(text, jsonb, text)", None)
        raw.commit()
        raw.close()
        class Gone:
            def post(self, *a, **k):
                return self_.pg._Reply(404, {"code": "PGRST202", "message": "Could not find the function public.portal_sql"})
            def close(self): pass
        self_ = self
        pgcompat.set_rest_session(Gone)
        with self.assertRaises(RuntimeError) as ctx:
            pgcompat.connect_rest("https://fake.supabase.co", "k").execute("SELECT 1")
        self.assertIn("schema.sql", str(ctx.exception))

    def test_only_service_role_can_run_the_function(self):
        raw = self.pg.LibpqRaw(self.url)
        rows, _ = raw.run("SELECT has_function_privilege(r, 'public.portal_sql(text, jsonb, text)', 'EXECUTE') AS ok, r "
                          "FROM unnest(ARRAY['anon', 'authenticated', 'service_role']) AS r", None)
        raw.close()
        self.assertEqual({r["r"]: r["ok"] for r in rows}, {"anon": False, "authenticated": False, "service_role": True})

    def test_rest_mode_needs_both_settings_and_tells_you_when_tables_are_missing(self):
        import config
        import database as db
        with mock.patch.object(config, "SUPABASE_URL", "https://x.supabase.co"), mock.patch.object(config, "SUPABASE_SERVICE_KEY", ""), \
                mock.patch.object(config, "DATABASE_URL", ""):
            self.assertEqual(db.backend(), "sqlite")
        raw = self.pg.LibpqRaw(self.url)
        raw.run("DROP TABLE usage_events", None)
        raw.commit()
        raw.close()
        with mock.patch.object(config, "SUPABASE_URL", "https://x.supabase.co"), mock.patch.object(config, "SUPABASE_SERVICE_KEY", "test-secret-key"), \
                mock.patch.object(config, "DATABASE_URL", ""):
            with self.assertRaises(RuntimeError) as ctx:
                db.init_db()
        self.assertIn("schema.sql", str(ctx.exception))


class DollarTests(unittest.TestCase):
    def test_dollar_conversion(self):
        self.assertEqual(pgcompat.dollar("a = %s AND b LIKE '%%x' AND c = %s", (1, 2)), ("a = $1 AND b LIKE '%x' AND c = $2", [1, 2]))
        self.assertEqual(pgcompat.dollar("a = %(n)s OR b = %(n)s", {"n": 5}), ("a = $1 OR b = $1", [5]))

    def test_statement_kind(self):
        self.assertEqual(pgcompat._mode("SELECT 1"), "rows")
        self.assertEqual(pgcompat._mode("  with x as (select 1) select * from x"), "rows")
        self.assertEqual(pgcompat._mode("INSERT INTO faq(a) VALUES ($1) RETURNING id"), "returning")
        self.assertEqual(pgcompat._mode("UPDATE faq SET a = $1"), "exec")


class SchemaFileTests(unittest.TestCase):
    def test_generated_schema_has_rls_and_revoke(self):
        import database as db
        sql = db.pg_schema(with_revoke=True)
        self.assertEqual(sql.count("ENABLE ROW LEVEL SECURITY"), sql.count("CREATE TABLE"))
        self.assertIn("REVOKE ALL", sql)
        self.assertNotIn("AUTOINCREMENT", sql)

    def test_committed_schema_file_is_up_to_date(self):
        import database as db
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "supabase", "schema.sql")
        self.assertTrue(os.path.exists(path), "run: python tools/make_supabase_schema.py")
        self.assertIn(db.pg_schema(with_revoke=True).strip(), open(path, encoding="utf-8").read())


if __name__ == "__main__":
    unittest.main()
