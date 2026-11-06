"""Tests for the chat channels: text-channel conversation, Infobip WhatsApp webhook, Answers API, website widget.
Run:  python -m unittest discover -s tests -v"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from test_portal import Base, ok_post  # noqa: E402

SECRET = "s3cret-value"
KEY = "bot-key-123"


def inbound(text="hello", sender="27821234567", mid="m1", mtype="TEXT"):
    return {"results": [{"from": sender, "to": "27800000000", "integrationType": "WHATSAPP", "messageId": mid,
                         "message": {"type": mtype, "text": text}, "contact": {"name": "Jane"}}]}


class ChannelBase(Base):
    def setUp(self):
        super().setUp()
        import app as app_module
        import whatsapp
        whatsapp._recent.clear()
        self.app = app_module.create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        for name, value in (("INFOBIP_WEBHOOK_SECRET", SECRET), ("BOT_API_KEY", KEY),
                            ("INFOBIP_BASE_URL", "https://abc123.api.infobip.com/"), ("INFOBIP_API_KEY", "infobip-key"),
                            ("INFOBIP_WHATSAPP_SENDER", "+27 80 000 0000"), ("EMBED_ALLOWED_ORIGINS", "")):
            p = mock.patch.object(config, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.post = mock.patch("integrations.requests.post", side_effect=ok_post).start()
        self.addCleanup(mock.patch.stopall)

    def sent_to_infobip(self):
        return [c for c in self.post.call_args_list if "infobip.com" in c.args[0]]

    def sent_to_zapier(self):
        return [c.kwargs["json"] for c in self.post.call_args_list if "hooks.zapier.com" in c.args[0]]

    def say(self, text, user="27821234567", channel="whatsapp"):
        import bot
        return bot.handle(self.conn, channel, user, text)


# =========================================================================== the text conversation
class BotConversationTests(ChannelBase):
    def test_faq_answer_comes_with_a_numbered_menu(self):
        r = self.say("how long until I hear back?")
        self.assertIn("14", r["reply"])
        self.assertIn("1. ", r["reply"])
        self.assertIn("0. Talk to a recruiter", r["reply"])
        self.assertEqual(r["handoff"], "none")

    def test_privacy_note_only_on_a_first_message(self):
        self.assertIn("Automated assistant", self.say("hello")["reply"])
        self.assertNotIn("Automated assistant", self.say("how long until I hear back?")["reply"])
        self.assertIn("Automated assistant", self.say("hello", user="27829999999")["reply"])

    def test_number_picks_a_menu_question(self):
        first = self.say("hello")["reply"]
        question = [line for line in first.splitlines() if line.startswith("2. ")][0][3:]
        picked = self.say("2")["reply"]
        direct = self.say(question)["reply"]
        self.assertEqual(picked.split("\n\n")[0], direct.split("\n\n")[0])

    def test_unknown_question_offers_the_human_and_remembers_it(self):
        r = self.say("what colour is the moon")
        self.assertFalse(r["matched"])
        self.assertIn("Reply 0", r["reply"])
        self.assertEqual(self.db.get_bot_session(self.conn, "whatsapp", "27821234567")["data"]["question"],
                         "what colour is the moon")

    def test_whatsapp_hand_off_without_email(self):
        self.configure_zapier()
        self.say("what colour is the moon")
        self.assertEqual(self.say("0")["handoff"], "asking")
        self.assertIn("email", self.say("Jane Doe")["reply"].lower())
        done = self.say("skip")
        self.assertEqual(done["handoff"], "submitted")
        self.assertIn("WhatsApp", done["reply"])
        row = self.db.list_escalations(self.conn)[0]
        self.assertEqual((row["name"], row["email"], row["channel"], row["contact"], row["message"]),
                         ("Jane Doe", "", "whatsapp", "27821234567", "what colour is the moon"))
        sent = self.sent_zapier = self.sent_to_zapier()
        self.assertEqual([p["event"] for p in sent], ["human_escalation"])     # no visitor email: nobody to send to
        self.assertIn("27821234567", sent[0]["email_body"])
        self.assertEqual(self.db.get_bot_session(self.conn, "whatsapp", "27821234567")["state"], "idle")

    def test_hand_off_with_email_also_acknowledges_the_visitor(self):
        self.configure_zapier()
        self.say("can I speak to a person")
        self.say("Sam")
        self.assertEqual(self.say("sam@example.org")["handoff"], "asking")      # still needs the question
        done = self.say("Please phone me about my interview time")
        self.assertEqual(done["handoff"], "submitted")
        self.assertEqual([p["event"] for p in self.sent_to_zapier()], ["human_escalation", "human_escalation_ack"])
        self.assertEqual(self.sent_to_zapier()[1]["email_to"], "sam@example.org")

    def test_bad_email_is_asked_again_and_cancel_stops(self):
        self.say("0")
        self.say("Sam")
        self.assertIn("does not look like", self.say("not-an-email")["reply"])
        self.assertEqual(self.say("cancel")["handoff"], "none")
        self.assertEqual(self.db.list_escalations(self.conn), [])
        self.assertEqual(self.db.get_bot_session(self.conn, "whatsapp", "27821234567")["state"], "idle")

    def test_api_user_without_a_phone_number_must_give_an_email(self):
        self.say("what colour is the moon", user="visitor-abc", channel="api")
        self.say("0", user="visitor-abc", channel="api")
        self.say("Sam", user="visitor-abc", channel="api")
        r = self.say("skip", user="visitor-abc", channel="api")           # skip is not allowed: no way to reply
        self.assertEqual(r["handoff"], "asking")
        self.assertIn("does not look like", r["reply"])

    def test_users_do_not_share_a_conversation(self):
        self.say("0", user="111111111")
        self.assertEqual(self.say("how long until I hear back?", user="222222222")["handoff"], "none")
        self.assertEqual(self.db.get_bot_session(self.conn, "whatsapp", "111111111")["state"], "ask_name")

    def test_a_quiet_session_starts_again(self):
        self.say("0")
        self.conn.execute("UPDATE bot_sessions SET updated_at = '2020-01-01T00:00:00+00:00'")
        self.conn.commit()
        self.assertEqual(self.say("how long until I hear back?")["handoff"], "none")

    def test_empty_and_huge_input_are_safe(self):
        self.assertIn("Please type", self.say("   ")["reply"])
        self.say("x" * 100000)

    def test_unanswered_questions_are_logged_for_the_team(self):
        self.say("what colour is the moon")
        self.assertEqual(self.db.unanswered_chats(self.conn)[0]["question"], "what colour is the moon")


# =========================================================================== Infobip WhatsApp webhook
class WhatsAppWebhookTests(ChannelBase):
    URL = "/webhooks/infobip/whatsapp"

    def test_secret_is_required(self):
        self.assertEqual(self.client.post(self.URL, json=inbound()).status_code, 401)
        self.assertEqual(self.client.post(self.URL + "?secret=wrong", json=inbound()).status_code, 401)
        self.assertEqual(self.sent_to_infobip(), [])
        with mock.patch.object(config, "INFOBIP_WEBHOOK_SECRET", ""):     # unset = closed, never open
            self.assertEqual(self.client.post(self.URL + "?secret=", json=inbound()).status_code, 503)

    def test_secret_in_header_bearer_or_basic_also_works(self):
        import base64
        basic = "Basic " + base64.b64encode(f"infobip:{SECRET}".encode()).decode()
        for i, headers in enumerate(({"X-Webhook-Secret": SECRET}, {"Authorization": f"Bearer {SECRET}"},
                                     {"Authorization": basic})):
            r = self.client.post(self.URL, json=inbound(mid=f"h{i}"), headers=headers)
            self.assertEqual(r.status_code, 200, headers)

    def test_message_is_answered_through_infobip(self):
        r = self.client.post(f"{self.URL}?secret={SECRET}", json=inbound("how long until I hear back?"))
        self.assertEqual((r.status_code, r.get_json()), (200, {"ok": True, "handled": 1}))
        call = self.sent_to_infobip()[0]
        self.assertEqual(call.args[0], "https://abc123.api.infobip.com/whatsapp/1/message/text")
        self.assertEqual(call.kwargs["headers"]["Authorization"], "App infobip-key")
        body = call.kwargs["json"]
        self.assertEqual((body["from"], body["to"]), ("27800000000", "27821234567"))
        self.assertIn("14 business days", body["content"]["text"])
        self.assertTrue(body["messageId"])
        log = self.db.recent_integration_logs(self.conn, 5)[0]
        self.assertEqual((log["service"], log["action"], log["success"]), ("infobip", "whatsapp_reply", 1))

    def test_duplicate_delivery_is_answered_once(self):
        for _ in range(3):
            self.client.post(f"{self.URL}?secret={SECRET}", json=inbound(mid="same-id"))
        self.assertEqual(len(self.sent_to_infobip()), 1)

    def test_several_messages_in_one_delivery(self):
        payload = {"results": inbound("hello", mid="a")["results"] + inbound("how long until I hear back?", mid="b")["results"]}
        self.client.post(f"{self.URL}?secret={SECRET}", json=payload)
        self.assertEqual(len(self.sent_to_infobip()), 2)

    def test_non_text_message_gets_a_polite_answer(self):
        self.client.post(f"{self.URL}?secret={SECRET}", json=inbound("", mtype="IMAGE"))
        self.assertIn("only read text", self.sent_to_infobip()[0].kwargs["json"]["content"]["text"])

    def test_reactions_and_malformed_payloads_do_not_crash(self):
        self.client.post(f"{self.URL}?secret={SECRET}", json=inbound("👍", mtype="REACTION"))
        self.assertEqual(self.sent_to_infobip(), [])
        for bad in ({}, {"results": "x"}, {"results": [1, None, {"from": "", "messageId": ""}]}, {"results": [{"from": "1"}]}):
            self.assertEqual(self.client.post(f"{self.URL}?secret={SECRET}", json=bad).status_code, 200)
        self.assertEqual(self.client.post(f"{self.URL}?secret={SECRET}", data="not json").status_code, 400)
        self.assertEqual(self.client.post(f"{self.URL}?secret={SECRET}", json=[1, 2]).status_code, 400)

    def test_infobip_failure_is_logged_and_never_breaks_the_webhook(self):
        with mock.patch("integrations.requests.post", side_effect=ConnectionError("down")):
            r = self.client.post(f"{self.URL}?secret={SECRET}", json=inbound())
        self.assertEqual(r.status_code, 200)
        log = self.db.recent_integration_logs(self.conn, 5)[0]
        self.assertEqual((log["service"], log["success"]), ("infobip", 0))
        self.assertIn("ConnectionError", log["detail"])

    def test_http_error_from_infobip_is_logged(self):
        bad = mock.Mock(ok=False, status_code=401, text='{"requestError":{"serviceException":{"text":"Invalid login details"}}}')
        with mock.patch("integrations.requests.post", return_value=bad):
            self.client.post(f"{self.URL}?secret={SECRET}", json=inbound())
        log = self.db.recent_integration_logs(self.conn, 5)[0]
        self.assertEqual((log["success"], log["status_code"]), (0, 401))
        self.assertIn("Invalid login", log["detail"])

    def test_reply_settings_missing_is_reported_not_crashed(self):
        with mock.patch.object(config, "INFOBIP_API_KEY", ""):
            self.client.post(f"{self.URL}?secret={SECRET}", json=inbound())
        log = self.db.recent_integration_logs(self.conn, 5)[0]
        self.assertIn("skipped", log["detail"])

    def test_a_noisy_number_is_rate_limited(self):
        import whatsapp
        with mock.patch.object(whatsapp, "RATE_PER_HOUR", 2):
            for i in range(4):
                self.client.post(f"{self.URL}?secret={SECRET}", json=inbound(mid=f"r{i}"))
        self.assertEqual(len(self.sent_to_infobip()), 2)

    def test_full_hand_off_over_whatsapp(self):
        self.configure_zapier()
        sent = []
        for i, text in enumerate(["what colour is the moon", "0", "Jane Doe", "skip"]):
            self.client.post(f"{self.URL}?secret={SECRET}", json=inbound(text, mid=f"c{i}"))
            sent.append(self.sent_to_infobip()[-1].kwargs["json"]["content"]["text"])
        self.assertIn("name", sent[1].lower())
        self.assertIn("(#1)", sent[3])
        self.assertEqual(self.db.list_escalations(self.conn)[0]["channel"], "whatsapp")

    def test_sender_digits_only_and_parse(self):
        import whatsapp
        self.assertEqual(whatsapp.sender(), "27800000000")
        self.assertEqual(whatsapp.base_url(), "abc123.api.infobip.com")
        got = whatsapp.parse_inbound(inbound("Hi", sender="+27 82 123 4567"))
        self.assertEqual(got[0]["from"], "27821234567")


# =========================================================================== API for an Infobip Answers chatbot
class AnswersApiTests(ChannelBase):
    URL = "/api/bot/message"

    def call(self, body, key=KEY, **kw):
        return self.client.post(self.URL, json=body, headers={"X-API-Key": key} if key else {}, **kw)

    def test_key_is_required(self):
        self.assertEqual(self.call({"user_id": "u1", "text": "hi"}, key=None).status_code, 401)
        self.assertEqual(self.call({"user_id": "u1", "text": "hi"}, key="nope").status_code, 401)
        with mock.patch.object(config, "BOT_API_KEY", ""):
            self.assertEqual(self.call({"user_id": "u1", "text": "hi"}).status_code, 503)

    def test_reply_shape_for_infobip_response_mapping(self):
        r = self.call({"user_id": "27821234567", "text": "how long until I hear back?"})
        d = r.get_json()
        self.assertEqual(r.status_code, 200)
        for key in ("ok", "reply", "handoff", "matched", "escalation_id"):
            self.assertIn(key, d)
        self.assertIn("14 business days", d["reply"])
        self.assertEqual(d["handoff"], "none")

    def test_conversation_continues_between_calls(self):
        self.call({"user_id": "27821234567", "text": "0"})
        self.call({"user_id": "27821234567", "text": "Sam"})
        self.call({"user_id": "27821234567", "text": "skip"})
        d = self.call({"user_id": "27821234567", "text": "Please call me about my application"}).get_json()
        self.assertEqual(d["handoff"], "submitted")
        self.assertEqual(self.db.list_escalations(self.conn)[0]["channel"], "api")

    def test_bad_requests(self):
        self.assertEqual(self.call({"text": "hi"}).status_code, 400)
        self.assertEqual(self.client.post(self.URL, data="x", headers={"X-API-Key": KEY}).status_code, 400)

    def test_session_id_is_accepted_as_the_user_id(self):
        self.assertEqual(self.call({"session_id": "abc", "text": "hello"}).status_code, 200)

    def test_rate_limit_per_user(self):
        calls = [self.call({"user_id": "u9", "text": "hello"}).status_code for _ in range(122)]
        self.assertEqual(calls[:120], [200] * 120)
        self.assertEqual(calls[120:], [429, 429])


# =========================================================================== website widget
class WidgetTests(ChannelBase):
    def test_widget_page_and_embed_script(self):
        page = self.client.get("/chat-widget")
        html = page.get_data(as_text=True)
        self.assertEqual(page.status_code, 200)
        self.assertIn('id="chat-panel"', html)
        self.assertIn("widget.js", html)
        self.assertNotIn("Recruiter login", html)                 # no site header inside the frame
        js = self.client.get("/static/embed.js").get_data(as_text=True)
        self.assertIn("/chat-widget", js)
        self.assertIn("tt-chat-close", js)

    def test_widget_may_be_framed_by_any_site_by_default_but_nothing_else_may(self):
        self.assertEqual(self.client.get("/chat-widget").headers["Content-Security-Policy"], "frame-ancestors *")
        for path in ("/", "/admin/login"):
            self.assertEqual(self.client.get(path).headers["Content-Security-Policy"], "frame-ancestors 'self'", path)

    def test_embedding_can_be_limited_to_your_sites(self):
        with mock.patch.object(config, "EMBED_ALLOWED_ORIGINS", "https://www.example.org, https://shop.example.org evil;script"):
            csp = self.client.get("/chat-widget").headers["Content-Security-Policy"]
        self.assertEqual(csp, "frame-ancestors 'self' https://www.example.org https://shop.example.org")

    def test_widget_chat_works_from_the_frame(self):
        r = self.client.post("/api/chat", json={"message": "how long until I hear back?"})
        self.assertIn("14", r.get_json()["answer"])

    def test_admin_chatbot_page_shows_the_setup_snippets_without_secrets(self):
        self.client.post("/admin/login", data={"password": "0000"})
        html = self.client.get("/admin/faq").get_data(as_text=True)
        self.assertIn("/static/embed.js", html)
        self.assertIn("/webhooks/infobip/whatsapp?secret=YOUR_SECRET", html)
        self.assertIn("/api/bot/message", html)
        for secret in (SECRET, KEY, "infobip-key"):
            self.assertNotIn(secret, html)

    def test_integrations_page_reports_channel_settings_without_secrets(self):
        self.client.post("/admin/login", data={"password": "0000"})
        html = self.client.get("/admin/integrations").get_data(as_text=True)
        self.assertIn("WhatsApp through Infobip", html)
        for secret in (SECRET, KEY, "infobip-key"):
            self.assertNotIn(secret, html)

    def test_requests_page_shows_whatsapp_requests(self):
        self.say("0")
        self.say("Jane")
        self.say("skip")
        self.say("Please call me about my application")
        self.client.post("/admin/login", data={"password": "0000"})
        html = self.client.get("/admin/requests").get_data(as_text=True)
        self.assertIn("WhatsApp", html)
        self.assertIn("27821234567", html)
        self.assertIn("no email given", html)


class MigrationTests(Base):
    def test_old_database_gets_the_new_escalation_columns(self):
        import sqlite3
        path = os.path.join(self.tmp.name, "old.db")
        old = sqlite3.connect(path)
        old.executescript("CREATE TABLE escalations (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, "
                          "email TEXT NOT NULL, message TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Open', "
                          "note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, resolved_at TEXT NOT NULL DEFAULT '');"
                          "INSERT INTO escalations(name, email, message, created_at) VALUES ('A','a@b.co','hello there','2026-01-01');")
        old.commit()
        old.close()
        self.db.init_db(path)
        conn = self.db.get_conn(path)
        row = dict(conn.execute("SELECT * FROM escalations").fetchone())
        conn.close()
        self.assertEqual((row["channel"], row["contact"], row["name"]), ("web", "", "A"))


if __name__ == "__main__":
    unittest.main()
