"""Tests for the recruitment portal. Run:  python -m unittest discover -s tests -v"""
import io
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402

GOOD_CV = ("Jane Doe. Data analyst with 6 years of experience. Bachelor of Science in Statistics. "
           "Skills: data analysis, statistics, python, r, sql, tableau, power bi, machine learning, visualisation.")
WEAK_CV = "Matric graduate. Enjoys cooking and hiking every weekend with friends and family in the mountains."
INTERN_CV = "Student working towards a diploma. Built a small python project, enjoy learning, volunteer, teamwork, computer."

FORM = {"name": "Jane Doe", "email": "jane@example.org", "phone": "+27 82 123 4567", "location": "Cape Town",
        "work_authorisation": "South African citizen", "position": "Data Analyst",
        "highest_qualification": "Bachelor's degree", "years_experience": "6", "consent": "yes", "cv_text": GOOD_CV}


def ok_post(*a, **k):
    return mock.Mock(ok=True, status_code=200, text="{}", json=lambda: {})


def fail_post(*a, **k):
    raise ConnectionError("network down")


class Base(unittest.TestCase):
    """SQLite by default. TEST_POSTGRES=1 runs every test against a real throw-away Postgres (see pg_support.py)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [
            mock.patch.object(config, "DB_PATH", os.path.join(self.tmp.name, "t.db")),
            mock.patch.object(config, "EXCEL_PATH", os.path.join(self.tmp.name, "t.xlsx")),
            mock.patch.object(config, "ZAPIER_WEBHOOK_URL", ""),
            mock.patch.object(config, "RECRUITMENT_LEAD_EMAIL", ""),
        ]
        if os.environ.get("TEST_POSTGRES"):
            import pg_support
            import pgcompat
            url = pg_support.start_server()
            pg_support.reset(url)
            pgcompat.set_driver(pg_support.LibpqRaw)
            self.addCleanup(pgcompat.set_driver, None)
            if os.environ.get("TEST_REST"):
                # the same database, but reached through Supabase's HTTPS API (portal_sql function from supabase/schema.sql)
                pg_support.apply_schema_file(url)
                pgcompat.set_rest_session(lambda: pg_support.FakeSupabaseApi(url))
                self.addCleanup(pgcompat.set_rest_session, None)
                self.patches += [mock.patch.object(config, "DATABASE_URL", ""),
                                 mock.patch.object(config, "SUPABASE_URL", "https://fake.supabase.co"),
                                 mock.patch.object(config, "SUPABASE_SERVICE_KEY", "test-secret-key")]
            else:
                self.patches.append(mock.patch.object(config, "DATABASE_URL", url))
        for p in self.patches:
            p.start()
        import database as db
        db.init_db()
        self.db = db
        self.conn = db.get_conn()

    def tearDown(self):
        self.conn.close()
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def configure_zapier(self, lead="lead@example.org"):
        for name, value in (("ZAPIER_WEBHOOK_URL", "https://hooks.zapier.com/hooks/catch/1/abc/"),
                            ("RECRUITMENT_LEAD_EMAIL", lead)):
            p = mock.patch.object(config, name, value)
            p.start()
            self.addCleanup(p.stop)

    @staticmethod
    def payloads(post):
        """Every JSON body posted to Zapier, in order."""
        return [c.kwargs["json"] for c in post.call_args_list if "hooks.zapier.com" in c.args[0]]


# =========================================================================== service layer
class ServiceTests(Base):
    def apply(self, **over):
        import service
        form = {**FORM, **over}
        return service.apply(self.conn, form, cv_text=form.pop("cv_text"))

    def test_good_candidate_passes_and_is_saved(self):
        out = self.apply()
        self.assertEqual(out["result"]["status"], "Pass")
        c = self.db.get_candidate(self.conn, out["candidate_id"])
        self.assertEqual(c["location"], "Cape Town")
        self.assertEqual(c["stage"], "Applied")
        self.assertTrue(c["consent_at"])

    def test_weak_candidate_rejected(self):
        self.assertEqual(self.apply(cv_text=WEAK_CV)["result"]["status"], "Reject")

    def test_validation(self):
        import service
        for bad in ({"name": ""}, {"email": "nope"}, {"phone": "12"}, {"position": "Astronaut"}, {"consent": ""},
                    {"location": ""}, {"work_authorisation": ""}, {"highest_qualification": "Wizard"},
                    {"years_experience": "abc"}, {"linkedin_url": "javascript:alert(1)"}, {"cv_text": "short"}):
            with self.assertRaises(service.ServiceError, msg=bad):
                self.apply(**bad)

    def test_notifications_logged_even_when_unconfigured(self):
        out = self.apply()
        self.assertEqual([(n["service"], n["action"]) for n in out["notifications"]],
                         [("zapier", "application_received")])
        self.assertFalse(out["notifications"][0]["success"])
        self.assertIn("ZAPIER_WEBHOOK_URL not set", out["notifications"][0]["detail"])
        self.assertTrue(self.db.recent_integration_logs(self.conn, 50))

    def test_candidate_gets_received_email_via_zapier(self):
        self.configure_zapier()
        with mock.patch("integrations.requests.post", side_effect=ok_post) as post:
            self.apply()
        sent = self.payloads(post)
        self.assertEqual([p["event"] for p in sent], ["application_received", "recruiter_notification"])
        mine = sent[0]
        self.assertEqual((mine["send_email"], mine["email_to"]), ("yes", "jane@example.org"))
        self.assertIn("14 business days", mine["email_body"])
        self.assertIn("unsuccessful", mine["email_body"])
        self.assertIn("received", mine["email_subject"].lower())
        self.assertNotIn("score", mine["email_body"].lower())     # candidates never see a verdict
        self.assertNotIn("Pass", mine["email_body"])
        lead = sent[1]
        self.assertEqual((lead["send_email"], lead["email_to"]), ("yes", "lead@example.org"))
        self.assertIn("Pass", lead["email_subject"])

    def test_no_recruiter_email_when_lead_address_blank(self):
        self.configure_zapier(lead="")
        with mock.patch("integrations.requests.post", side_effect=ok_post) as post:
            self.apply()
        self.assertEqual([p["event"] for p in self.payloads(post)], ["application_received"])

    def test_nothing_is_sent_to_anyone_but_zapier(self):
        self.configure_zapier()
        with mock.patch("integrations.requests.post", side_effect=ok_post) as post:
            self.apply()
        self.assertTrue(all("hooks.zapier.com" in c.args[0] for c in post.call_args_list))

    def test_integration_failure_never_blocks_application(self):
        self.configure_zapier()
        with mock.patch("integrations.requests.post", side_effect=fail_post):
            out = self.apply()
        self.assertEqual(out["result"]["status"], "Pass")
        self.assertTrue(self.db.get_candidate(self.conn, out["candidate_id"]))
        self.assertFalse(any(n["success"] for n in out["notifications"]))

    def test_rescreen_sends_no_candidate_email(self):
        import service
        self.configure_zapier(lead="")
        with mock.patch("integrations.requests.post", side_effect=ok_post):
            cid = self.apply()["candidate_id"]
        with mock.patch("integrations.requests.post", side_effect=ok_post) as post:
            service.rescreen(self.conn, cid)
        p = self.payloads(post)[0]
        self.assertEqual((p["event"], p["send_email"], p["email_to"]), ("application_rescreened", "no", ""))

    def test_shortlist_email_rules(self):
        import service
        passed = self.apply()["candidate_id"]
        rejected = self.apply(email="w@example.org", cv_text=WEAK_CV)["candidate_id"]
        with self.assertRaises(service.ServiceError):
            service.send_shortlist_email(self.conn, rejected)          # rejected -> not eligible
        out = service.send_shortlist_email(self.conn, passed)          # Zapier not configured
        self.assertFalse(out["sent"])
        self.assertEqual(self.db.get_candidate(self.conn, passed)["stage"], "Applied")
        service.set_stage(self.conn, rejected, "Shortlisted")           # recruiter override
        self.assertTrue(service.can_send_shortlist(self.db.get_candidate(self.conn, rejected), "Reject"))

    def test_shortlist_email_sent_content_and_stage(self):
        import service
        self.configure_zapier(lead="")
        with mock.patch("integrations.requests.post", side_effect=ok_post):
            cid = self.apply()["candidate_id"]
        with mock.patch("integrations.requests.post", side_effect=ok_post) as post:
            out = service.send_shortlist_email(self.conn, cid, "Thu 6 Nov 10:00", "https://meet.google.com/abc-defg-hij")
        self.assertTrue(out["sent"])
        sent = self.payloads(post)
        self.assertEqual([p["event"] for p in sent], ["shortlist_email"])      # exactly one webhook, one email
        p = sent[0]
        self.assertEqual((p["send_email"], p["email_to"]), ("yes", "jane@example.org"))
        self.assertIn("shortlisted", (p["email_subject"] + p["email_body"]).lower())
        self.assertIn("5 business days", p["email_body"])
        self.assertIn("Google Meet", p["email_body"])
        self.assertIn("https://meet.google.com/abc-defg-hij", p["email_body"])
        c = self.db.get_candidate(self.conn, cid)
        self.assertEqual(c["stage"], "Interview invited")
        self.assertTrue(c["shortlist_email_sent_at"])

    def test_shortlist_not_marked_sent_if_zapier_rejects(self):
        import service
        self.configure_zapier(lead="")
        with mock.patch("integrations.requests.post", side_effect=ok_post):
            cid = self.apply()["candidate_id"]
        with mock.patch("integrations.requests.post", side_effect=fail_post):
            out = service.send_shortlist_email(self.conn, cid)
        self.assertFalse(out["sent"])
        self.assertEqual(self.db.get_candidate(self.conn, cid)["stage"], "Applied")

    def test_meet_link_must_be_google_meet(self):
        import service
        cid = self.apply()["candidate_id"]
        with self.assertRaises(service.ServiceError):
            service.send_shortlist_email(self.conn, cid, "", "https://evil.example/meet")

    def test_interview_ranking_and_validation(self):
        import service
        cid = self.apply()["candidate_id"]
        data = {"interviewer": "Sam", "skills_rating": "4", "communication_rating": "5", "culture_rating": "4",
                "overall_rating": "5", "recommendation": "Yes", "notes": "Great."}
        for bad in ({"interviewer": ""}, {"overall_rating": "6"}, {"skills_rating": "x"}, {"recommendation": "Perhaps"}):
            with self.assertRaises(service.ServiceError, msg=bad):
                service.save_interview(self.conn, cid, {**data, **bad})
        service.save_interview(self.conn, cid, data)
        self.assertEqual(self.db.get_candidate(self.conn, cid)["stage"], "Interviewed")
        row = self.db.latest_screenings(self.conn)[0]
        self.assertEqual(row["avg_rating"], 5.0)
        self.assertEqual(row["rec_yes"], 1)

    def test_intern_flow(self):
        import service
        cid = self.apply(position="Intern", cv_text=INTERN_CV, preferred_department="Data & Analytics",
                         highest_qualification="Diploma", years_experience="0")["candidate_id"]
        self.assertEqual(self.db.get_candidate(self.conn, cid)["preferred_department"], "Data & Analytics")
        with self.assertRaises(service.ServiceError):                  # must be Selected first
            service.place_intern(self.conn, cid, "Data & Analytics", "Pat", "")
        service.set_stage(self.conn, cid, "Selected")
        with self.assertRaises(service.ServiceError):
            service.place_intern(self.conn, cid, "Nonexistent", "Pat", "")
        iid, created = service.place_intern(self.conn, cid, "Cloud & DevOps", "Pat", "2026-12-01")
        self.assertTrue(created)
        self.assertTrue(self.db.list_intern_courses(self.conn, iid))   # starter courses seeded
        service.add_update(self.conn, iid, "Welcome aboard!", "HR")
        with self.assertRaises(service.ServiceError):
            service.add_course(self.conn, iid, "Bad", "", "javascript:alert(1)", "")
        intern = self.db.get_intern(self.conn, iid)
        self.assertEqual(self.db.get_intern_by_token(self.conn, intern["token"])["id"], iid)
        self.assertGreater(len(intern["token"]), 20)

    def test_non_intern_cannot_be_placed(self):
        import service
        cid = self.apply()["candidate_id"]
        service.set_stage(self.conn, cid, "Selected")
        with self.assertRaises(service.ServiceError):
            service.place_intern(self.conn, cid, "Cloud & DevOps", "", "")


# =========================================================================== chatbot
class ChatbotTests(Base):
    def ask(self, text):
        import chatbot
        return chatbot.reply(text, self.db.list_faq(self.conn))

    def test_matches(self):
        self.assertTrue(self.ask("how long until I hear back?")["matched"])
        self.assertIn("14", self.ask("how long until I hear back?")["answer"])
        self.assertTrue(self.ask("can I work from home")["matched"])
        self.assertTrue(self.ask("hello")["matched"])

    def test_unknown_question_not_matched(self):
        r = self.ask("what colour is the moon")
        self.assertFalse(r["matched"])
        self.assertTrue(r["suggestions"])

    def test_placeholders_filled(self):
        self.assertNotIn("{org}", " ".join(self.ask(q)["answer"] for q in ("who are you hiring", "how long until I hear back")))

    def test_long_input_safe(self):
        self.ask("a" * 100000)

    def test_human_hand_off_offered(self):
        for q in ("can I speak to a person", "I want to talk to a recruiter", "let me speak to a human", "please call me"):
            self.assertTrue(self.ask(q)["escalate"], q)
        self.assertTrue(self.ask("what colour is the moon")["escalate"])      # fallback also offers a human
        self.assertFalse(self.ask("how long until I hear back?")["escalate"])
        self.assertFalse(self.ask("who can I contact with other questions")["escalate"])
        self.assertFalse(self.ask("hello")["escalate"])


# =========================================================================== excel
class ExcelTests(Base):
    def test_workbook(self):
        import service
        from openpyxl import load_workbook
        service.apply(self.conn, FORM, cv_text=GOOD_CV)
        service.apply(self.conn, {**FORM, "name": "=HYPERLINK(\"http://evil\",\"x\")", "email": "e@example.org"}, cv_text=WEAK_CV)
        self.assertTrue(os.path.exists(config.EXCEL_PATH))            # written automatically on application
        wb = load_workbook(config.EXCEL_PATH)
        self.assertEqual(wb.sheetnames, ["Summary", "Candidates", "Interviews", "Interns"])
        ws = wb["Candidates"]
        self.assertIsNotNone(ws.freeze_panes)
        self.assertTrue(ws.auto_filter.ref)
        self.assertEqual(ws.max_row, 3)
        for row in ws.iter_rows(min_row=2):                           # no cell is ever a formula
            for cell in row:
                self.assertNotEqual(cell.data_type, "f", cell.coordinate)
        headers = [c.value for c in ws[1]]
        for h in ("Rank", "Candidate", "Score /100", "Auto decision", "Hiring stage"):
            self.assertIn(h, headers)
        self.assertEqual(ws.cell(2, headers.index("Auto decision") + 1).value, "Pass")  # best score ranked first


# =========================================================================== Flask
class FlaskBase(Base):
    """The Flask app, a test client and helpers, without any tests of its own (other test files build on it)."""

    def setUp(self):
        super().setUp()
        import app as app_module
        self.app = app_module.create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        self.cpatch = mock.patch("integrations.requests.post", side_effect=ok_post)
        self.post = self.cpatch.start()
        self.addCleanup(self.cpatch.stop)

    def login(self, client=None, password="0000"):
        return (client or self.client).post("/admin/login", data={"password": password})

    def submit(self, follow_redirects=False, **over):
        return self.client.post("/submit", data={**FORM, **over}, follow_redirects=follow_redirects)


class FlaskTests(FlaskBase):

    # ---- public side
    def test_public_pages_open_without_login(self):
        for path in ("/", "/thanks", "/healthz", "/api/chat/suggestions"):
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_form_has_recruitment_fields_and_cv_upload(self):
        html = self.client.get("/").get_data(as_text=True)
        for field in ("name", "email", "phone", "location", "work_authorisation", "position", "highest_qualification",
                      "years_experience", "notice_period", "available_from", "expected_salary", "work_arrangement",
                      "linkedin_url", "portfolio_url", "referral_source", "cover_note", "cv_file", "cv_text", "consent",
                      "preferred_department"):
            self.assertIn(f'name="{field}"', html, field)
        self.assertIn("Intern", html)
        self.assertIn("Chat with us", html)         # chatbot present for applicants

    def test_applicant_sees_thanks_not_score(self):
        r = self.submit()
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/thanks"))
        page = self.client.get("/thanks").get_data(as_text=True)
        self.assertIn("14 business days", page)
        for word in ("Pass", "Reject", "Needs Review", "score"):
            self.assertNotIn(word, page.replace("Application received", ""))

    def test_submit_with_file_upload(self):
        data = {**FORM, "cv_text": "", "cv_file": (io.BytesIO(GOOD_CV.encode()), "cv.txt")}
        r = self.client.post("/submit", data=data, content_type="multipart/form-data")
        self.assertTrue(r.headers["Location"].endswith("/thanks"))
        self.assertEqual(self.db.get_candidate(self.conn, 1)["cv_filename"], "cv.txt")

    def test_bad_submissions_show_error_and_save_nothing(self):
        r = self.submit(consent="", follow_redirects=True)
        self.assertIn("consent", r.get_data(as_text=True))
        r = self.client.post("/submit", data={**FORM, "cv_text": "", "cv_file": (io.BytesIO(b"x"), "cv.exe")},
                             content_type="multipart/form-data", follow_redirects=True)
        self.assertIn("Unsupported file type", r.get_data(as_text=True))
        self.assertEqual(self.db.latest_screenings(self.conn), [])

    def test_oversized_upload_is_refused_politely(self):
        self.app.config["MAX_CONTENT_LENGTH"] = 2000
        data = {**FORM, "cv_text": "", "cv_file": (io.BytesIO(b"x" * 5000), "cv.txt")}
        r = self.client.post("/submit", data=data, content_type="multipart/form-data", follow_redirects=True)
        self.assertIn("File too large", r.get_data(as_text=True))
        self.assertEqual(self.db.latest_screenings(self.conn), [])

    def test_public_submit_rate_limit(self):
        with mock.patch.dict(os.environ, {"SUBMIT_LIMIT_PER_HOUR": "2"}):
            for _ in range(2):
                self.submit()
            r = self.submit(follow_redirects=True)
        self.assertIn("Too many submissions", r.get_data(as_text=True))

    # ---- the wall
    def test_admin_pages_require_password(self):
        for path in ("/admin", "/admin/candidates", "/admin/candidates/1", "/admin/candidates/1/interview",
                     "/admin/interviews", "/admin/interns", "/admin/faq", "/admin/criteria", "/admin/requests",
                     "/admin/integrations", "/admin/export.xlsx"):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 302, path)
            self.assertIn("/admin/login", r.headers["Location"], path)
        for path in ("/admin/candidates/1/shortlist-email", "/admin/candidates/1/stage", "/admin/faq/save",
                     "/admin/criteria/settings", "/admin/integrations/test-zapier"):
            self.assertEqual(self.client.post(path, data={}).status_code, 302, path)

    def test_password_typed_once(self):
        self.assertEqual(self.client.post("/admin/login", data={"password": "1234"}).status_code, 401)
        self.assertEqual(self.login().status_code, 302)
        for path in ("/admin", "/admin/candidates", "/admin/interns", "/admin/faq"):
            self.assertEqual(self.client.get(path).status_code, 200, path)     # no second prompt

    def test_logout_closes_the_wall_and_no_store(self):
        self.login()
        self.assertIn("no-store", self.client.get("/admin").headers["Cache-Control"])
        self.client.post("/admin/logout")
        self.assertEqual(self.client.get("/admin").status_code, 302)

    def test_lockout_after_repeated_failures(self):
        for _ in range(5):
            self.client.post("/admin/login", data={"password": "bad"})
        self.assertEqual(self.client.post("/admin/login", data={"password": "0000"}).status_code, 429)

    def test_open_redirect_blocked(self):
        for evil in ("//evil.example", "https://evil.example", "/\\evil.example"):
            r = self.client.post("/admin/login", data={"password": "0000", "next": evil})
            self.assertTrue(r.headers["Location"].endswith("/admin"), evil)
            self.client.post("/admin/logout")

    def test_password_from_env(self):
        with mock.patch.dict(os.environ, {"ADMIN_PASSWORD": "s3cret"}):
            self.assertEqual(self.client.post("/admin/login", data={"password": "0000"}).status_code, 401)
            self.assertEqual(self.client.post("/admin/login", data={"password": "s3cret"}).status_code, 302)

    # ---- recruiter pages
    def test_recruiter_sees_scores_and_all_details(self):
        self.submit()
        self.login()
        ranking = self.client.get("/admin/candidates").get_data(as_text=True)
        self.assertIn("Jane Doe", ranking)
        self.assertIn("Pass", ranking)
        self.assertIn("Send shortlist email", ranking)             # the button, on passed candidates
        detail = self.client.get("/admin/candidates/1").get_data(as_text=True)
        for text in ("Cape Town", "Bachelor", "Score breakdown", "Required keywords", "South African citizen", "jane@example.org"):
            self.assertIn(text, detail)
        self.assertEqual(self.client.get("/admin/candidates/999").status_code, 302)
        self.assertEqual(self.client.get("/admin").status_code, 200)

    def test_shortlist_button_hidden_for_rejected(self):
        self.submit(cv_text=WEAK_CV, email="w@example.org", name="Weak Person")
        self.login()
        self.assertNotIn("Send shortlist email</button>", self.client.get("/admin/candidates").get_data(as_text=True))

    def test_shortlist_button_sends_email(self):
        self.configure_zapier()
        self.submit()
        self.login()
        r = self.client.post("/admin/candidates/1/shortlist-email", data={"next": "/admin/candidates"}, follow_redirects=True)
        self.assertIn("handed to Zapier", r.get_data(as_text=True))
        self.assertEqual(self.payloads(self.post)[-1]["event"], "shortlist_email")
        self.assertEqual(self.db.get_candidate(self.conn, 1)["stage"], "Interview invited")

    def test_shortlist_button_honest_when_zapier_not_configured(self):
        self.submit()
        self.login()
        r = self.client.post("/admin/candidates/1/shortlist-email", data={}, follow_redirects=True)
        self.assertIn("NOT sent", r.get_data(as_text=True))
        self.assertEqual(self.db.get_candidate(self.conn, 1)["stage"], "Applied")

    def test_interview_page_and_decision(self):
        self.submit()
        self.login()
        page = self.client.get("/admin/candidates/1/interview").get_data(as_text=True)
        self.assertIn("right person for the job", page)
        r = self.client.post("/admin/candidates/1/interview", follow_redirects=True, data={
            "interviewer": "Sam", "skills_rating": "4", "communication_rating": "4", "culture_rating": "5",
            "overall_rating": "5", "recommendation": "Yes", "notes": "Strong <script>alert(1)</script>"})
        html = r.get_data(as_text=True)
        self.assertIn("Interview saved", html)
        self.assertNotIn("<script>alert(1)</script>", html)         # notes are escaped
        self.assertIn("Interviewed", self.client.get("/admin/interviews").get_data(as_text=True))
        bad = self.client.post("/admin/candidates/1/interview", data={"interviewer": "Sam"})
        self.assertIn("must be a rating", bad.get_data(as_text=True))

    def test_stage_change_and_invalid_stage(self):
        self.submit()
        self.login()
        self.client.post("/admin/candidates/1/stage", data={"stage": "Shortlisted"})
        self.assertEqual(self.db.get_candidate(self.conn, 1)["stage"], "Shortlisted")
        r = self.client.post("/admin/candidates/1/stage", data={"stage": "Hired!!"}, follow_redirects=True)
        self.assertEqual(self.db.get_candidate(self.conn, 1)["stage"], "Shortlisted")

    def test_intern_end_to_end(self):
        self.submit(position="Intern", cv_text=INTERN_CV, preferred_department="UX / UI Design",
                    highest_qualification="Diploma", years_experience="0")
        self.login()
        self.client.post("/admin/candidates/1/stage", data={"stage": "Selected"})
        self.assertIn("Place", self.client.get("/admin/interns").get_data(as_text=True))
        r = self.client.post("/admin/candidates/1/place-intern", data={"department": "UX / UI Design", "supervisor": "Lee"})
        self.assertEqual(r.status_code, 302)
        intern = self.db.get_intern(self.conn, 1)
        self.client.post("/admin/interns/1/update", data={"message": "Welcome to the design team!", "author": "HR"})
        self.client.post("/admin/interns/1/course", data={"title": "Figma basics", "link": "https://example.org"})
        # the intern's page works WITHOUT a login, but only with the secret link
        anon = self.app.test_client()
        page = anon.get(f"/intern/{intern['token']}").get_data(as_text=True)
        self.assertIn("Welcome to the design team!", page)
        self.assertIn("Figma basics", page)
        self.assertEqual(anon.get("/intern/not-a-real-token").status_code, 404)
        self.assertEqual(anon.get("/admin/interns/1").status_code, 302)
        self.assertIn("noindex", anon.get(f"/intern/{intern['token']}").headers["X-Robots-Tag"])

    def test_faq_admin_and_public_chat(self):
        anon = self.app.test_client()
        r = anon.post("/api/chat", json={"message": "how long until I hear back"})
        self.assertTrue(r.get_json()["matched"])
        self.assertEqual(anon.post("/api/chat", json={"message": "  "}).status_code, 400)
        anon.post("/api/chat", json={"message": "what colour is the moon"})
        self.login()
        page = self.client.get("/admin/faq").get_data(as_text=True)
        self.assertIn("what colour is the moon", page)               # unanswered log
        self.client.post("/admin/faq/save", data={"question": "Do you have parking?", "answer": "Yes, free parking.",
                                                  "keywords": "parking, park, car", "sort_order": "5"})
        self.assertIn("free parking", anon.post("/api/chat", json={"message": "is there parking?"}).get_json()["answer"])

    def test_chat_answers_are_not_html_injected(self):
        self.login()
        self.client.post("/admin/faq/save", data={"question": "Test", "answer": "<b>x</b>", "keywords": "zzzqq"})
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", self.client.get("/admin/faq").get_data(as_text=True))

    def test_criteria_page_validation(self):
        self.login()
        self.assertEqual(self.client.get("/admin/criteria").status_code, 200)
        r = self.client.post("/admin/criteria/settings", data={"pass_threshold": "50", "review_threshold": "60"}, follow_redirects=True)
        self.assertIn("review threshold", r.get_data(as_text=True))
        r = self.client.post("/admin/criteria/position", follow_redirects=True, data={
            "name": "Tester", "min_years": "1", "min_education": "Diploma", "required_keywords": "qa, testing",
            "preferred_keywords": "", "w_exp": "1", "w_edu": "1", "w_req": "1", "w_pref": "0"})
        self.assertIn("Saved Tester", r.get_data(as_text=True))
        self.assertTrue(self.db.get_position(self.conn, "Tester"))

    def test_rescreen_and_export(self):
        self.submit()
        self.login()
        r = self.client.post("/admin/candidates/1/rescreen", data={"position": "Data Analyst"}, follow_redirects=True)
        self.assertIn("Re-screened", r.get_data(as_text=True))
        x = self.client.get("/admin/export.xlsx")
        self.assertEqual(x.status_code, 200)
        self.assertTrue(x.data.startswith(b"PK"))

    def test_integrations_page_and_tests(self):
        self.login()
        page = self.client.get("/admin/integrations").get_data(as_text=True)
        self.assertIn("Zapier", page)
        self.assertIn("shortlist_email", page)
        r = self.client.post("/admin/integrations/test-zapier", follow_redirects=True)
        self.assertIn("failed", r.get_data(as_text=True))          # not configured -> honest message
        r = self.client.post("/admin/integrations/test-email", data={"email": "me@example.org"}, follow_redirects=True)
        self.assertIn("NOT sent", r.get_data(as_text=True))

    def test_test_email_goes_through_zapier(self):
        self.configure_zapier()
        self.login()
        r = self.client.post("/admin/integrations/test-email", data={"email": "me@example.org"}, follow_redirects=True)
        self.assertIn("handed to Zapier", r.get_data(as_text=True))
        p = self.payloads(self.post)[-1]
        self.assertEqual((p["event"], p["send_email"], p["email_to"]), ("test_email", "yes", "me@example.org"))

    def test_intern_welcome_email_via_zapier(self):
        self.configure_zapier(lead="")
        self.submit(position="Intern", cv_text=INTERN_CV, highest_qualification="Diploma", years_experience="0")
        self.login()
        self.client.post("/admin/candidates/1/stage", data={"stage": "Selected"})
        self.client.post("/admin/candidates/1/place-intern", data={"department": "Cloud & DevOps"})
        r = self.client.post("/admin/interns/1/email-link", follow_redirects=True)
        self.assertIn("handed to Zapier", r.get_data(as_text=True))
        p = self.payloads(self.post)[-1]
        self.assertEqual((p["event"], p["send_email"]), ("intern_welcome_email", "yes"))
        self.assertIn("/intern/", p["email_body"])

    def test_zapier_payload_fields(self):
        self.configure_zapier(lead="")
        self.submit()
        p = self.payloads(self.post)[0]
        self.assertEqual(p["event"], "application_received")
        for key in ("event", "send_email", "email_to", "email_subject", "email_body", "candidate_name", "email", "phone",
                    "position", "score", "status", "stage", "notes", "timestamp"):
            self.assertIn(key, p)

    def test_infobip_is_only_used_for_whatsapp_never_for_email(self):
        """Emails are Zapier-only. The word Infobip may appear only in the WhatsApp channel code and its docs."""
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for name in ("integrations.py", "emails.py", "service.py", "screener.py", "excel_export.py", "sheets.py",
                     "database.py", "chatbot.py", "bot.py"):
            text = open(os.path.join(root, name), encoding="utf-8").read().lower()
            self.assertNotIn("infobip", text, name)

    def test_applications_send_nothing_to_infobip_even_when_it_is_configured(self):
        self.configure_zapier()
        for name, value in (("INFOBIP_BASE_URL", "x.api.infobip.com"), ("INFOBIP_API_KEY", "k"),
                            ("INFOBIP_WHATSAPP_SENDER", "27820000000")):
            p = mock.patch.object(config, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.submit()
        urls = [c.args[0] for c in self.post.call_args_list]
        self.assertTrue(urls)
        self.assertTrue(all("hooks.zapier.com" in u for u in urls), urls)

    # ---- human escalation (chatbot -> recruiter)
    ESC = {"name": "Visitor", "email": "visitor@example.org", "message": "Can someone call me about my application?"}

    def test_escalation_saved_and_two_emails_sent_via_zapier(self):
        self.configure_zapier()
        anon = self.app.test_client()
        r = anon.post("/api/escalate", json=self.ESC)
        self.assertEqual((r.status_code, r.get_json()["ok"]), (200, True))
        sent = self.payloads(self.post)
        self.assertEqual([p["event"] for p in sent], ["human_escalation", "human_escalation_ack"])
        self.assertEqual(sent[0]["email_to"], "lead@example.org")
        self.assertIn("call me", sent[0]["email_body"])
        self.assertEqual(sent[1]["email_to"], "visitor@example.org")
        self.assertNotIn("Pass", sent[1]["email_body"])
        self.assertEqual(self.db.list_escalations(self.conn)[0]["status"], "Open")

    def test_escalation_saved_even_if_zapier_is_down(self):
        self.configure_zapier()
        with mock.patch("integrations.requests.post", side_effect=fail_post):
            r = self.app.test_client().post("/api/escalate", json=self.ESC)
        self.assertTrue(r.get_json()["ok"])                          # the request is never lost
        self.assertEqual(len(self.db.list_escalations(self.conn)), 1)

    def test_escalation_validation(self):
        anon = self.app.test_client()
        for bad in ({"name": ""}, {"email": "nope"}, {"message": "hi"}):
            r = anon.post("/api/escalate", json={**self.ESC, **bad})
            self.assertEqual(r.status_code, 400, bad)
            self.assertFalse(r.get_json()["ok"])
        self.assertEqual(anon.post("/api/escalate", data="not json").status_code, 400)
        self.assertEqual(self.db.list_escalations(self.conn), [])

    def test_escalation_rate_limit(self):
        anon = self.app.test_client()
        with mock.patch.dict(os.environ, {"ESCALATION_LIMIT_PER_HOUR": "2"}):
            codes = [anon.post("/api/escalate", json=self.ESC).status_code for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])

    def test_requests_page_is_behind_the_wall_and_resolves(self):
        self.app.test_client().post("/api/escalate", json=self.ESC)
        self.assertEqual(self.client.get("/admin/requests").status_code, 302)
        self.assertEqual(self.client.post("/admin/requests/1/resolve", data={}).status_code, 302)
        self.login()
        page = self.client.get("/admin/requests").get_data(as_text=True)
        self.assertIn("Can someone call me", page)
        self.assertIn("Requests", self.client.get("/admin").get_data(as_text=True))
        self.client.post("/admin/requests/1/resolve", data={"note": "Replied by email"})
        self.assertEqual(self.db.list_escalations(self.conn)[0]["status"], "Resolved")
        self.assertIn("No open requests", self.client.get("/admin/requests").get_data(as_text=True))

    def test_chat_widget_has_human_hand_off(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("Talk to a recruiter", html)
        self.assertIn('id="human-form"', html)

    def test_secret_key_is_random_and_persisted(self):
        key = self.app.config["SECRET_KEY"]
        self.assertGreaterEqual(len(key), 32)
        import app as app_module
        self.assertEqual(app_module.create_app().config["SECRET_KEY"], key)


if __name__ == "__main__":
    unittest.main()
