"""Website usage tracking: who uses the site, how, without storing personal data.

What is stored for each event (table usage_events): the day, the kind of event, the page (without ?query and with the
secret parts of private links replaced), the HTTP status, a coarse device and browser name, the referring SITE NAME,
and an anonymous visitor hash.

What is NOT stored: IP addresses, the full browser string, cookies, query strings, names, emails or message text.
The visitor hash is sha256(server secret | day | IP | browser string) cut short. It changes every day and cannot be
reversed without the server secret, so it can count "unique visitors per day" but cannot follow anyone across days.
Visitors whose browser sends "Do Not Track" or "Global Privacy Control" are not tracked. Set TRACK_USAGE=false to turn
tracking off completely. Events are deleted after USAGE_RETENTION_DAYS (default 400).

Tracking never breaks a page: any error is logged and ignored.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

import config
import database as db

log = logging.getLogger(__name__)

_BOT_WORDS = ("bot", "crawl", "spider", "slurp", "curl/", "wget", "python-requests", "headless", "monitor", "uptime",
              "preview", "facebookexternalhit")
EVENTS = ["page_view", "admin_view", "application_submitted", "application_rejected", "chat_opened", "chat_message",
          "chat_handoff", "whatsapp_message", "api_bot_message", "login_success", "login_failed", "export_excel"]


def enabled() -> bool:
    return config.env_bool("TRACK_USAGE", True)


def device_and_browser(ua: str) -> tuple[str, str]:
    u = (ua or "").lower()
    if not u or any(w in u for w in _BOT_WORDS):
        return "bot", "Other"
    device = "tablet" if ("ipad" in u or "tablet" in u) else "mobile" if ("mobi" in u or "android" in u or "iphone" in u) else "desktop"
    if "edg/" in u or "edga/" in u or "edgios/" in u:
        browser = "Edge"
    elif "opr/" in u or "opera" in u:
        browser = "Opera"
    elif "firefox" in u or "fxios" in u:
        browser = "Firefox"
    elif "chrome" in u or "crios" in u:
        browser = "Chrome"
    elif "safari" in u:
        browser = "Safari"
    else:
        browser = "Other"
    return device, browser


def visitor_hash(secret: str, day: str, ip: str, ua: str) -> str:
    return hashlib.sha256(f"{secret}|{day}|{ip}|{ua}".encode("utf-8")).hexdigest()[:16]


def referrer_site(referer: str, own_host: str) -> str:
    host = (urlparse(referer or "").hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    own = (own_host or "").split(":")[0].lower()
    own = own[4:] if own.startswith("www.") else own
    return "" if host == own else host[:100]


def classify(endpoint: str | None, method: str, rule: str, status: int, override: str = "") -> str | None:
    """Which usage event (if any) a finished request counts as."""
    if override:
        return override
    if not endpoint or endpoint in ("static", "healthz") or method not in ("GET", "POST"):
        return None
    if method == "POST":
        if endpoint == "login":
            return "login_success" if status == 302 else "login_failed" if status in (401, 429) else None
        if status != 200:
            return None
        return {"chat": "chat_message", "escalate": "chat_handoff", "bot_message": "api_bot_message",
                "infobip_whatsapp_webhook": "whatsapp_message"}.get(endpoint)
    if status != 200:
        return None
    if endpoint == "chat_suggestions":
        return "chat_opened"
    if endpoint == "export_xlsx":
        return "export_excel"
    if endpoint in ("bot_message", "infobip_whatsapp_webhook"):
        return None
    return "admin_view" if rule.startswith("/admin") else "page_view"


def record(conn, request, response, secret: str, override: str = "", detail: str = "", channel: str = "web") -> None:
    """Called after every request. Never raises."""
    try:
        if not enabled() or request.headers.get("DNT") == "1" or request.headers.get("Sec-GPC") == "1":
            return
        rule = request.url_rule.rule if request.url_rule is not None else request.path
        event = classify(request.endpoint, request.method, rule, response.status_code, override)
        if not event:
            return
        ua = request.headers.get("User-Agent", "")
        device, browser = device_and_browser(ua)
        day = datetime.now(timezone.utc).date().isoformat()
        if event in ("whatsapp_message", "api_bot_message"):
            device, browser, visitor = "", "", ""                      # server-to-server calls: nothing about a browser
        else:
            visitor = visitor_hash(secret, day, request.remote_addr or "", ua)
        db.add_usage_event(conn, day=day, event=event, path=rule[:200], status=response.status_code, visitor=visitor,
                           device=device, browser=browser, referrer=referrer_site(request.referrer, request.host),
                           channel=channel, detail=detail[:100])
    except Exception:  # noqa: BLE001 - tracking must never break the site
        log.exception("usage tracking failed")
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass


# ------------------------------------------------------------------------------------------ the numbers
def _scalar(conn, sql: str, params=()) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row[0] or 0) if row else 0


def summary(conn, days: int = 30) -> dict:
    """Everything the Usage page shows, for the last `days` days (UTC days, today included)."""
    days = max(1, min(int(days), 365))
    today = datetime.now(timezone.utc).date()
    since = (today - timedelta(days=days - 1)).isoformat()
    human = "device <> 'bot'"

    totals = {e: 0 for e in EVENTS}
    for r in conn.execute(f"SELECT event, COUNT(*) AS n FROM usage_events WHERE day >= ? AND {human} GROUP BY event", (since,)):
        totals[r["event"]] = r["n"]
    visitors = _scalar(conn, f"SELECT COUNT(DISTINCT day || ':' || visitor) FROM usage_events "
                             f"WHERE day >= ? AND event = 'page_view' AND visitor <> '' AND {human}", (since,))
    bots = _scalar(conn, "SELECT COUNT(*) FROM usage_events WHERE day >= ? AND device = 'bot'", (since,))

    per_day: dict[str, dict] = {}
    for i in range(days):
        d = (today - timedelta(days=days - 1 - i)).isoformat()
        per_day[d] = {"day": d, "views": 0, "visitors": 0, "applications": 0, "chats": 0, "whatsapp": 0}
    for r in conn.execute(f"SELECT day, event, COUNT(*) AS n, COUNT(DISTINCT visitor) AS v FROM usage_events "
                          f"WHERE day >= ? AND {human} GROUP BY day, event", (since,)):
        row = per_day.get(r["day"])
        if not row:
            continue
        if r["event"] == "page_view":
            row["views"], row["visitors"] = r["n"], r["v"]
        elif r["event"] == "application_submitted":
            row["applications"] = r["n"]
        elif r["event"] == "chat_message":
            row["chats"] = r["n"]
        elif r["event"] == "whatsapp_message":
            row["whatsapp"] = r["n"]
    series = list(per_day.values())
    peak = max([r["views"] for r in series] + [1])
    for r in series:
        r["bar"] = round(100 * r["views"] / peak)

    def ranked(column: str, extra: str = "", limit: int = 8) -> list[dict]:
        return [{"name": r["name"] or "(unknown)", "n": r["n"]} for r in conn.execute(
            f"SELECT {column} AS name, COUNT(DISTINCT day || ':' || visitor) AS n FROM usage_events "
            f"WHERE day >= ? AND event = 'page_view' AND visitor <> '' AND {human} {extra} "
            f"GROUP BY {column} ORDER BY n DESC, name LIMIT {limit}", (since,))]

    pages = [{"name": r["path"], "n": r["n"]} for r in conn.execute(
        f"SELECT path, COUNT(*) AS n FROM usage_events WHERE day >= ? AND event = 'page_view' AND {human} "
        f"GROUP BY path ORDER BY n DESC, path LIMIT 10", (since,))]

    chat = {"matched": 0, "unmatched": 0}
    for r in conn.execute(f"SELECT detail, COUNT(*) AS n FROM usage_events WHERE day >= ? AND event = 'chat_message' AND {human} "
                          "GROUP BY detail", (since,)):
        if r["detail"] in chat:
            chat[r["detail"]] = r["n"]

    form_visitors = _scalar(conn, f"SELECT COUNT(DISTINCT day || ':' || visitor) FROM usage_events WHERE day >= ? "
                                  f"AND event = 'page_view' AND path = '/' AND visitor <> '' AND {human}", (since,))
    applicants = _scalar(conn, f"SELECT COUNT(DISTINCT day || ':' || visitor) FROM usage_events WHERE day >= ? "
                               f"AND event = 'application_submitted' AND visitor <> '' AND {human}", (since,))

    saved_total = _scalar(conn, "SELECT COUNT(*) FROM candidates")
    saved_period = _scalar(conn, "SELECT COUNT(*) FROM candidates WHERE created_at >= ?", (since,))
    return {
        "days": days, "since": since, "totals": totals, "visitors": visitors, "bots": bots, "series": series,
        "pages": pages, "devices": ranked("device"), "browsers": ranked("browser"),
        "referrers": ranked("referrer", "AND referrer <> ''"), "chat": chat,
        "form_visitors": form_visitors, "applicants": applicants,
        "conversion": round(100 * applicants / form_visitors, 1) if form_visitors else None,
        "candidates_saved_total": saved_total, "candidates_saved_period": saved_period,
        "backend": (("Supabase (Postgres, online, through the web API)" if db.use_rest() else "Supabase (Postgres, online)")
                    if db.backend() == "postgres" else "SQLite file on this server"),
    }
