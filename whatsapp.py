"""WhatsApp chat channel through Infobip.

Infobip is used here and ONLY here (emails always go through Zapier). Two things happen:

1. INBOUND: Infobip forwards every WhatsApp message sent to your number to /webhooks/infobip/whatsapp
   (a JSON body with a "results" list - see parse_inbound).
2. OUTBOUND: the bot's answer is sent back with Infobip's "send WhatsApp text message" API
   (POST https://<base url>/whatsapp/1/message/text, header "Authorization: App <api key>").

A free-text reply can only be sent while the 24-hour customer-service window is open, which it always is when
the person has just written to you. Starting a conversation yourself needs an approved template message instead
(not used here).

Every send returns a result dict and never raises, and is logged to `integrations_log` (service "infobip").
"""
from __future__ import annotations

import re
import time
import uuid

import requests

import bot
import config
import database as db
import integrations

MAX_TEXT = 4096                 # WhatsApp text body limit
RATE_PER_HOUR = 60              # messages answered per WhatsApp number per hour (loop / abuse guard)
_recent: dict[str, list[float]] = {}


def base_url() -> str:
    return re.sub(r"^https?://", "", config.INFOBIP_BASE_URL.strip()).strip("/")


def sender() -> str:
    return re.sub(r"\D", "", config.INFOBIP_WHATSAPP_SENDER)


def sending_configured() -> bool:
    return bool(base_url() and config.INFOBIP_API_KEY and sender())


def parse_inbound(payload) -> list[dict]:
    """Infobip's incoming-message JSON -> [{"from", "message_id", "text", "type"}].
    Items without a sender or message id are skipped."""
    out = []
    items = payload.get("results") if isinstance(payload, dict) else None
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        msg = item.get("message") if isinstance(item.get("message"), dict) else {}
        sender_no = re.sub(r"\D", "", str(item.get("from") or ""))
        mid = str(item.get("messageId") or "").strip()
        if not sender_no or not mid:
            continue
        out.append({"from": sender_no, "message_id": mid[:200], "type": str(msg.get("type") or "").upper(),
                    "text": str(msg.get("text") or "").strip()})
    return out


def send_text(to: str, text: str) -> dict:
    """Send one WhatsApp text through Infobip."""
    if not sending_configured():
        return integrations._skipped("infobip", "whatsapp_reply",
                                     "INFOBIP_BASE_URL, INFOBIP_API_KEY and INFOBIP_WHATSAPP_SENDER must all be set")
    body = {"from": sender(), "to": to, "messageId": str(uuid.uuid4()), "content": {"text": text[:MAX_TEXT]}}
    headers = {"Authorization": f"App {config.INFOBIP_API_KEY}", "Content-Type": "application/json",
               "Accept": "application/json"}
    try:
        r = requests.post(f"https://{base_url()}/whatsapp/1/message/text", json=body, headers=headers,
                          timeout=config.HTTP_TIMEOUT)
        return integrations._result("infobip", "whatsapp_reply", r.ok, r.status_code,
                                    "queued by Infobip" if r.ok else r.text[:300])
    except Exception as exc:  # noqa: BLE001 - never block the webhook
        return integrations._result("infobip", "whatsapp_reply", False, None, f"{type(exc).__name__}: {exc}")


def _allowed(number: str) -> bool:
    now = time.time()
    items = [t for t in _recent.get(number, []) if now - t < 3600]
    _recent[number] = items
    if len(items) >= RATE_PER_HOUR:
        return False
    items.append(now)
    return True


def handle_inbound(conn, payload) -> list[dict]:
    """Answer every new text message in an Infobip payload. Returns one summary dict per message."""
    summary = []
    for m in parse_inbound(payload):
        entry = {"from": m["from"], "message_id": m["message_id"], "action": "ignored"}
        summary.append(entry)
        if not db.first_time_seen(conn, m["message_id"]):
            entry["action"] = "duplicate"
            continue
        if "REACTION" in m["type"]:
            continue
        if not _allowed(m["from"]):
            entry["action"] = "rate_limited"
            integrations.record(conn, integrations._result("infobip", "whatsapp_rate_limited", False, None,
                                                           "too many messages from one number"))
            continue
        if not m["text"]:
            reply = "Sorry, I can only read text messages. Please type your question."
        else:
            try:
                reply = bot.handle(conn, "whatsapp", m["from"], m["text"])["reply"]
            except Exception as exc:  # noqa: BLE001 - a bug must not become a silent chat
                integrations.record(conn, integrations._result("infobip", "whatsapp_bot_error", False, None,
                                                               f"{type(exc).__name__}: {exc}"))
                reply = "Sorry, something went wrong on our side. Please try again in a few minutes."
        res = integrations.record(conn, send_text(m["from"], reply))
        entry.update(action="replied" if res["success"] else "reply_failed", detail=res["detail"])
    return summary
