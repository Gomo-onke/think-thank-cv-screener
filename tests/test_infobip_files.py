"""Tests for company information, the extra FAQ entries and the generated Infobip files."""
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "infobip"))

import chatbot  # noqa: E402
import config  # noqa: E402
import make_infobip_files as gen  # noqa: E402
from bot_content import INTENTS  # noqa: E402


class CompanyFaqTests(unittest.TestCase):
    def test_blank_company_info_adds_only_what_is_known(self):
        questions = [q for q, _a, _k in config.company_faq({k: "" for k in config.COMPANY})]
        self.assertEqual(questions, ["What positions are open?", "How do I apply?"])

    def test_filled_company_info_adds_answers_and_nothing_is_invented(self):
        info = {"about": "We build research software.", "services": "Data tools.", "location": "12 Long St, Cape Town",
                "hours": "Mon-Fri 08:00-17:00", "phone": "021 000 0000", "email": "hello@example.org", "website": "https://example.org"}
        faq = {q: a for q, a, _k in config.company_faq(info)}
        self.assertEqual(faq["What does {org} do?"], "We build research software.")
        self.assertIn("12 Long St", faq["Where is your office?"])
        contact = faq["What are your contact details?"]
        for part in ("021 000 0000", "hello@example.org", "https://example.org"):
            self.assertIn(part, contact)
        self.assertIn("https://example.org", faq["How do I apply?"])

    def test_open_positions_lists_the_real_positions(self):
        answer = dict((q, a) for q, a, _k in config.company_faq())["What positions are open?"]
        for name in ("Research Fellow", "Data Analyst", "Administrative Assistant"):
            self.assertIn(name, answer)

    def test_company_info_file_is_valid_and_blank_by_default(self):
        self.assertEqual(set(config.COMPANY), {"about", "services", "location", "hours", "phone", "email", "website"})

    def test_missing_or_broken_company_file_does_not_crash(self):
        with mock.patch.object(config.Path, "read_text", side_effect=OSError):
            self.assertTrue(all(v == "" for v in config._load_company().values()))


class MatcherTests(unittest.TestCase):
    FAQS = [{"id": i, "question": q, "answer": a, "keywords": k} for i, (q, a, k) in enumerate(config.DEFAULT_FAQ, 1)]

    def ask(self, text):
        r = chatbot.reply(text, self.FAQS)
        return next((q for i, (q, _a, _k) in enumerate(config.DEFAULT_FAQ, 1) if i == r["faq_id"]), None)

    def test_new_questions_are_found(self):
        self.assertEqual(self.ask("What jobs do you have"), "What positions are open?")
        self.assertEqual(self.ask("How do I apply for a job"), "How do I apply?")
        self.assertEqual(self.ask("Can I work remotely"), "Can I work remotely?")

    def test_stemming_helps_but_does_not_mangle(self):
        self.assertEqual(chatbot._stem("remotely"), "remote")
        self.assertEqual(chatbot._stem("applying"), "apply")
        self.assertEqual(chatbot._stem("jobs"), "job")
        self.assertEqual(chatbot._stem("boss"), "boss")
        self.assertEqual(chatbot._stem("family"), "family")

    def test_a_keyword_and_its_plural_do_not_count_twice(self):
        faqs = [{"id": 1, "question": "q", "answer": "a", "keywords": "job, jobs"},
                {"id": 2, "question": "q2", "answer": "a2", "keywords": "work, apply"}]
        self.assertEqual(chatbot.reply("I want a job and to apply", faqs)["faq_id"], 1)   # 3 vs 3: first wins, not 6 vs 3
        faqs[1]["keywords"] = "apply, job work"
        self.assertTrue(chatbot.reply("I want a job and to apply", faqs)["matched"])

    def test_no_dangling_email_phrase_without_a_recruitment_email(self):
        with mock.patch.object(config, "RECRUITMENT_LEAD_EMAIL", ""):
            self.assertEqual(chatbot.render("Please email the recruitment team at {hr_email}."),
                             "Please email the recruitment team.")
        with mock.patch.object(config, "RECRUITMENT_LEAD_EMAIL", "hr@example.org"):
            self.assertEqual(chatbot.render("Please email the recruitment team at {hr_email}."),
                             "Please email the recruitment team at hr@example.org.")


class GeneratedFilesTests(unittest.TestCase):
    def test_content_passes_validation(self):
        self.assertEqual(gen.validate(), [])

    def test_validation_catches_mistakes(self):
        bad = [dict(name="Bad name", faq=None, phrases=["a;b"] * 2, words=[])]
        with mock.patch.object(gen, "INTENTS", bad):
            problems = " ".join(gen.validate())
        self.assertIn("letters, digits and underscores", problems)
        self.assertIn("only 2 training phrases", problems)
        self.assertIn("';'", problems)

    def test_files_follow_infobips_import_format(self):
        got, missing = gen.answers()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(gen, "OUT", tmp):
            gen.write_files(got)
            lines = open(os.path.join(tmp, "1_intents_import.csv"), encoding="utf-8").read().splitlines()
            words = open(os.path.join(tmp, "2_important_words_import.csv"), encoding="utf-8").read().splitlines()
            md = open(os.path.join(tmp, "3_dialog_answers.md"), encoding="utf-8").read()
        self.assertTrue(lines and all(lines))                                  # no empty rows
        for line in lines:
            phrase, intent = line.split(";")                                    # exactly two fields, no header
            self.assertTrue(phrase and intent.replace("_", "").isalnum(), line)
            self.assertNotEqual(phrase, "Training_Phrase")
        for line in words:
            word, intent, syns = line.split(";")
            self.assertTrue(word and intent and syns, line)
        self.assertEqual({l.split(";")[1] for l in lines}, set(got))
        for name in got:
            self.assertIn(f"`{name}`", md)
        self.assertNotIn("{org}", md + "\n".join(lines))
        self.assertNotIn("{hr_email}", md)

    def test_intents_without_company_information_are_left_out_not_invented(self):
        with mock.patch.object(config, "DEFAULT_FAQ", [f for f in config.DEFAULT_FAQ if f[0] not in
                                                       ("What does {org} do?", "Where is your office?")]):
            got, missing = gen.answers()
        self.assertIn("About_Company", missing)
        self.assertNotIn("About_Company", got)
        self.assertIn("Welcome", got)

    def test_every_faq_intent_points_at_a_real_answer_when_company_info_is_full(self):
        full = {k: "x" for k in config.COMPANY}
        faq = list(config.DEFAULT_FAQ) + [f for f in config.company_faq(full) if f[0] not in {q for q, _a, _k in config.DEFAULT_FAQ}]
        with mock.patch.object(config, "DEFAULT_FAQ", faq):
            got, missing = gen.answers()
        self.assertEqual(missing, [])
        self.assertEqual(len(got), len(INTENTS))

    def test_sync_adds_missing_answers_and_can_refresh_keywords_without_touching_answers(self):
        import database as db
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(config, "DB_PATH", os.path.join(tmp, "t.db")):
            db.init_db()
            conn = db.get_conn()
            conn.execute("DELETE FROM faq WHERE question = 'How do I apply?'")
            conn.execute("UPDATE faq SET answer = 'MY OWN ANSWER', keywords = 'old' WHERE question = 'Can I work remotely?'")
            conn.commit()
            conn.close()
            gen.sync_portal()
            conn = db.get_conn()
            faq = {f["question"]: f for f in db.list_faq(conn)}
            self.assertIn("How do I apply?", faq)
            self.assertEqual(faq["Can I work remotely?"]["keywords"], "old")       # not refreshed without the flag
            conn.close()
            gen.sync_portal(refresh_keywords=True)
            conn = db.get_conn()
            faq = {f["question"]: f for f in db.list_faq(conn)}
            self.assertNotEqual(faq["Can I work remotely?"]["keywords"], "old")
            self.assertEqual(faq["Can I work remotely?"]["answer"], "MY OWN ANSWER")   # answers are never overwritten
            conn.close()


if __name__ == "__main__":
    unittest.main()
