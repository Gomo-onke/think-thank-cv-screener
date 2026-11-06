"""Emails sent when the hiring stage becomes "Selected" or "Not selected"."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_portal as tp  # noqa: E402

import emails  # noqa: E402
import service  # noqa: E402


class StageEmailTests(tp.FlaskBase):
    def candidate(self, **over):
        out = service.apply(self.conn, {**tp.FORM, **over}, cv_text=tp.GOOD_CV)
        return out["candidate_id"]

    def set_stage(self, cid, stage, tick=True, follow=False):
        data = {"stage": stage}
        if tick:
            data["send_email"] = "yes"
        return self.client.post(f"/admin/candidates/{cid}/stage", data=data, follow_redirects=follow)

    def mails(self):
        return [p for p in self.payloads(self.post) if p["send_email"] == "yes" and p["event"] in ("selection_email", "rejection_email")]

    def setUp(self):
        super().setUp()
        self.login()
        self.configure_zapier()

    def test_selected_sends_the_congratulations_email(self):
        cid = self.candidate()
        self.set_stage(cid, "Selected")
        (m,) = self.mails()
        self.assertEqual((m["event"], m["email_to"], m["stage"]), ("selection_email", "jane@example.org", "Selected"))
        self.assertIn("selected", m["email_subject"].lower())
        self.assertIn("Dear Jane Doe", m["email_body"])
        self.assertIn("Data Analyst", m["email_body"])
        self.assertIn("formal offer", m["email_body"])
        self.assertNotIn("not to take your application forward", m["email_body"])

    def test_not_selected_sends_the_decline_email(self):
        cid = self.candidate()
        self.set_stage(cid, "Not selected")
        (m,) = self.mails()
        self.assertEqual((m["event"], m["email_to"]), ("rejection_email", "jane@example.org"))
        self.assertIn("not to take your application forward", m["email_body"])
        self.assertNotIn("Congratulations", m["email_body"])
        self.assertNotIn("Congratulations", m["email_subject"])

    def test_wording_depends_on_whether_there_was_an_interview(self):
        c = {"name": "A B", "position": "Data Analyst"}
        self.assertIn("your interview", emails.selected(c, True)[1])
        self.assertIn("our review of your application", emails.selected(c, False)[1])
        self.assertIn("your interview with us", emails.not_selected(c, True)[1])
        self.assertNotIn("interview", emails.not_selected(c, False)[1])

    def test_interview_recorded_changes_the_wording(self):
        cid = self.candidate()
        service.save_interview(self.conn, cid, {"interviewer": "Sam", "skills_rating": 4, "communication_rating": 4,
                                                "culture_rating": 4, "overall_rating": 4, "interview_date": "2026-11-01", "recommendation": "Yes"})
        self.set_stage(cid, "Selected")
        self.assertIn("your interview", self.mails()[0]["email_body"])

    def test_intern_gets_the_personal_page_paragraph(self):
        import config
        self.assertIn("personal link", emails.selected({"name": "A", "position": config.INTERN_POSITION})[1])
        self.assertNotIn("personal link", emails.selected({"name": "A", "position": "Data Analyst"})[1])

    def test_no_email_when_the_box_is_not_ticked_or_for_other_stages(self):
        cid = self.candidate()
        self.set_stage(cid, "Selected", tick=False)
        self.set_stage(cid, "Interviewed", tick=True)
        self.set_stage(cid, "Interview invited", tick=True)
        self.assertEqual(self.mails(), [])

    def test_each_email_is_sent_only_once(self):
        cid = self.candidate()
        self.set_stage(cid, "Selected")
        self.set_stage(cid, "Selected")
        self.set_stage(cid, "Interviewed", tick=False)
        r = self.set_stage(cid, "Selected", follow=True)
        self.assertEqual(len(self.mails()), 1)
        self.assertIn("already sent", r.get_data(as_text=True))

    def test_the_opposite_email_is_refused(self):
        cid = self.candidate()
        self.set_stage(cid, "Selected")
        r = self.set_stage(cid, "Not selected", follow=True)
        self.assertEqual([m["event"] for m in self.mails()], ["selection_email"])
        self.assertIn("contact them directly", r.get_data(as_text=True))
        self.assertEqual(self.db.get_candidate(self.conn, cid)["stage"], "Not selected")   # the stage change itself is allowed

    def test_failed_send_is_reported_and_can_be_retried(self):
        import config
        from unittest import mock
        cid = self.candidate()
        with mock.patch.object(config, "ZAPIER_WEBHOOK_URL", ""):
            r = self.set_stage(cid, "Not selected", follow=True)
        self.assertIn("email was NOT sent", r.get_data(as_text=True))
        self.assertEqual(self.mails(), [])
        self.assertEqual(self.db.get_candidate(self.conn, cid)["stage"], "Not selected")
        r = self.set_stage(cid, "Not selected", follow=True)                      # Zapier is configured again: retry
        self.assertEqual(len(self.mails()), 1)
        self.assertIn("Email sent to the candidate", r.get_data(as_text=True))

    def test_candidate_page_offers_the_tick_box_and_shows_what_was_sent(self):
        cid = self.candidate()
        html = self.client.get(f"/admin/candidates/{cid}").get_data(as_text=True)
        self.assertIn('name="send_email"', html)
        self.assertIn('data-email="selection"', html)
        self.assertIn('data-email="not selected"', html)
        self.assertNotIn("email already sent", html)
        self.set_stage(cid, "Selected")
        self.assertIn("Selection email already sent", self.client.get(f"/admin/candidates/{cid}").get_data(as_text=True))

    def test_service_default_sends_nothing(self):
        cid = self.candidate()
        out = service.set_stage(self.conn, cid, "Selected")
        self.assertEqual((out["changed"], out["email"]), (True, None))
        self.assertEqual(self.mails(), [])
        with self.assertRaises(service.ServiceError):
            service.send_outcome_email(self.conn, self.candidate(email="x@example.org"))     # stage Applied: not allowed

    def test_stage_email_failure_never_loses_the_stage_change(self):
        from unittest import mock
        cid = self.candidate()
        with mock.patch("integrations.requests.post", side_effect=tp.fail_post):
            self.set_stage(cid, "Selected")
        self.assertEqual(self.db.get_candidate(self.conn, cid)["stage"], "Selected")


if __name__ == "__main__":
    import unittest
    unittest.main()
