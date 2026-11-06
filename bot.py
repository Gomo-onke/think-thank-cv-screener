"""One chatbot conversation for every TEXT channel (WhatsApp, a chatbot builder that calls our API, any other chat).

The website widget talks to /api/chat and uses buttons. WhatsApp has no custom buttons in a plain text reply, so this
module turns the same FAQ bot (chatbot.py) into a short text conversation:

    * answers frequent questions and lists numbered follow-up questions (type 1-5 to pick one),
    * type 0 (or "talk to a person") to hand the question to the recruitment team. The bot then asks for a name,
      an email address (optional on WhatsApp, because we already have the number) and the question, and saves the
      request exactly like the website does (Admin > Requests, plus the two Zapier emails).

Where the user is in that hand-off is remembered in the `bot_sessions` table, so the bot survives restarts and
several workers. A session that has been quiet for 30 minutes starts again from the beginning.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

import chatbot
import config
import database as db
import integrations
import service

IDLE, ASK_NAME, ASK_EMAIL, ASK_MESSAGE = "idle", "ask_name", "ask_email", "ask_message"
SESSION_TTL_SECONDS = 30 * 60
MAX_INPUT = 1000
PRIVACY_NOTE = "(Automated assistant. Please do not send ID numbers or passwords here.)\n\n"
CANCEL = {"cancel", "stop", "menu", "back", "restart", "start over"}
SKIP = {"skip", "no email", "none", "n/a", "-"}
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def _expired(updated_at: str) -> bool:
    try:
        then = datetime.fromisoformat(updated_at)
    except ValueError:
        return True
    return (datetime.now(timezone.utc) - then).total_seconds() > SESSION_TTL_SECONDS


def _menu_text(menu: list[str], with_human: bool = True) -> str:
    lines = ["You can ask me:"] + [f"{i}. {q}" for i, q in enumerate(menu, start=1)]
    if with_human:
        lines.append("0. Talk to a recruiter")
    return "\n".join(lines)


def _contact_for(channel: str, user_id: str) -> str:
    """Something the recruiter can reply to: the WhatsApp number (or a phone-like chat id), else nothing."""
    if channel == "whatsapp" or integrations.normalise_phone(user_id):
        return user_id
    return ""


def _result(reply: str, state: str = "none", matched: bool = True, escalation_id: int | None = None) -> dict:
    return {"reply": reply, "handoff": state, "matched": matched, "escalation_id": escalation_id}


def handle(conn, channel: str, user_id: str, text: str) -> dict:
    """Process one message from one user. Returns {"reply", "handoff", "matched", "escalation_id"}
    where handoff is "none" (normal chat), "asking" (collecting details) or "submitted" (request saved)."""
    user_id = str(user_id or "").strip()[:100]
    if not user_id:
        raise ValueError("user_id is required")
    text = re.sub(r"\s+", " ", str(text or "")).strip()[:MAX_INPUT]
    session = db.get_bot_session(conn, channel, user_id)
    state, data = session["state"], dict(session["data"])
    if state != IDLE and _expired(session["updated_at"]):
        state, data = IDLE, {}

    if not text:
        return _result("Please type a question, or 0 to talk to a recruiter.", "asking" if state != IDLE else "none")

    low = text.lower().strip(" .!?")

    # ----------------------------------------------------------------- hand-off conversation
    if state != IDLE:
        if low in CANCEL:
            db.save_bot_session(conn, channel, user_id, IDLE, {"menu": data.get("menu", [])})
            return _result("No problem, I have cancelled that. " + _menu_text(data.get("menu") or
                           chatbot.suggestions(db.list_faq(conn))))
        return _handoff_step(conn, channel, user_id, state, data, text, low)

    # ----------------------------------------------------------------- normal chat
    faqs = db.list_faq(conn)
    menu = data.get("menu") or chatbot.suggestions(faqs)
    if low == "0":
        return _start_handoff(conn, channel, user_id, data)
    if low.isdigit() and 1 <= int(low) <= len(menu):
        text = menu[int(low) - 1]

    first_visit = not session["updated_at"]               # never chatted before: add the privacy note once
    r = chatbot.reply(text, faqs)
    if r["faq_id"] is not None or not r["matched"]:       # not greetings / thanks (same rule as the website)
        db.log_chat(conn, text, r["matched"])

    if r["escalate"] and r["matched"]:                    # the visitor asked for a person
        return _start_handoff(conn, channel, user_id, data)

    note = PRIVACY_NOTE if first_visit else ""
    new_menu = r["suggestions"] or chatbot.suggestions(faqs)
    if not r["matched"]:                                  # the bot did not understand
        data = {"menu": new_menu, "question": text}
        db.save_bot_session(conn, channel, user_id, IDLE, data)
        return _result(note + "I'm not sure about that one yet. Reply 0 to send your question to the recruitment "
                       "team, or choose one of these.\n\n" + _menu_text(new_menu), matched=False)
    db.save_bot_session(conn, channel, user_id, IDLE, {"menu": new_menu})
    return _result(note + r["answer"] + "\n\n" + _menu_text(new_menu))


def _start_handoff(conn, channel, user_id, data) -> dict:
    keep = {k: data[k] for k in ("menu", "question") if k in data}
    db.save_bot_session(conn, channel, user_id, ASK_NAME, keep)
    intro = ("Of course. I will pass " + ("your question" if keep.get("question") else "your message") +
             " to the recruitment team. Reply *cancel* at any time to stop.\n\nWhat is your name?")
    return _result(intro, "asking")


def _handoff_step(conn, channel, user_id, state, data, text, low) -> dict:
    contact = _contact_for(channel, user_id)

    if state == ASK_NAME:
        if len(text) < 2:
            return _result("Please tell me your name so the team knows who to reply to.", "asking")
        data["name"] = text[:100]
        db.save_bot_session(conn, channel, user_id, ASK_EMAIL, data)
        ask = "Thanks, " + data["name"].split()[0] + ". What is your email address?"
        if contact:
            ask += " Or reply *skip* and the team will reply here instead."
        return _result(ask, "asking")

    if state == ASK_EMAIL:
        if low in SKIP and contact:
            data["email"] = ""
        elif EMAIL_RE.fullmatch(text):
            data["email"] = text
        else:
            hint = " Or reply *skip* to be answered here." if contact else ""
            return _result("That does not look like an email address. Please type it like name@example.com." + hint,
                           "asking")
        if data.get("question"):
            return _finish(conn, channel, user_id, data, contact)
        db.save_bot_session(conn, channel, user_id, ASK_MESSAGE, data)
        return _result("What would you like to ask the recruitment team?", "asking")

    # ASK_MESSAGE
    if len(text) < 5:
        return _result("Please type your question in a few words.", "asking")
    data["question"] = text
    return _finish(conn, channel, user_id, data, contact)


def _finish(conn, channel, user_id, data, contact) -> dict:
    try:
        out = service.request_human(conn, data.get("name", ""), data.get("email", ""), data.get("question", ""),
                                    channel=channel, contact=contact)
    except service.ServiceError as exc:
        # e.g. a bad email slipped through: go back one step instead of losing what was typed
        db.save_bot_session(conn, channel, user_id, ASK_EMAIL, {k: v for k, v in data.items() if k != "email"})
        return _result(f"{exc} What is your email address?", "asking")
    menu = data.get("menu") or chatbot.suggestions(db.list_faq(conn))
    db.save_bot_session(conn, channel, user_id, IDLE, {"menu": menu})
    way = "by email" if data.get("email") else ("here on WhatsApp" if channel == "whatsapp" else "on this number")
    return _result(f"Thank you, {data['name'].split()[0]}. Your request (#{out['id']}) has been sent and a member of "
                   f"the recruitment team at {config.ORGANISATION_NAME} will reply {way}.\n\nAnything else? "
                   + _menu_text(menu), "submitted", True, out["id"])
