"""Zapier is the ONLY outside service this app talks to for messages.

Every email the portal "sends" is really a webhook POST to your Zapier Catch Hook. The JSON payload carries the
finished email (`email_to`, `email_subject`, `email_body`) and a `send_email` flag, and your Zap's Gmail / Outlook /
Email step actually delivers it. Every sender returns a result dict and NEVER raises, so a failing integration can
never block screening or any recruiter action. Every attempt is logged to `integrations_log`.

EVENTS (the `event` field)                 send_email   email goes to
    application_received                      yes        the candidate ("we received your application ... 14 business days")
    recruiter_notification                    yes        RECRUITMENT_LEAD_EMAIL (summary + score) - only if that is set
    human_escalation                          yes        RECRUITMENT_LEAD_EMAIL (a chat visitor asked for a person) - only if set
    human_escalation_ack                      yes        the visitor ("we passed your question to the recruitment team")
    shortlist_email                           yes        the candidate (congratulations, interview in 5 business days, Google Meet)
    selection_email                           yes        the candidate - stage set to "Selected" (congratulations and next steps)
    rejection_email                           yes        the candidate - stage set to "Not selected" (a respectful decline)
    intern_welcome_email                      yes        the intern (their personal page link)
    application_rescreened / stage_changed
    intern_placed / test                      no         (data only - for Google Sheets, Slack, etc.)
    test_email                                yes        the address typed on the Integrations page
"""
from __future__ import annotations

import re

import requests

try:  # Optional: on networks that inspect HTTPS (company, school, antivirus) use the Windows/macOS trust store
    import truststore  # pip install truststore
    truststore.inject_into_ssl()
except Exception:  # noqa: BLE001 - not installed or not supported: carry on with the normal certificates
    pass

import config
import database as db
import emails


# --------------------------------------------------------------------------- helpers
def _result(service: str, action: str, success: bool, status_code=None, detail: str = "") -> dict:
    return {"service": service, "action": action, "success": success,
            "status_code": status_code, "detail": (detail or "")[:1000]}


def _skipped(service: str, action: str, why: str) -> dict:
    return _result(service, action, False, None, f"skipped: {why}")


def normalise_phone(raw: str) -> str:
    """Digits-only international number without '+', or '' if it cannot be made valid.
    A leading 0 is converted with DEFAULT_COUNTRY_CODE (e.g. 27)."""
    digits = re.sub(r"[^\d+]", "", raw or "")
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if digits.startswith("+"):
        digits = digits[1:]
    elif digits.startswith("0"):
        cc = config.env("DEFAULT_COUNTRY_CODE")
        if not cc:
            return ""
        digits = cc + digits[1:]
    return digits if 8 <= len(digits) <= 15 and digits.isdigit() else ""


# --------------------------------------------------------------------------- Zapier
def send_zapier(payload: dict, action: str = "webhook") -> dict:
    """POST one JSON payload to the Catch Hook. Success means Zapier ACCEPTED it (HTTP 2xx);
    the Zap itself then sends the email, and its run history shows whether that worked."""
    if not config.ZAPIER_WEBHOOK_URL:
        return _skipped("zapier", action, "ZAPIER_WEBHOOK_URL not set")
    try:
        r = requests.post(config.ZAPIER_WEBHOOK_URL, json=payload, timeout=config.HTTP_TIMEOUT)
        return _result("zapier", action, r.ok, r.status_code, r.text[:300])
    except Exception as exc:  # noqa: BLE001 - never block the app
        return _result("zapier", action, False, None, f"{type(exc).__name__}: {exc}")


def zapier_payload(candidate: dict, result: dict, timestamp: str, event: str, email: dict | None = None) -> dict:
    """Flat JSON (Zapier maps flat fields most easily). `email` = {"to", "subject", "body"} or None.
    `send_email` is "yes" only when there is a recipient - add a Zap Filter: send_email exactly matches yes."""
    email = email or {}
    to = (email.get("to") or "").strip()
    return {
        "event": event,
        "send_email": "yes" if to else "no",
        "email_to": to,
        "email_subject": email.get("subject", "") if to else "",
        "email_body": email.get("body", "") if to else "",
        "candidate_name": candidate["name"],
        "email": candidate["email"],
        "phone": candidate.get("phone", ""),
        "phone_international": normalise_phone(candidate.get("phone", "")),
        "position": result["position"],
        "score": result["score"],
        "status": result["status"],
        "stage": candidate.get("stage", ""),
        "preferred_department": candidate.get("preferred_department", ""),
        "notes": result["notes"],
        "timestamp": timestamp,
    }


# --------------------------------------------------------------------------- orchestration
def record(conn, res: dict, candidate_id=None, screening_id=None) -> dict:
    """Write one result to integrations_log (never raises) and return it."""
    try:
        db.log_integration(conn, candidate_id=candidate_id, screening_id=screening_id,
                           service=res["service"], action=res["action"], success=res["success"],
                           status_code=res["status_code"], detail=res["detail"])
    except Exception:  # noqa: BLE001
        pass
    return res


def run_logged(conn, attempt, candidate_id=None, screening_id=None) -> dict:
    try:
        res = attempt()
    except Exception as exc:  # noqa: BLE001 - belt and braces
        res = _result("unknown", "unknown", False, None, f"{type(exc).__name__}: {exc}")
    return record(conn, res, candidate_id, screening_id)


def notify_application(conn, candidate: dict, result: dict, screening_id: int | None, timestamp: str,
                       *, notify_candidate: bool = True) -> list[dict]:
    """On every screening, send up to two webhooks:
    1. application_received (email to the candidate) - or application_rescreened (no email) on a re-screen
    2. recruiter_notification (email to the recruitment lead), if RECRUITMENT_LEAD_EMAIL is set."""
    cid = candidate.get("id")
    attempts = []
    if notify_candidate:
        subject, body = emails.application_received(candidate)
        event = "application_received"
        payload = zapier_payload(candidate, result, timestamp, event,
                                 {"to": candidate["email"], "subject": subject, "body": body})
    else:
        event = "application_rescreened"
        payload = zapier_payload(candidate, result, timestamp, event)
    attempts.append(lambda: send_zapier(payload, action=event))
    if config.RECRUITMENT_LEAD_EMAIL:
        lead_subject, lead_body = emails.lead_summary(candidate, result, screening_id)
        lead = zapier_payload(candidate, result, timestamp, "recruiter_notification",
                              {"to": config.RECRUITMENT_LEAD_EMAIL, "subject": lead_subject, "body": lead_body})
        attempts.append(lambda: send_zapier(lead, action="recruiter_notification"))
    return [run_logged(conn, a, cid, screening_id) for a in attempts]


def notify_event(conn, candidate: dict, result: dict, event: str) -> dict:
    """A data-only Zapier event (stage_changed, intern_placed, ...). No email is attached."""
    return run_logged(conn, lambda: send_zapier(zapier_payload(candidate, result, db.now_iso(), event), action=event),
                      candidate.get("id"))


def send_candidate_email(conn, candidate: dict, result: dict, subject: str, body: str, event: str) -> dict:
    """Hand one finished email to Zapier (event = shortlist_email | selection_email | rejection_email | intern_welcome_email)."""
    payload = zapier_payload(candidate, result, db.now_iso(), event,
                             {"to": candidate["email"], "subject": subject, "body": body})
    return run_logged(conn, lambda: send_zapier(payload, action=event), candidate.get("id"))


def send_message_event(conn, event: str, to: str, subject: str, body: str, **extra) -> dict:
    """A webhook that is only an email (no candidate), e.g. human_escalation. `extra` fields are added as-is."""
    to = (to or "").strip()
    payload = {"event": event, "send_email": "yes" if to else "no", "email_to": to,
               "email_subject": subject if to else "", "email_body": body if to else "",
               "timestamp": db.now_iso(), **extra}
    return run_logged(conn, lambda: send_zapier(payload, action=event) if to
                      else _skipped("zapier", event, "no recipient email address"))


# --------------------------------------------------------------------------- test buttons
_SAMPLE = {"name": "Test Candidate", "email": "test@example.org", "phone": "", "stage": "Applied",
           "preferred_department": ""}
_SAMPLE_RESULT = {"position": "Research Fellow", "score": 99.9, "status": "Pass",
                  "notes": "Test payload from the Integrations page."}


def test_zapier() -> dict:
    """Data-only sample so Zapier can detect every field (send_email = no)."""
    return send_zapier({**zapier_payload(_SAMPLE, _SAMPLE_RESULT, db.now_iso(), "test"), "test": True}, action="test")


def test_email(to: str = "") -> dict:
    """A real email through your Zap: to the address given, else RECRUITMENT_LEAD_EMAIL."""
    to = (to or config.RECRUITMENT_LEAD_EMAIL).strip()
    if not to:
        return _skipped("zapier", "test_email", "no recipient email address")
    org = config.ORGANISATION_NAME
    return send_zapier({**zapier_payload(
        _SAMPLE, _SAMPLE_RESULT, db.now_iso(), "test_email",
        {"to": to, "subject": f"[{org}] Test email from the recruitment portal",
         "body": f"This is a test email sent through Zapier by the {org} recruitment portal.\n"
                 f"If you can read this, your Zap is delivering the portal's emails correctly."}),
        "test": True}, action="test_email")
