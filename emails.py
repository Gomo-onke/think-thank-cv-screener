"""All candidate- and recruiter-facing message wording in one place (edit freely)."""
from __future__ import annotations

import config


def _first(name: str) -> str:
    return (name or "").strip().split(" ")[0] or "there"


def application_received(candidate: dict) -> tuple[str, str]:
    """Automatic email to every applicant."""
    org, pos = config.ORGANISATION_NAME, candidate["position"]
    subject = f"We have received your application for {pos}"
    body = (
        f"Dear {candidate['name'].strip()},\n\n"
        f"Thank you for applying for the {pos} role at {org}. We are pleased to confirm that your "
        f"application has been received successfully.\n\n"
        f"Our recruitment team will now review it, and a recruitment agent will contact you by email "
        f"if your application is taken forward.\n\n"
        f"Please note: if you do not hear from {org} within {config.RESPONSE_WINDOW_BUSINESS_DAYS} "
        f"business days of submitting your application, please consider your application "
        f"unsuccessful on this occasion. Because of the number of applications we receive, we may not "
        f"be able to reply to every applicant individually.\n\n"
        f"Thank you for your interest in working with us, and we wish you every success.\n\n"
        f"Kind regards,\nThe Recruitment Team\n{org}\n"
    )
    return subject, body


def shortlisted(candidate: dict, interview_when: str = "", meet_link: str = "") -> tuple[str, str]:
    """Sent when a recruiter presses the shortlist button."""
    org, pos = config.ORGANISATION_NAME, candidate["position"]
    subject = f"Congratulations - you have been shortlisted for {pos}"
    lines = [
        f"Dear {candidate['name'].strip()},",
        "",
        f"Congratulations! Following the review of your application for the {pos} role at {org}, "
        f"we are delighted to tell you that you have been shortlisted.",
        "",
        f"We would like to invite you to an interview within the next "
        f"{config.INTERVIEW_WINDOW_BUSINESS_DAYS} business days. The interview will take place as a "
        f"Google Meet video call.",
        "",
    ]
    if interview_when:
        lines.append(f"Interview date and time: {interview_when}")
    if meet_link:
        lines.append(f"Join the Google Meet call: {meet_link}")
    if not interview_when and not meet_link:
        lines.append("We will send you the exact date, time and Google Meet link shortly.")
    elif not interview_when:
        lines.append("We will confirm the exact date and time shortly.")
    elif not meet_link:
        lines.append("We will send you the Google Meet link before the interview.")
    lines += [
        "",
        "To get the most out of the call, please join from a quiet place with a stable internet connection, "
        "test your camera and microphone beforehand, and keep your CV to hand.",
        "",
        "Please reply to this email to confirm that you are available. We look forward to speaking with you.",
        "",
        "Kind regards,",
        "The Recruitment Team",
        org,
        "",
    ]
    return subject, "\n".join(lines)


def selected(candidate: dict, interviewed: bool = True) -> tuple[str, str]:
    """Sent when the stage is set to "Selected" (the candidate got the job)."""
    org, pos = config.ORGANISATION_NAME, candidate["position"]
    after = "your interview" if interviewed else "our review of your application"
    lines = [
        f"Dear {candidate['name'].strip()},",
        "",
        f"Congratulations! Following {after}, we are delighted to tell you that you have been selected "
        f"for the {pos} role at {org}. Well done, and thank you for the time and effort you put into the process.",
        "",
        "What happens next:",
        "- Our recruitment team will send you your formal offer, which confirms your start date, working hours, "
        "where you will work and the other terms of your employment.",
        "- You will usually be asked for a copy of your ID, your qualifications, your bank details and contact "
        "details for references. The offer email will confirm the exact list.",
        "- Please reply to this email to confirm that you are happy to proceed, and tell us if anything about "
        "your availability has changed.",
    ]
    if pos == config.INTERN_POSITION:
        lines += ["- As an intern you will be placed in a department. We will send you a personal link where you can "
                  "read updates from your supervisor and see the courses we recommend for you."]
    lines += [
        "",
        f"We are excited to welcome you to {org}. If you have any questions in the meantime, simply reply to "
        "this email.",
        "",
        "Kind regards,",
        "The Recruitment Team",
        org,
        "",
    ]
    return f"Congratulations - you have been selected for {pos}", "\n".join(lines)


def not_selected(candidate: dict, interviewed: bool = True) -> tuple[str, str]:
    """Sent when the stage is set to "Not selected" (the candidate did not get the job)."""
    org, pos = config.ORGANISATION_NAME, candidate["position"]
    lines = [
        f"Dear {candidate['name'].strip()},",
        "",
        f"Thank you for your interest in the {pos} role at {org}, and for the time you invested in "
        + ("your interview with us." if interviewed else "applying."),
        "",
        "After careful consideration, we have decided not to take your application forward on this occasion. "
        "We received applications from many capable people, and this was not an easy decision.",
        "",
        "This is not a reflection of your worth as a professional. We encourage you to keep an eye on our "
        "openings and to apply again in future, and we wish you every success in your search.",
        "",
        "If you have a question about your application, you are welcome to reply to this email.",
        "",
        "Kind regards,",
        "The Recruitment Team",
        org,
        "",
    ]
    return f"Your application for {pos} at {org}", "\n".join(lines)


def intern_welcome(candidate: dict, department: str, hub_link: str, start_date: str = "") -> tuple[str, str]:
    org = config.ORGANISATION_NAME
    subject = f"Welcome to {org} - your internship page"
    start = f"Your start date is {start_date}.\n\n" if start_date else ""
    body = (
        f"Dear {candidate['name'].strip()},\n\n"
        f"Congratulations and welcome to {org}! You have been placed in our {department} department.\n\n"
        f"{start}"
        f"We have created a personal page for you. It shows your department, updates from the team under your "
        f"name, and the courses we recommend to help you grow in your role:\n\n{hub_link}\n\n"
        f"Please keep this link private - it is just for you. Check it regularly, because we will post "
        f"updates there.\n\n"
        f"Kind regards,\nThe Recruitment Team\n{org}\n"
    )
    return subject, body


def lead_summary(candidate: dict, result: dict, screening_id: int | None) -> tuple[str, str]:
    """Internal email to the recruitment lead for every application."""
    subject = (f"[Recruitment] {result['status']}: {candidate['name']} - {result['position']} "
               f"({result['score']}/100)")
    lines = [
        f"Candidate: {candidate['name']} <{candidate['email']}>",
        f"Phone: {candidate.get('phone') or 'n/a'}   Location: {candidate.get('location') or 'n/a'}",
        f"Position: {result['position']}",
        f"Score: {result['score']}/100   Decision: {result['status']}",
        f"Education detected: {result['education_found']} (required: {result['education_required']})",
        f"Experience detected: {result['years_found']:g} yrs (required: {result['min_years']:g})",
        f"Required keywords found: {', '.join(result['required_found']) or 'none'}",
        f"Required keywords missing: {', '.join(result['required_missing']) or 'none'}",
        f"Preferred keywords found: {', '.join(result['preferred_found']) or 'none'}",
        "",
        f"Notes: {result['notes']}",
    ]
    if candidate.get("preferred_department"):
        lines.insert(3, f"Preferred department: {candidate['preferred_department']}")
    if screening_id:
        lines.append(f"Screening ID: {screening_id}")
    return subject, "\n".join(lines)


def escalation_to_recruiter(name: str, email: str, message: str, escalation_id: int,
                            channel: str = "web", contact: str = "") -> tuple[str, str]:
    """Internal email: a chat visitor asked the chatbot for a human."""
    where = {"whatsapp": "WhatsApp", "api": "the chatbot"}.get(channel, "the website chat")
    subject = f"[Recruitment] Chat request #{escalation_id} from {name}"
    lines = [f"A visitor asked to speak to a recruiter through {where}.", "", f"Name: {name}"]
    lines.append(f"Email: {email}" if email else "Email: (not given)")
    if contact:
        lines.append(f"{'WhatsApp number' if channel == 'whatsapp' else 'Chat user id'}: {contact}")
    lines += ["", "Their question:", message, ""]
    how = "by email" if email else ("on WhatsApp" if channel == "whatsapp" else "using the contact above")
    lines.append(f"Reply to them {how}, then mark request #{escalation_id} as resolved under Admin > Requests.")
    return subject, "\n".join(lines)


def escalation_ack(name: str) -> tuple[str, str]:
    """Automatic acknowledgement to the visitor."""
    org = config.ORGANISATION_NAME
    subject = f"We have received your question - {org}"
    body = (f"Dear {_first(name)},\n\n"
            f"Thank you for contacting {org}. We have passed your question to our recruitment team and a member "
            f"of the team will reply to you by email.\n\n"
            f"Kind regards,\nThe Recruitment Team\n{org}\n")
    return subject, body
