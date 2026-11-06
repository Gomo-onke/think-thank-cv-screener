"""Think Tank recruitment portal (Flask).

PUBLIC  (no login)
    /                     application form (with CV upload) + FAQ chatbot
    /thanks               confirmation page - never shows a score or decision
    /intern/<token>       an intern's personal page (private link)
ADMIN   (password 0000 by default - typed once per session)
    /admin                dashboard
    /admin/candidates     ranking, filters, shortlist-email button
    /admin/candidates/<id>            full profile, score breakdown, actions
    /admin/candidates/<id>/interview  interview notes + personal ranking
    /admin/interviews     interview board (recruiter ranking)
    /admin/interns        place selected interns, post updates & courses
    /admin/requests       chatbot "talk to a recruiter" requests (human hand-off)
    /admin/faq            edit the chatbot's questions and answers; how to add it to a website / WhatsApp
    /chat-widget          the chat window shown inside other websites (static/embed.js)
    /webhooks/infobip/whatsapp   incoming WhatsApp messages from Infobip (needs INFOBIP_WEBHOOK_SECRET)
    /api/bot/message      chatbot API for an Infobip Answers bot (needs BOT_API_KEY)
    /admin/criteria       positions, keywords, weights, thresholds
    /admin/usage          how the website is used (visitors, applications, chat) - no personal data
    /admin/integrations   Zapier status, test buttons and activity log
    /admin/export.xlsx    download the Excel report

Run:  flask --app app run --debug      (or)      python app.py
"""
from __future__ import annotations

import base64
import hmac
import io
import re
import secrets
import time
from datetime import date, datetime, timedelta
from functools import wraps

from flask import (Flask, Response, abort, flash, g, jsonify, redirect, render_template,
                   request, send_file, session, url_for)
from werkzeug.middleware.proxy_fix import ProxyFix

import bot
import chatbot
import config
import database as db
import excel_export
import integrations
import parsers
import service
import sheets
import usage
import whatsapp
from screener import parse_keywords

EDU_CHOICES = ["Diploma", "Bachelor", "Master", "PhD"]
MAX_LOGIN_FAILS = 5
LOGIN_WINDOW_SECONDS = 300
CHAT_LIMIT_PER_HOUR = 120


def _safe_next(value: str | None) -> str | None:
    """Only allow same-site relative redirects."""
    if value and value.startswith("/") and not value.startswith("//") and "\\" not in value:
        return value
    return None


def _secret_key() -> str:
    """SECRET_KEY from .env, or a random key generated once and stored in the database
    (shared by every worker, survives restarts). Never a hard-coded default."""
    key = config.env("SECRET_KEY")
    if key and not key.startswith("change-me"):
        return key
    c = db.get_conn()
    try:
        c.execute("INSERT OR IGNORE INTO settings(key, value) VALUES ('secret_key', ?)", (secrets.token_hex(32),))
        c.commit()
        return c.execute("SELECT value FROM settings WHERE key = 'secret_key'").fetchone()[0]
    finally:
        c.close()


def create_app() -> Flask:
    app = Flask(__name__)
    if config.env_bool("TRUST_PROXY"):  # behind nginx / Render: use the real client IP and https
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    db.init_db()
    app.config["SECRET_KEY"] = _secret_key()
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_MB * 1024 * 1024
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = config.env_bool("COOKIE_SECURE", False)
    app.permanent_session_lifetime = timedelta(hours=8)

    login_fails: dict[str, list[float]] = {}
    submits: dict[str, list[float]] = {}
    chats: dict[str, list[float]] = {}
    escalations: dict[str, list[float]] = {}
    app.login_fails, app.submits, app.chats, app.escalations = login_fails, submits, chats, escalations  # for tests

    # ------------------------------------------------------------------ plumbing
    def conn():
        if "conn" not in g:
            g.conn = db.get_conn()
        return g.conn

    @app.teardown_appcontext
    def close_conn(_exc):
        c = g.pop("conn", None)
        if c is not None:
            c.close()

    def is_admin() -> bool:
        return bool(session.get("is_admin"))

    def admin_required(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not is_admin():
                if request.path.startswith("/api/"):
                    return jsonify(ok=False, error="Admin login required."), 401
                nxt = request.full_path.rstrip("?") if request.method == "GET" else None
                return redirect(url_for("login", next=nxt))
            return view(*args, **kwargs)
        return wrapper

    def recent(bucket: dict, key: str, window: float) -> list[float]:
        now = time.time()
        items = [t for t in bucket.get(key, []) if now - t < window]
        bucket[key] = items
        return items

    def back(default: str, **values):
        """Redirect to the form's hidden `next` field if safe, otherwise to `default`."""
        return redirect(_safe_next(request.form.get("next")) or url_for(default, **values))

    def embed_ancestors() -> str:
        """Which sites may show the chat widget in a frame: EMBED_ALLOWED_ORIGINS, or any site when blank."""
        origins = [o for o in re.split(r"[\s,]+", config.EMBED_ALLOWED_ORIGINS) if re.fullmatch(r"https?://[\w.*:-]+", o)]
        return "'self' " + " ".join(origins) if origins else "*"

    def public_base_url() -> str:
        return config.env("PUBLIC_BASE_URL") or request.url_root

    @app.context_processor
    def inject_globals():
        open_requests = db.count_open_escalations(conn()) if is_admin() else 0
        return {"open_requests": open_requests, "is_admin": is_admin(), "org_name": config.ORGANISATION_NAME, "stages": config.STAGES,
                "response_days": config.RESPONSE_WINDOW_BUSINESS_DAYS,
                "interview_days": config.INTERVIEW_WINDOW_BUSINESS_DAYS,
                "intern_position": config.INTERN_POSITION, "departments": config.DEPARTMENTS}

    @app.after_request
    def headers(resp):
        if request.path.startswith(("/admin", "/api/positions", "/intern/")):
            resp.headers["Cache-Control"] = "no-store"   # the back button must not reveal data after logout
        if request.path.startswith("/intern/"):
            resp.headers["X-Robots-Tag"] = "noindex, nofollow"
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        if request.path == "/chat-widget":
            resp.headers["Content-Security-Policy"] = "frame-ancestors " + embed_ancestors()
        else:   # nobody else may put the portal (login, admin pages) inside a frame
            resp.headers.setdefault("Content-Security-Policy", "frame-ancestors 'self'")
        return resp

    @app.after_request
    def track_usage(resp):
        """Count the visit (no personal data, see usage.py). Never fails the request."""
        if request.endpoint not in (None, "static", "healthz"):
            usage.record(conn(), request, resp, app.config["SECRET_KEY"], override=g.get("usage_event", ""),
                         detail=g.get("usage_detail", ""), channel=g.get("usage_channel", "web"))
        return resp

    @app.template_filter("badge")
    def badge(status: str) -> str:
        return {"Pass": "pass", "Needs Review": "review", "Reject": "reject", "Selected": "pass",
                "Not selected": "reject", "Interview invited": "info", "Interviewed": "info",
                "Shortlisted": "info", "Applied": "neutral", "Yes": "pass", "Maybe": "review",
                "No": "reject"}.get(status, "neutral")

    @app.template_filter("ts")
    def fmt_ts(value: str) -> str:
        try:
            return datetime.fromisoformat(value).strftime("%d %b %Y, %H:%M")
        except Exception:  # noqa: BLE001
            return value or ""

    @app.template_filter("day")
    def fmt_day(value: str) -> str:
        try:
            return datetime.fromisoformat(value).strftime("%d %b %Y")
        except Exception:  # noqa: BLE001
            return value or ""

    @app.template_filter("pct")
    def pct(value) -> str:
        return f"{round(float(value) * 100)}%"

    @app.errorhandler(413)
    def too_large(_e):
        flash(f"File too large (max {config.MAX_UPLOAD_MB} MB).", "danger")
        return redirect(url_for("apply_form"))

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("error.html", code=404, message="That page could not be found."), 404

    # ================================================================== PUBLIC
    @app.get("/")
    def apply_form():
        return render_template("apply.html", positions=db.list_positions(conn()), choices=config,
                               selected_position=request.args.get("position", ""))

    @app.post("/submit")
    def submit():
        ip = request.remote_addr or "?"
        if not is_admin():   # per-IP limit so the public form cannot be used to spam texts / emails
            try:
                limit = int(config.env("SUBMIT_LIMIT_PER_HOUR", "30"))
            except ValueError:
                limit = 30
            if len(recent(submits, ip, 3600)) >= limit:
                flash("Too many submissions from your connection. Please try again later.", "danger")
                return redirect(url_for("apply_form"))
            submits[ip].append(time.time())

        file = request.files.get("cv_file")
        form = request.form.to_dict()
        try:
            filename, source = "", "paste"
            if file and file.filename:
                cv_text = parsers.extract_text(file.filename, file.read())
                filename, source = file.filename, "web"
            else:
                cv_text = form.get("cv_text", "")
            out = service.apply(conn(), form, cv_text=cv_text, cv_filename=filename, source=source)
            g.usage_event = "application_submitted"
        except ValueError as exc:   # ServiceError and parser errors are user-fixable
            g.usage_event = "application_rejected"
            flash(str(exc), "danger")
            return redirect(url_for("apply_form", position=form.get("position", "")))
        except Exception as exc:  # noqa: BLE001
            app.logger.exception("application failed")
            flash(f"Unexpected error: {exc}" if is_admin()
                  else "Something went wrong while processing your application. Please try again.", "danger")
            return redirect(url_for("apply_form"))

        if not is_admin():
            return redirect(url_for("thanks"))   # applicants never see their score or decision
        r = out["result"]
        flash(f"Screened {form.get('name', '').strip()}: {r['status']} ({r['score']}/100)", "success")
        failed = [n for n in out["notifications"] if not n["success"] and not n["detail"].startswith("skipped")]
        if failed:
            flash("Some notifications failed (the application itself was saved): "
                  + ", ".join(f"{n['service']} {n['action']}" for n in failed), "warning")
        return redirect(url_for("candidate", cid=out["candidate_id"]))

    @app.get("/thanks")
    def thanks():
        return render_template("thanks.html")

    @app.get("/healthz")
    def healthz():
        return jsonify(status="ok", database=db.backend(), via=("web-api" if db.use_rest() else "direct" if db.backend() == "postgres" else "file"))

    # ---- an intern's private page (the secret token in the link is the key) ----
    @app.get("/intern/<token>")
    def intern_hub(token: str):
        intern = db.get_intern_by_token(conn(), token)
        if not intern:
            abort(404)
        return render_template("intern_hub.html", intern=intern,
                               dept=config.DEPARTMENTS.get(intern["department"], {}),
                               updates=db.list_intern_updates(conn(), intern["id"]),
                               courses=db.list_intern_courses(conn(), intern["id"]))

    # ---- FAQ chatbot ----
    @app.get("/api/chat/suggestions")
    def chat_suggestions():
        return jsonify(suggestions=chatbot.suggestions(db.list_faq(conn())), org=config.ORGANISATION_NAME)

    @app.post("/api/chat")
    def chat():
        ip = request.remote_addr or "?"
        if len(recent(chats, ip, 3600)) >= CHAT_LIMIT_PER_HOUR:
            return jsonify(answer="You have asked a lot of questions - please try again later.",
                           matched=False, suggestions=[]), 429
        chats[ip].append(time.time())
        message = str((request.get_json(silent=True) or {}).get("message", "")).strip()
        if not message:
            return jsonify(answer="Please type a question.", matched=False, suggestions=[]), 400
        answer = chatbot.reply(message, db.list_faq(conn()))
        g.usage_detail = "matched" if answer["matched"] else "unmatched"
        if answer["faq_id"] is not None or not answer["matched"]:   # skip greetings / thanks
            db.log_chat(conn(), message, answer["matched"])
        return jsonify(answer)

    @app.post("/api/escalate")
    def escalate():
        """'Talk to a recruiter': saves the request, then Zapier emails the recruiter and the visitor."""
        ip = request.remote_addr or "?"
        try:
            limit = int(config.env("ESCALATION_LIMIT_PER_HOUR", "5"))
        except ValueError:
            limit = 5
        if len(recent(escalations, ip, 3600)) >= limit:
            return jsonify(ok=False, error="You have sent several requests already - please try again later."), 429
        data = request.get_json(silent=True) or {}
        try:
            out = service.request_human(conn(), str(data.get("name", "")), str(data.get("email", "")),
                                        str(data.get("message", "")))
        except ValueError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        escalations[ip].append(time.time())
        return jsonify(ok=True, id=out["id"], message="Thank you - a member of the recruitment team will reply to you by email.")

    # ---- chat widget for other websites (see static/embed.js) ----
    @app.get("/chat-widget")
    def chat_widget():
        return render_template("widget.html")

    # ---- Infobip: WhatsApp webhook and the API for an Infobip Answers chatbot ----
    def _supplied_secrets() -> list[str]:
        """Every place the caller may put the shared secret (the first is the easiest to set in Infobip)."""
        found = [request.args.get("secret", ""), request.headers.get("X-Webhook-Secret", ""),
                 request.headers.get("X-API-Key", "")]
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            found.append(auth[7:].strip())
        elif auth.lower().startswith("basic "):
            try:
                found.append(base64.b64decode(auth[6:]).decode("utf-8", "replace").split(":", 1)[-1])
            except Exception:  # noqa: BLE001
                pass
        return [f for f in found if f]

    def _authorised(expected: str) -> bool:
        return any(hmac.compare_digest(f.encode("utf-8"), expected.encode("utf-8")) for f in _supplied_secrets())

    bot_calls: dict[str, list[float]] = {}
    app.bot_calls = bot_calls

    @app.post("/webhooks/infobip/whatsapp")
    def infobip_whatsapp_webhook():
        """Infobip forwards each incoming WhatsApp message here; the bot's answer is sent back through Infobip."""
        if not config.INFOBIP_WEBHOOK_SECRET:
            return jsonify(ok=False, error="INFOBIP_WEBHOOK_SECRET is not set on the server."), 503
        if not _authorised(config.INFOBIP_WEBHOOK_SECRET):
            return jsonify(ok=False, error="Unauthorised."), 401
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(ok=False, error="Expected a JSON body."), 400
        handled = whatsapp.handle_inbound(conn(), payload)
        g.usage_channel, g.usage_detail = "whatsapp", f"{len(handled)} message(s)"
        return jsonify(ok=True, handled=len(handled))     # always 200, so Infobip does not retry a processed message

    @app.post("/api/bot/message")
    def bot_message():
        """For an Infobip Answers chatbot (API element) or any other chat tool.
        Body: {"user_id": "...", "text": "..."}  ->  {"reply": "...", "handoff": "none|asking|submitted", ...}"""
        if not config.BOT_API_KEY:
            return jsonify(ok=False, error="BOT_API_KEY is not set on the server."), 503
        if not _authorised(config.BOT_API_KEY):
            return jsonify(ok=False, error="Unauthorised."), 401
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(ok=False, error="Expected a JSON body."), 400
        user_id = str(data.get("user_id") or data.get("session_id") or "").strip()
        if not user_id:
            return jsonify(ok=False, error="user_id is required (a stable id for this person, e.g. their phone number)."), 400
        if len(recent(bot_calls, user_id, 3600)) >= 120:
            return jsonify(ok=False, error="Too many messages from this user."), 429
        bot_calls[user_id].append(time.time())
        out = bot.handle(conn(), "api", user_id, str(data.get("text", "")))
        g.usage_channel = "api"
        return jsonify(ok=True, **out)

    # ================================================================== ADMIN: login
    @app.route("/admin/login", methods=["GET", "POST"])
    def login():
        nxt = _safe_next(request.values.get("next"))
        if request.method == "POST":
            ip = request.remote_addr or "?"
            if len(recent(login_fails, ip, LOGIN_WINDOW_SECONDS)) >= MAX_LOGIN_FAILS:
                flash("Too many wrong attempts. Please wait a few minutes and try again.", "danger")
                return render_template("login.html", next=nxt), 429
            supplied = request.form.get("password", "")
            if hmac.compare_digest(supplied.encode("utf-8"), config.env("ADMIN_PASSWORD", "0000").encode("utf-8")):
                login_fails.pop(ip, None)
                session.clear()
                session["is_admin"] = True    # typed once: stays logged in for 8 hours or until Log out
                session.permanent = True
                return redirect(nxt or url_for("dashboard"))
            login_fails.setdefault(ip, []).append(time.time())
            flash("Incorrect password.", "danger")
            return render_template("login.html", next=nxt), 401
        if is_admin():
            return redirect(nxt or url_for("dashboard"))
        return render_template("login.html", next=nxt)

    @app.post("/admin/logout")
    def logout():
        session.clear()
        flash("You have been logged out.", "success")
        return redirect(url_for("apply_form"))

    # ================================================================== ADMIN: dashboard
    @app.get("/admin")
    @admin_required
    def dashboard():
        c = conn()
        rows = db.latest_screenings(c)
        total = len(rows)
        counts = {"Pass": 0, "Needs Review": 0, "Reject": 0}
        for r in rows:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        shares = {k: (round(100 * v / total) if total else 0) for k, v in counts.items()}
        average = round(sum(r["score"] for r in rows) / total, 1) if total else 0
        ranked = sorted(rows, key=lambda r: (-r["score"], r["screened_at"]))

        by_position: dict[str, dict] = {}
        for r in rows:
            p = by_position.setdefault(r["position"], {"position": r["position"], "n": 0, "sum": 0.0,
                                                       "Pass": 0, "Needs Review": 0, "Reject": 0})
            p["n"] += 1
            p["sum"] += r["score"]
            p[r["status"]] = p.get(r["status"], 0) + 1
        positions = sorted(({**p, "avg": round(p["sum"] / p["n"], 1)} for p in by_position.values()),
                           key=lambda p: -p["n"])

        awaiting_email = [r for r in rows if r["status"] == "Pass" and r["stage"] == "Applied"]
        needs_review = [r for r in rows if r["status"] == "Needs Review" and r["stage"] == "Applied"]
        placed_ids = {n["candidate_id"] for n in db.list_interns(c)}
        awaiting_placement = [r for r in rows if r["position"] == config.INTERN_POSITION
                              and r["stage"] == "Selected" and r["candidate_id"] not in placed_ids]
        logs = db.recent_integration_logs(c, 100)
        failed = [l for l in logs if not l["success"] and not l["detail"].startswith("skipped")]
        return render_template("dashboard.html", total=total, counts=counts, shares=shares, average=average,
                               top=ranked[:5], recent=rows[:6], positions=positions, failed=failed,
                               pipeline=db.stage_counts(c), awaiting_email=awaiting_email,
                               needs_review=needs_review, awaiting_placement=awaiting_placement)

    # ================================================================== ADMIN: candidates
    @app.get("/admin/candidates")
    @admin_required
    def candidates():
        status = request.args.get("status") or None
        position = request.args.get("position") or None
        stage = request.args.get("stage") or None
        q = (request.args.get("q") or "").strip() or None
        sort = request.args.get("sort", "score")
        rows = db.latest_screenings(conn(), status=status, position=position, stage=stage, search=q)
        if sort == "rating":   # the recruiters' own ranking first
            rows.sort(key=lambda r: (r["avg_rating"] is None, -(r["avg_rating"] or 0), -r["score"]))
        elif sort == "recent":
            sort = "recent"
        else:
            sort = "score"
            rows.sort(key=lambda r: (-r["score"], r["screened_at"]))
        for r in rows:
            r["can_shortlist"] = service.can_send_shortlist(r, r["status"])
        return render_template("candidates.html", rows=rows, counts=db.status_counts(conn()),
                               positions=db.list_positions(conn()), f={"status": status or "", "position": position or "",
                                                                      "stage": stage or "", "q": q or "", "sort": sort})

    @app.get("/admin/candidates/<int:cid>")
    @admin_required
    def candidate(cid: int):
        c = db.get_candidate(conn(), cid)
        if not c:
            flash("Candidate not found.", "danger")
            return redirect(url_for("candidates"))
        history = db.screening_history(conn(), cid)
        latest = history[0] if history else None
        return render_template(
            "candidate.html", c=c, latest=latest, history=history,
            logs=db.recent_integration_logs(conn(), 50, cid), interviews=db.list_interviews(conn(), cid),
            intern=db.get_intern_by_candidate(conn(), cid), positions=db.list_positions(conn()),
            can_shortlist=bool(latest) and service.can_send_shortlist(c, latest["status"]),
            outcome_email=db.last_success(conn(), cid, list(service.OUTCOME_EMAILS.values())),
            email_stages=service.OUTCOME_EMAILS)

    @app.post("/admin/candidates/<int:cid>/rescreen")
    @admin_required
    def rescreen(cid: int):
        try:
            out = service.rescreen(conn(), cid, request.form.get("position") or None)
            r = out["result"]
            flash(f"Re-screened: {r['status']} ({r['score']}/100) using the current criteria.", "success")
        except ValueError as exc:
            flash(str(exc), "danger")
        return back("candidate", cid=cid)

    @app.post("/admin/candidates/<int:cid>/shortlist-email")
    @admin_required
    def shortlist_email(cid: int):
        try:
            out = service.send_shortlist_email(conn(), cid, request.form.get("interview_when", ""),
                                               request.form.get("meet_link", ""))
            if out["sent"]:
                flash("Shortlist email handed to Zapier - your Zap delivers it to the candidate, inviting them to a "
                      "Google Meet interview within the next 5 business days.", "success")
            else:
                flash("The email was NOT sent: " + out["result"]["detail"] +
                      " (Set ZAPIER_WEBHOOK_URL - see the Integrations page.)", "danger")
        except ValueError as exc:
            flash(str(exc), "danger")
        return back("candidate", cid=cid)

    @app.post("/admin/candidates/<int:cid>/stage")
    @admin_required
    def stage(cid: int):
        stage_name = request.form.get("stage", "")
        try:
            out = service.set_stage(conn(), cid, stage_name, send_email=request.form.get("send_email") == "yes")
            flash(f"Stage updated to {stage_name}." if out["changed"] else f"The stage is already {stage_name}.", "success")
            mail = out["email"]
            if mail and mail["sent"]:
                flash("Email sent to the candidate: " + ("the selection email." if mail["event"] == "selection_email"
                                                         else "the 'not selected' email."), "success")
            elif mail and mail["already"]:
                flash(f"This email was already sent to the candidate on {mail['already'][:10]}, so it was not sent again.", "success")
            elif mail:
                flash("The stage was updated but the email was NOT sent: " + mail["result"]["detail"] +
                      " (Set ZAPIER_WEBHOOK_URL - see the Integrations page. Press Update stage again to retry.)", "danger")
        except ValueError as exc:
            flash(str(exc), "danger")
        return back("candidate", cid=cid)

    # ---- interviews ----
    @app.route("/admin/candidates/<int:cid>/interview", methods=["GET", "POST"])
    @admin_required
    def interview(cid: int):
        c = db.get_candidate(conn(), cid)
        if not c:
            flash("Candidate not found.", "danger")
            return redirect(url_for("candidates"))
        if request.method == "POST":
            try:
                service.save_interview(conn(), cid, request.form.to_dict())
                flash("Interview saved and the candidate's ranking updated.", "success")
                return redirect(url_for("interview", cid=cid))
            except ValueError as exc:
                flash(str(exc), "danger")
        history = db.screening_history(conn(), cid)
        return render_template("interview.html", c=c, latest=history[0] if history else None,
                               interviews=db.list_interviews(conn(), cid), today=date.today().isoformat(),
                               intern=db.get_intern_by_candidate(conn(), cid),
                               form=request.form if request.method == "POST" else {})

    @app.post("/admin/interviews/<int:iid>/delete")
    @admin_required
    def interview_delete(iid: int):
        service.remove_interview(conn(), iid)
        flash("Interview entry deleted.", "success")
        return back("interviews")

    @app.get("/admin/interviews")
    @admin_required
    def interviews():
        position = request.args.get("position") or None
        rows = [r for r in db.latest_screenings(conn(), position=position)
                if r["stage"] != "Applied" or r["interview_count"]]
        rows.sort(key=lambda r: (r["avg_rating"] is None, -(r["avg_rating"] or 0), -r["rec_yes"], -r["score"]))
        for r in rows:
            r["can_shortlist"] = service.can_send_shortlist(r, r["status"])
        return render_template("interviews.html", rows=rows, positions=db.list_positions(conn()),
                               sel_position=position or "")

    # ---- interns ----
    @app.get("/admin/interns")
    @admin_required
    def interns():
        placed = db.list_interns(conn())
        placed_ids = {n["candidate_id"] for n in placed}
        applicants = db.latest_screenings(conn(), position=config.INTERN_POSITION)
        awaiting = [r for r in applicants if r["stage"] == "Selected" and r["candidate_id"] not in placed_ids]
        others = [r for r in applicants if r["stage"] != "Selected" and r["candidate_id"] not in placed_ids]
        return render_template("interns.html", placed=placed, awaiting=awaiting, others=others)

    @app.post("/admin/candidates/<int:cid>/place-intern")
    @admin_required
    def place_intern(cid: int):
        try:
            intern_id, created = service.place_intern(conn(), cid, request.form.get("department", ""),
                                                      request.form.get("supervisor", ""),
                                                      request.form.get("start_date", ""))
            flash("Intern placed in the department. Starter courses were added - email them their personal link "
                  "from this page." if created else "Placement updated.", "success")
            return redirect(url_for("intern_detail", iid=intern_id))
        except ValueError as exc:
            flash(str(exc), "danger")
            return back("interns")

    @app.get("/admin/interns/<int:iid>")
    @admin_required
    def intern_detail(iid: int):
        intern = db.get_intern(conn(), iid)
        if not intern:
            flash("Intern not found.", "danger")
            return redirect(url_for("interns"))
        return render_template("intern_detail.html", intern=intern,
                               hub_link=f"{public_base_url().rstrip('/')}/intern/{intern['token']}",
                               dept=config.DEPARTMENTS.get(intern["department"], {}),
                               updates=db.list_intern_updates(conn(), iid),
                               courses=db.list_intern_courses(conn(), iid))

    def _intern_action(iid: int, fn, ok_message: str):
        try:
            fn()
            flash(ok_message, "success")
        except ValueError as exc:
            flash(str(exc), "danger")
        return redirect(url_for("intern_detail", iid=iid))

    @app.post("/admin/interns/<int:iid>/placement")
    @admin_required
    def intern_placement(iid: int):
        intern = db.get_intern(conn(), iid)
        if not intern:
            abort(404)
        return _intern_action(iid, lambda: service.place_intern(
            conn(), intern["candidate_id"], request.form.get("department", ""), request.form.get("supervisor", ""),
            request.form.get("start_date", "")), "Placement updated.")

    @app.post("/admin/interns/<int:iid>/update")
    @admin_required
    def intern_update(iid: int):
        return _intern_action(iid, lambda: service.add_update(conn(), iid, request.form.get("message", ""),
                                                              request.form.get("author", "")),
                              "Update posted on the intern's page.")

    @app.post("/admin/interns/<int:iid>/updates/<int:uid>/delete")
    @admin_required
    def intern_update_delete(iid: int, uid: int):
        db.delete_intern_update(conn(), uid)
        flash("Update deleted.", "success")
        return redirect(url_for("intern_detail", iid=iid))

    @app.post("/admin/interns/<int:iid>/course")
    @admin_required
    def intern_course(iid: int):
        f = request.form
        return _intern_action(iid, lambda: service.add_course(conn(), iid, f.get("title", ""), f.get("provider", ""),
                                                              f.get("link", ""), f.get("note", "")),
                              "Course added to the intern's page.")

    @app.post("/admin/interns/<int:iid>/courses/<int:cid>/delete")
    @admin_required
    def intern_course_delete(iid: int, cid: int):
        db.delete_intern_course(conn(), cid)
        flash("Course removed.", "success")
        return redirect(url_for("intern_detail", iid=iid))

    @app.post("/admin/interns/<int:iid>/suggest-courses")
    @admin_required
    def intern_suggest(iid: int):
        try:
            n = service.suggest_courses(conn(), iid)
            flash(f"Added {n} suggested course(s) for this department." if n else
                  "All suggested courses for this department are already on the list.", "success")
        except ValueError as exc:
            flash(str(exc), "danger")
        return redirect(url_for("intern_detail", iid=iid))

    @app.post("/admin/interns/<int:iid>/email-link")
    @admin_required
    def intern_email_link(iid: int):
        try:
            out = service.send_intern_welcome(conn(), iid, public_base_url())
            flash("Welcome email with the intern's personal link was handed to Zapier." if out["sent"] else
                  "The email was NOT sent: " + out["result"]["detail"] + f" You can copy the link yourself: {out['link']}",
                  "success" if out["sent"] else "danger")
        except ValueError as exc:
            flash(str(exc), "danger")
        return redirect(url_for("intern_detail", iid=iid))

    # ================================================================== ADMIN: FAQ chatbot
    @app.get("/admin/faq")
    @admin_required
    def faq():
        base = public_base_url().rstrip("/")
        return render_template("faq_admin.html", faqs=db.list_faq(conn()), unanswered=db.unanswered_chats(conn()),
                               base=base, wa_on=bool(config.INFOBIP_WEBHOOK_SECRET), api_on=bool(config.BOT_API_KEY),
                               wa_send_on=whatsapp.sending_configured())

    @app.post("/admin/faq/save")
    @admin_required
    def faq_save():
        f = request.form
        question, answer = f.get("question", "").strip(), f.get("answer", "").strip()
        if not question or not answer:
            flash("A question and an answer are both required.", "danger")
            return redirect(url_for("faq"))
        try:
            order = int(f.get("sort_order") or 0)
        except ValueError:
            order = 0
        faq_id = int(f["faq_id"]) if f.get("faq_id", "").isdigit() else None
        db.save_faq(conn(), faq_id, question[:300], answer[:2000], f.get("keywords", "").strip()[:500], order)
        flash("FAQ saved." if faq_id else "FAQ added.", "success")
        return redirect(url_for("faq"))

    @app.post("/admin/faq/<int:fid>/delete")
    @admin_required
    def faq_delete(fid: int):
        db.delete_faq(conn(), fid)
        flash("FAQ deleted.", "success")
        return redirect(url_for("faq"))

    # ================================================================== ADMIN: chat requests (human escalation)
    @app.get("/admin/requests")
    @admin_required
    def requests_page():
        show = request.args.get("show", "open")
        rows = db.list_escalations(conn(), None if show == "all" else "Open")
        return render_template("requests.html", rows=rows, show="all" if show == "all" else "open",
                               open_count=db.count_open_escalations(conn()))

    @app.post("/admin/requests/<int:eid>/resolve")
    @admin_required
    def request_resolve(eid: int):
        service.resolve_request(conn(), eid, request.form.get("note", ""))
        flash("Request marked as resolved.", "success")
        return redirect(url_for("requests_page"))

    # ================================================================== ADMIN: criteria
    @app.get("/admin/criteria")
    @admin_required
    def criteria():
        return render_template("criteria.html", positions=db.list_positions(conn()),
                               settings=db.get_settings(conn()), edu_choices=EDU_CHOICES)

    def _position_from_form(f) -> dict:
        name = (f.get("name") or "").strip()
        if not name:
            raise ValueError("Position name is required.")
        if f.get("min_education") not in EDU_CHOICES:
            raise ValueError(f"Minimum education must be one of {', '.join(EDU_CHOICES)}.")
        try:
            p = {"name": name[:100], "min_years": float(f.get("min_years") or 0),
                 **{k: float(f.get(k) or 0) for k in ("w_exp", "w_edu", "w_req", "w_pref")}}
        except ValueError:
            raise ValueError("Years and weights must be numbers.") from None
        weights = [p[k] for k in ("w_exp", "w_edu", "w_req", "w_pref")]
        if p["min_years"] < 0 or any(w < 0 for w in weights):
            raise ValueError("Years and weights cannot be negative.")
        if sum(weights) <= 0:
            raise ValueError("At least one weight must be above zero.")
        p["min_education"] = f["min_education"]
        p["required_keywords"] = ", ".join(parse_keywords(f.get("required_keywords", "")))
        p["preferred_keywords"] = ", ".join(parse_keywords(f.get("preferred_keywords", "")))
        return p

    @app.post("/admin/criteria/position")
    @admin_required
    def criteria_position():
        try:
            p = _position_from_form(request.form)
        except ValueError as exc:
            flash(str(exc), "danger")
            return redirect(url_for("criteria"))
        original = (request.form.get("original_name") or "").strip()
        if original and original != p["name"]:
            if db.get_position(conn(), p["name"]):
                flash(f"A position called {p['name']} already exists.", "danger")
                return redirect(url_for("criteria"))
            db.delete_position(conn(), original)
            conn().execute("UPDATE candidates SET position = ? WHERE position = ?", (p["name"], original))
            conn().commit()
        db.upsert_position(conn(), p)
        flash(f"Saved {p['name']}. Use Re-screen on a candidate to apply the new criteria to them.", "success")
        return redirect(url_for("criteria"))

    @app.post("/admin/criteria/position/delete")
    @admin_required
    def criteria_position_delete():
        name = (request.form.get("name") or "").strip()
        if name:
            db.delete_position(conn(), name)
            flash(f"Deleted {name}. Existing candidates keep their results.", "success")
        return redirect(url_for("criteria"))

    @app.post("/admin/criteria/settings")
    @admin_required
    def criteria_settings():
        f = request.form
        try:
            pass_t, review_t = float(f["pass_threshold"]), float(f["review_threshold"])
        except (KeyError, ValueError):
            flash("Thresholds must be numbers.", "danger")
            return redirect(url_for("criteria"))
        if not (0 <= review_t <= pass_t <= 100):
            flash("Need 0 <= review threshold <= pass threshold <= 100.", "danger")
            return redirect(url_for("criteria"))
        db.set_setting(conn(), "pass_threshold", f"{pass_t:g}")
        db.set_setting(conn(), "review_threshold", f"{review_t:g}")
        db.set_setting(conn(), "require_all_required_keywords", "1" if f.get("require_all_required_keywords") else "0")
        flash("Thresholds saved.", "success")
        return redirect(url_for("criteria"))

    # ================================================================== ADMIN: integrations + Excel
    @app.get("/admin/integrations")
    @admin_required
    def integrations_page():
        checks = [
            ("Zapier webhook URL (needed for ALL emails)", bool(config.ZAPIER_WEBHOOK_URL)),
            ("Recruiter email (receives a summary of every application)", bool(config.RECRUITMENT_LEAD_EMAIL)),
            ("Google Sheets (credentials + sheet id)", sheets.sheets_configured()),
            ("WhatsApp through Infobip: reply settings (base URL, API key, sender)", whatsapp.sending_configured()),
            ("WhatsApp through Infobip: webhook secret", bool(config.INFOBIP_WEBHOOK_SECRET)),
            ("Chatbot API key for an Infobip Answers chatbot", bool(config.BOT_API_KEY)),
        ]
        return render_template("integrations.html", checks=checks, logs=db.recent_integration_logs(conn(), 60),
                               sheets_on=sheets.sheets_configured(), excel_path=config.EXCEL_PATH,
                               zapier_on=bool(config.ZAPIER_WEBHOOK_URL))

    @app.post("/admin/integrations/test-zapier")
    @admin_required
    def test_zapier():
        res = integrations.record(conn(), integrations.test_zapier())
        flash("Zapier test payload sent." if res["success"] else f"Zapier test failed: {res['detail']}",
              "success" if res["success"] else "danger")
        return redirect(url_for("integrations_page"))

    @app.post("/admin/integrations/test-email")
    @admin_required
    def test_email():
        res = integrations.record(conn(), integrations.test_email(request.form.get("email", "").strip()))
        flash("Test email handed to Zapier - check the inbox once your Zap has run." if res["success"]
              else f"Test email NOT sent: {res['detail']}", "success" if res["success"] else "danger")
        return redirect(url_for("integrations_page"))

    @app.post("/admin/sheets-import")
    @admin_required
    def sheets_import():
        try:
            summary = service.import_from_sheets(conn())
            flash(f"Google Sheets: {summary['screened']} of {summary['found']} new row(s) screened.", "success")
            for err in summary["errors"][:5]:
                flash(err, "warning")
        except Exception as exc:  # noqa: BLE001
            flash(f"Google Sheets import failed: {exc}", "danger")
        return redirect(url_for("integrations_page"))

    @app.get("/admin/usage")
    @admin_required
    def usage_page():
        try:
            days = int(request.args.get("days", "30"))
        except ValueError:
            days = 30
        days = days if days in (7, 14, 30, 90) else 30
        return render_template("usage.html", u=usage.summary(conn(), days), tracking=usage.enabled())

    @app.get("/admin/export.xlsx")
    @admin_required
    def export_xlsx():
        data = excel_export.workbook_bytes(conn())
        return send_file(io.BytesIO(data), as_attachment=True,
                         download_name=f"recruitment_report_{date.today().isoformat()}.xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(config.env("PORT", "5000")), debug=config.env_bool("FLASK_DEBUG"))
