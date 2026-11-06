"""Business actions, independent of Flask: apply -> screen -> save -> notify -> Excel,
plus shortlist emails, stages, interviews and intern placement."""
from __future__ import annotations

import re
from datetime import datetime

import config
import database as db
import emails
import excel_export
import integrations
import sheets
from screener import screen_cv

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_CV_CHARS = 30
MEET_PREFIX = "https://meet.google.com/"


class ServiceError(ValueError):
    """User-fixable problem; the message is shown verbatim in the UI."""


ScreeningError = ServiceError


def _clean(value, limit: int = 200) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _date(value: str, label: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ServiceError(f"{label} must be a valid date.") from None
    return value


def _choice(value: str, options, label: str, required: bool = False) -> str:
    value = (value or "").strip()
    if not value:
        if required:
            raise ServiceError(f"{label} is required.")
        return ""
    if value not in options:
        raise ServiceError(f"Please choose a valid option for {label.lower()}.")
    return value


def _url(value: str, label: str) -> str:
    value = (value or "").strip()
    if value and not re.match(r"^https?://\S+$", value):
        raise ServiceError(f"{label} must be a web address starting with https://")
    return value[:300]


# ------------------------------------------------------------------ Excel
def refresh_excel(conn) -> None:
    """Rewrite the Excel workbook. Never raises; a failure is logged and shown on the Integrations page."""
    try:
        excel_export.write_file(conn)
    except Exception as exc:  # noqa: BLE001
        integrations.record(conn, {"service": "excel", "action": "write", "success": False,
                                   "status_code": None, "detail": f"{type(exc).__name__}: {exc}"})


# ------------------------------------------------------------------ applying / screening
def _run(conn, candidate: dict, *, notify_candidate: bool) -> dict:
    position = db.get_position(conn, candidate["position"])
    if not position:
        raise ServiceError(f"Unknown position: {candidate['position']!r}")
    result = screen_cv(candidate["cv_text"], position, db.get_settings(conn))
    screening_id = db.add_screening(conn, candidate["id"], candidate["position"], result)
    ts = db.now_iso()
    notifications = integrations.notify_application(conn, candidate, result, screening_id, ts,
                                                    notify_candidate=notify_candidate)
    if sheets.sheets_configured():
        notifications.append(integrations.record(
            conn, sheets.append_result(candidate, result, ts), candidate["id"], screening_id))
    refresh_excel(conn)
    return {"candidate_id": candidate["id"], "screening_id": screening_id,
            "result": result, "notifications": notifications}


def apply(conn, form: dict, *, cv_text: str, cv_filename: str = "", source: str = "web",
          full_form: bool = True) -> dict:
    """Validate an application, save it, screen it and notify. `full_form=False` is used for
    Google Sheets rows, which only carry name/email/phone/position/cv."""
    g = lambda k, n=200: _clean(form.get(k, ""), n)  # noqa: E731
    name, email, phone = g("name"), g("email"), g("phone", 40)
    if not name:
        raise ServiceError("Full name is required.")
    if not EMAIL_RE.match(email):
        raise ServiceError("A valid email address is required.")
    if full_form and len(re.sub(r"\D", "", phone)) < 7:
        raise ServiceError("A valid phone number is required (include the country code).")
    position = g("position")
    if not db.get_position(conn, position):
        raise ServiceError("Please choose a valid position.")
    cv_text = (cv_text or "").strip()
    if len(cv_text) < MIN_CV_CHARS:
        raise ServiceError("The CV is empty or too short - upload a file or paste the CV text.")

    data = {"name": name, "email": email, "phone": phone, "position": position,
            "cv_text": cv_text, "cv_filename": cv_filename, "source": source}
    if full_form:
        if not str(form.get("consent", "")).strip():
            raise ServiceError("Please tick the box to consent to us processing your application.")
        years = g("years_experience", 10)
        if years:
            try:
                if not 0 <= float(years) <= 60:
                    raise ValueError
            except ValueError:
                raise ServiceError("Years of experience must be a number between 0 and 60.") from None
        dept = _choice(g("preferred_department"), list(config.DEPARTMENTS), "Preferred department")
        data.update({
            "location": g("location") or _raise("City / province is required."),
            "work_authorisation": _choice(g("work_authorisation"), config.WORK_AUTHORISATION,
                                          "Right to work", required=True),
            "highest_qualification": _choice(g("highest_qualification"), config.QUALIFICATIONS,
                                             "Highest qualification", required=True),
            "preferred_department": dept if position == config.INTERN_POSITION else "",
            "field_of_study": g("field_of_study"), "current_title": g("current_title"),
            "current_employer": g("current_employer"), "years_experience": years,
            "notice_period": _choice(g("notice_period"), config.NOTICE_PERIODS, "Notice period"),
            "available_from": _date(g("available_from", 10), "Available from"),
            "expected_salary": g("expected_salary", 60),
            "work_arrangement": _choice(g("work_arrangement"), config.WORK_ARRANGEMENTS, "Work arrangement"),
            "linkedin_url": _url(g("linkedin_url", 300), "LinkedIn address"),
            "portfolio_url": _url(g("portfolio_url", 300), "Portfolio address"),
            "referral_source": _choice(g("referral_source"), config.REFERRAL_SOURCES, "How you heard about us"),
            "cover_note": _clean(form.get("cover_note", ""), 2000),
            "consent_at": db.now_iso(),
        })
    cid = db.add_candidate(conn, **data)
    return _run(conn, db.get_candidate(conn, cid), notify_candidate=True)


def _raise(message: str):
    raise ServiceError(message)


def rescreen(conn, candidate_id: int, position: str | None = None) -> dict:
    """Re-run the stored CV against the current criteria. Notifies Zapier + the recruiter;
    the candidate is only messaged again if RESCREEN_NOTIFY_CANDIDATE=true."""
    candidate = db.get_candidate(conn, candidate_id)
    if not candidate:
        raise ServiceError("Candidate not found.")
    if position and position != candidate["position"]:
        if not db.get_position(conn, position):
            raise ServiceError(f"Unknown position: {position!r}")
        db.update_candidate(conn, candidate_id, position=position)
        candidate["position"] = position
    return _run(conn, candidate, notify_candidate=config.RESCREEN_NOTIFY_CANDIDATE)


def import_from_sheets(conn) -> dict:
    rows = sheets.fetch_unprocessed()
    done, errors = 0, []
    for row in rows:
        try:
            apply(conn, row, cv_text=row.get("cv_text", ""), source="sheets", full_form=False)
            sheets.mark_processed(row["_row"], db.now_iso())
            done += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"row {row['_row']}: {exc}")
    return {"found": len(rows), "screened": done, "errors": errors}


# ------------------------------------------------------------------ pipeline: shortlist, stages
def latest_result(conn, candidate_id: int) -> dict | None:
    hist = db.screening_history(conn, candidate_id)
    return {**hist[0]["breakdown"], "status": hist[0]["status"], "score": hist[0]["score"]} if hist else None


def can_send_shortlist(candidate: dict, status: str) -> bool:
    """Passed candidates, and anyone a recruiter shortlisted, until a final decision is made."""
    if candidate["stage"] in ("Selected", "Not selected"):
        return False
    return status == "Pass" or candidate["stage"] in config.SHORTLIST_ELIGIBLE_STAGES


# Stages that email the candidate (when the recruiter leaves "Email the candidate" ticked): stage -> Zapier event.
OUTCOME_EMAILS = {"Selected": "selection_email", "Not selected": "rejection_email"}


def set_stage(conn, candidate_id: int, stage: str, send_email: bool = False) -> dict:
    """Move a candidate to a stage. With send_email, "Selected" / "Not selected" also email the candidate.
    Returns {"changed": bool, "email": None | send_outcome_email's result}."""
    if stage not in config.STAGES:
        raise ServiceError("Unknown stage.")
    candidate = db.get_candidate(conn, candidate_id)
    if not candidate:
        raise ServiceError("Candidate not found.")
    changed = candidate["stage"] != stage
    if changed:
        db.update_candidate(conn, candidate_id, stage=stage)
        result = latest_result(conn, candidate_id)
        if result:
            integrations.notify_event(conn, db.get_candidate(conn, candidate_id), result, "stage_changed")
        refresh_excel(conn)
    email = None
    if send_email and stage in OUTCOME_EMAILS:
        email = send_outcome_email(conn, candidate_id)          # also retries a send that failed earlier
    return {"changed": changed, "email": email}


def send_outcome_email(conn, candidate_id: int) -> dict:
    """Email the candidate the result that matches their current stage: "Selected" (congratulations, next steps)
    or "Not selected" (a respectful decline). Returns {"sent", "already", "event", "result"}:
      * each email is sent only once per candidate ("already" = when it was sent), so pressing the button twice is safe;
      * if the OPPOSITE email was already sent, nothing is sent and the recruiter must contact the person directly."""
    candidate = db.get_candidate(conn, candidate_id)
    result = latest_result(conn, candidate_id) if candidate else None
    if not candidate or not result:
        raise ServiceError("Candidate not found.")
    event = OUTCOME_EMAILS.get(candidate["stage"])
    if not event:
        raise ServiceError('This email is only sent for the stages "Selected" and "Not selected".')
    opposite = next(e for e in OUTCOME_EMAILS.values() if e != event)
    if db.last_success(conn, candidate_id, [opposite]):
        raise ServiceError(f"{candidate['name']} was already sent the other result email. Please contact them directly "
                           "instead of sending a second, contradictory email.")
    before = db.last_success(conn, candidate_id, [event])
    if before:
        return {"sent": False, "already": before["created_at"], "event": event, "result": None}
    interviewed = bool(db.list_interviews(conn, candidate_id))
    build = emails.selected if event == "selection_email" else emails.not_selected
    subject, body = build(candidate, interviewed)
    res = integrations.send_candidate_email(conn, candidate, result, subject, body, event)
    return {"sent": res["success"], "already": "", "event": event, "result": res}


def send_shortlist_email(conn, candidate_id: int, interview_when: str = "", meet_link: str = "") -> dict:
    """The recruiter's "Send shortlist email" button. Returns {"sent": bool, "result": {...}}.
    The stage only moves to "Interview invited" if the email was really sent."""
    candidate = db.get_candidate(conn, candidate_id)
    result = latest_result(conn, candidate_id) if candidate else None
    if not candidate or not result:
        raise ServiceError("Candidate not found.")
    if not can_send_shortlist(candidate, result["status"]):
        raise ServiceError("Only candidates who passed (or that you have shortlisted) can be sent this email. "
                           "Set their stage to Shortlisted first.")
    interview_when = _clean(interview_when, 120)
    meet_link = (meet_link or "").strip()
    if meet_link and (not meet_link.startswith(MEET_PREFIX) or re.search(r"\s", meet_link) or len(meet_link) > 200):
        raise ServiceError("Please paste a Google Meet link (it starts with https://meet.google.com/).")

    subject, body = emails.shortlisted(candidate, interview_when, meet_link)
    res = integrations.send_candidate_email(conn, candidate, result, subject, body, "shortlist_email")
    if res["success"]:
        fields = {"shortlist_email_sent_at": db.now_iso(), "interview_when": interview_when,
                  "meet_link": meet_link}
        if candidate["stage"] in ("Applied", "Shortlisted", "Interview invited"):
            fields["stage"] = "Interview invited"
        db.update_candidate(conn, candidate_id, **fields)
        refresh_excel(conn)
    return {"sent": res["success"], "result": res}


# ------------------------------------------------------------------ interviews
def save_interview(conn, candidate_id: int, data: dict) -> int:
    candidate = db.get_candidate(conn, candidate_id)
    if not candidate:
        raise ServiceError("Candidate not found.")
    interviewer = _clean(data.get("interviewer"), 100)
    if not interviewer:
        raise ServiceError("Please enter the interviewer's name.")
    ratings = {}
    for key, label in (("skills_rating", "Skills"), ("communication_rating", "Communication"),
                       ("culture_rating", "Culture fit"), ("overall_rating", "Overall ranking")):
        try:
            ratings[key] = int(data.get(key))
            if not 1 <= ratings[key] <= 5:
                raise ValueError
        except (TypeError, ValueError):
            raise ServiceError(f"{label} must be a rating from 1 to 5.") from None
    recommendation = _choice(data.get("recommendation", ""), ["Yes", "Maybe", "No"],
                             "Is this the right person for the job?", required=True)
    iid = db.add_interview(conn, candidate_id, {
        "interviewer": interviewer, "interview_date": _date(data.get("interview_date", ""), "Interview date"),
        "recommendation": recommendation, "notes": str(data.get("notes", "")).strip()[:4000], **ratings})
    if candidate["stage"] in ("Applied", "Shortlisted", "Interview invited"):
        db.update_candidate(conn, candidate_id, stage="Interviewed")
    refresh_excel(conn)
    return iid


def remove_interview(conn, interview_id: int) -> None:
    db.delete_interview(conn, interview_id)
    refresh_excel(conn)


# ------------------------------------------------------------------ interns
def place_intern(conn, candidate_id: int, department: str, supervisor: str, start_date: str) -> tuple[int, bool]:
    candidate = db.get_candidate(conn, candidate_id)
    if not candidate:
        raise ServiceError("Candidate not found.")
    if candidate["position"] != config.INTERN_POSITION:
        raise ServiceError("Only candidates who applied as an Intern can be placed in a department.")
    if candidate["stage"] != "Selected":
        raise ServiceError("Select this intern first (open their interview page and choose \"Select for the job\").")
    if department not in config.DEPARTMENTS:
        raise ServiceError("Please choose a department.")
    intern_id, created = db.upsert_intern(conn, candidate_id, department, _clean(supervisor, 100),
                                          _date(start_date, "Start date"))
    if created:
        suggest_courses(conn, intern_id)
        result = latest_result(conn, candidate_id)
        if result:
            integrations.notify_event(conn, candidate, result, "intern_placed")
    refresh_excel(conn)
    return intern_id, created


def suggest_courses(conn, intern_id: int) -> int:
    """Add the department's starter courses that the intern does not have yet."""
    intern = db.get_intern(conn, intern_id)
    if not intern:
        raise ServiceError("Intern not found.")
    have = {c["title"] for c in db.list_intern_courses(conn, intern_id)}
    added = 0
    for title, provider, note in config.DEPARTMENTS.get(intern["department"], {}).get("courses", []):
        if title not in have:
            db.add_intern_course(conn, intern_id, title, provider, "", note)
            added += 1
    return added


def add_course(conn, intern_id: int, title: str, provider: str, link: str, note: str) -> None:
    title = _clean(title, 200)
    if not title:
        raise ServiceError("Course name is required.")
    db.add_intern_course(conn, intern_id, title, _clean(provider, 120), _url(link, "Course link"),
                         _clean(note, 300))


def add_update(conn, intern_id: int, message: str, author: str) -> None:
    message = (message or "").strip()
    if not message:
        raise ServiceError("Please write an update.")
    db.add_intern_update(conn, intern_id, message[:2000], _clean(author, 100))


def send_intern_welcome(conn, intern_id: int, base_url: str) -> dict:
    intern = db.get_intern(conn, intern_id)
    if not intern:
        raise ServiceError("Intern not found.")
    candidate = db.get_candidate(conn, intern["candidate_id"])
    link = f"{base_url.rstrip('/')}/intern/{intern['token']}"
    result = latest_result(conn, intern["candidate_id"])
    if not result:
        raise ServiceError("This intern has no screening result yet.")
    subject, body = emails.intern_welcome(candidate, intern["department"], link, intern["start_date"])
    res = integrations.send_candidate_email(conn, candidate, result, subject, body, "intern_welcome_email")
    return {"sent": res["success"], "result": res, "link": link}


# ------------------------------------------------------------------ human escalation (chatbot -> recruiter)
def request_human(conn, name: str, email: str, message: str, channel: str = "web", contact: str = "") -> dict:
    """A chat visitor asks the chatbot to hand their question to a person. The request is ALWAYS saved
    (so it can never be lost); the emails go out through Zapier and their result is reported separately.
    On the website an email address is required. On WhatsApp / API chats it is optional when `contact`
    (their WhatsApp number) lets the recruiter reply there."""
    name, email, message = _clean(name, 100), _clean(email, 200), _clean(message, 1000)
    contact = _clean(contact, 100)
    if not name:
        raise ServiceError("Please tell us your name.")
    if email:
        if not EMAIL_RE.match(email):
            raise ServiceError("Please enter a valid email address so we can reply.")
    elif channel == "web" or not contact:
        raise ServiceError("Please enter a valid email address so we can reply.")
    if len(message) < 5:
        raise ServiceError("Please type your question (at least a few words).")
    eid = db.add_escalation(conn, name, email, message, channel, contact)
    lead_subject, lead_body = emails.escalation_to_recruiter(name, email, message, eid, channel, contact)
    to_lead = integrations.send_message_event(conn, "human_escalation", config.RECRUITMENT_LEAD_EMAIL,
                                              lead_subject, lead_body, visitor_name=name, visitor_email=email,
                                              message=message, escalation_id=eid, channel=channel, contact=contact)
    acknowledged = False
    if email:
        ack_subject, ack_body = emails.escalation_ack(name)
        to_visitor = integrations.send_message_event(conn, "human_escalation_ack", email, ack_subject, ack_body,
                                                     visitor_name=name, visitor_email=email, escalation_id=eid)
        acknowledged = to_visitor["success"]
    return {"id": eid, "recruiter_notified": to_lead["success"], "acknowledged": acknowledged}


def resolve_request(conn, escalation_id: int, note: str) -> None:
    db.resolve_escalation(conn, escalation_id, _clean(note, 500))
