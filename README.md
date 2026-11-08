# Think Tank Recruitment Portal

A web portal that takes a job applicant from the first click to the first day: they **apply** with a CV, the system **screens and ranks** the CV, recruiters **interview and decide**, every candidate receives a **clear email at each stage**, and selected interns get a private **onboarding page**. A built-in **FAQ chatbot**, a **dashboard**, an **Excel report** and privacy-first **usage statistics** run alongside.

Built by **Group 12** for **Think Tank Software Solutions** (IFS325 / IFS353 project). Recruiters make every hiring decision; the system prepares the information and sends the emails.

> **Status in one glance:** the full journey works end to end and is covered by 180 automated tests (0 failures). Still to do: publish the portal at a public address and confirm the online database against a real Supabase project. See [Project status](#project-status-what-is-done-and-what-is-not).

---

## Contents

1. [What it does](#what-it-does)
2. [What was used to build it](#what-was-used-to-build-it)
3. [Quick start (run it on your computer)](#quick-start-run-it-on-your-computer)
4. [Configuration (.env)](#configuration-env)
5. [Connect email with Zapier](#connect-email-with-zapier)
6. [Put the database online with Supabase (optional)](#put-the-database-online-with-supabase-optional)
7. [Put the portal online (hosting)](#put-the-portal-online-hosting)
8. [How recruiters use it](#how-recruiters-use-it)
9. [How candidates are scored](#how-candidates-are-scored)
10. [Interns, chatbot, Excel report and usage page](#interns-chatbot-excel-report-and-usage-page)
11. [Testing](#testing)
12. [Project layout](#project-layout)
13. [Security and privacy](#security-and-privacy)
14. [Troubleshooting](#troubleshooting)
15. [Project status: what is done and what is not](#project-status-what-is-done-and-what-is-not)
16. [Credits and licence](#credits-and-licence)

---

## What it does

| Who | What they see | Password |
|---|---|---|
| **Applicants** (public) | Application form with CV upload (PDF, DOCX or TXT), a thank-you page, the FAQ chatbot | None |
| **Recruiters** | Dashboard, ranked candidates with a score breakdown, candidate details, shortlist-email button, interview notes and personal rating, selected / not selected, interns, chatbot editor, scoring criteria, requests from the chatbot, usage page, integrations log, Excel download | One recruiter password, typed once per session |
| **Interns** (after placement) | Their own private page with updates and recommended courses | Secret link only |

Applicants are **never shown their score or decision**. They only see "application received" and receive the emails below.

### The five stages

1. **Apply** - a simple form that works on any phone. A confirmation email is sent straight away.
2. **Screen** - the CV is read automatically and scored against the role. Recruiters see a ranked list and the reasons behind each score.
3. **Interview** - one button sends the shortlist email (interview within 5 business days on Google Meet). Interview notes and a personal rating are recorded per recruiter.
4. **Decide** - the recruiter marks the candidate **Selected** or **Not selected**; the matching email is sent **once**.
5. **Onboard** - selected interns are placed in a department and receive a private page with updates and starter courses.

### Features at a glance

- Application form with validation, consent tick-box and CV upload; applicants never see their score.
- Automatic CV reading (PDF, DOCX, TXT) and weighted scoring with hard requirements.
- Ranked candidate list, filters, score breakdown, notes and an audit log of every email attempt.
- Shortlist, Selected and Not selected emails; each is sent once and contradictory emails are blocked.
- Interview board that ranks interviewed candidates by the recruiters' average rating.
- Interns: department placement, supervisor, start date, courses, updates and a private link.
- FAQ chatbot with **16 editable answers**, a polite fallback and **human hand-off** ("Talk to a recruiter").
- A chat window that can be placed on Think Tank's own website (`/chat-widget`, `static/embed.js`).
- Four-sheet Excel report (Summary, Candidates, Interviews, Interns), rewritten after every change.
- **Usage page**: visitors, applications, chat questions, devices - with no names, no IP addresses.
- Local SQLite database by default, or an online **Supabase** (Postgres) database with one setting.
- Safety: login lock-out after repeated wrong passwords, rate limits, escaped text, security headers.

---

## What was used to build it

### Languages and framework

| Part | Used |
|---|---|
| Language | **Python** (3.12 or newer; tested on 3.13) |
| Web framework | **Flask 3.1.3** with Werkzeug 3.1.9 |
| Pages | **Jinja2** templates, **HTML**, **CSS**, and plain (vanilla) **JavaScript** - no front-end framework |
| Production server | **gunicorn 23.0.0** |

### Libraries (see `requirements.txt`)

| Package | Version | Used for |
|---|---|---|
| Flask, Werkzeug | 3.1.3, 3.1.9 | Web application |
| requests | 2.34.2 | Calls to the Zapier webhook |
| python-dotenv | 1.2.3 | Reads the `.env` settings file |
| pdfplumber | 0.11.10 | Reads text from PDF CVs |
| python-docx | 1.2.0 | Reads text from DOCX CVs |
| openpyxl | 3.1.5 | Writes the Excel report |
| psycopg[binary] | 3.2 or newer, below 4 | Direct Postgres / Supabase connection |
| gspread | 6.2.1 | Optional Google Sheets sync |
| gunicorn | 23.0.0 | Production server |

### Services and tools

| Need | Used | Notes |
|---|---|---|
| Email delivery | **Zapier** (Webhooks by Zapier, Catch Hook) with **Gmail**, Outlook or Email by Zapier | One webhook and one Zap send *all* emails |
| Online database | **Supabase** (hosted PostgreSQL) | Optional; the default is a local **SQLite** file |
| Interviews | **Google Meet** | A Meet link is added to the shortlist email |
| Hosting | **Render** (Blueprint included), Railway, or your own server with **nginx** and **systemd** | See [hosting](#put-the-portal-online-hosting) |
| Source control | **Git** and **GitHub** | |
| Testing | Python **unittest**, local **PostgreSQL 16** | 180 tests, three database modes |
| Development support | **Claude** (Anthropic's AI assistant) was used as a coding and documentation assistant by the team | Remove this line if your team prefers not to state it |

### Design choices worth knowing

- **All email goes through one Zapier webhook.** The portal never talks to an email provider itself, so there are no email passwords in the code.
- **The chatbot is rule-based.** Nothing is sent to an AI service.
- **Screening is rule-based and explainable**, so every score can be justified to a candidate or auditor. A human makes the final decision.
- **One codebase, two databases.** The same queries run on SQLite and on Postgres (`pgcompat.py`).

---

## Quick start (run it on your computer)

You need **Python 3.12 or newer** and **Git**. A Zapier account and a Supabase account are optional for a first run.

**Windows (PowerShell)**

```powershell
git clone https://github.com/Gomo-onke/think-thank-cv-screener
cd think-thank-cv-screener
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
if (!(Test-Path .env)) { copy .env.example .env }
python -m flask --app app run
```

**macOS / Linux**

```bash
git clone https://github.com/Gomo-onke/think-thank-cv-screener
cd think-thank-cv-screener
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp -n .env.example .env
python -m flask --app app run
```

Open <http://127.0.0.1:5000>.

- Applicants use `/`.
- Recruiters open **Recruiter login** (`/admin/login`). The default password is **`0000`** - change it straight away (see below).
- Keep the terminal window open while the site runs (Ctrl+C stops it). Edit `.env` in a text editor, then restart.
- Health check: <http://127.0.0.1:5000/healthz> shows which database is in use.

**First 10 minutes**

1. Submit a test application at `/`. You land on the thank-you page (no score is shown).
2. Log in at `/admin/login` and open **Candidates**: the test applicant is scored.
3. Set `ADMIN_PASSWORD=` in `.env` and restart.
4. Connect Zapier (next sections) so emails are delivered. Without it the portal says plainly **"NOT sent: ZAPIER_WEBHOOK_URL not set"** instead of pretending.
5. Open **Chatbot** and review every answer - the supplied ones are generic samples, not Think Tank policy.
6. Open **Criteria** to edit positions, keywords, weights and the Pass / Needs Review thresholds.

---

## Configuration (.env)

Copy `.env.example` to `.env` (same folder as `app.py`). **Never commit `.env`** - it is already in `.gitignore`. On a host such as Render, set the same names in the host's environment settings instead.

| Setting | What it does | Default / example |
|---|---|---|
| `ADMIN_PASSWORD` | Recruiter password | `0000` - **change it** |
| `SECRET_KEY` | Signs login cookies. Blank = generated once and stored in the database | Optional |
| `COOKIE_SECURE` | `true` once the site is served over HTTPS | `false` locally, `true` online |
| `TRUST_PROXY` | `true` behind nginx / Render / Railway so real IPs and https are detected | `false` locally |
| `SUBMIT_LIMIT_PER_HOUR` | Max public applications per visitor per hour | Stops spam |
| `ESCALATION_LIMIT_PER_HOUR` | Max "Talk to a recruiter" requests per visitor per hour | |
| `PORT`, `FLASK_DEBUG` | Port and debug mode | `5000`, off |
| `ORGANISATION_NAME` | Shown in emails and on the site | `Think Tank Software Solutions` |
| `PUBLIC_BASE_URL` | Public address of the site, used in the intern's personal link | e.g. `https://careers.example.org` |
| `MAX_UPLOAD_MB` | Largest CV upload | |
| `HTTP_TIMEOUT` | Seconds to wait for Zapier | 15 |
| `ZAPIER_WEBHOOK_URL` | **The Catch Hook address - all email goes through it** | Required for email |
| `RECRUITMENT_LEAD_EMAIL` | Receives a summary for every application and chatbot hand-off. Blank = off | |
| `DEFAULT_COUNTRY_CODE` | Turns `082...` into `2782...` in the phone field sent to Zapier | `27` |
| `DATABASE_URL` | Supabase / Postgres connection string. Blank = local SQLite | Optional |
| `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | Supabase web-API route (use if the database port is blocked) | Optional |
| `SKIP_SCHEMA_SETUP` | `true` after you ran `supabase/schema.sql` yourself | |
| `TRACK_USAGE` | `false` turns usage statistics off | `true` |
| `USAGE_RETENTION_DAYS` | How long usage events are kept | 400 |
| `DATABASE_PATH` | SQLite file location (only when no online database) | |
| `EXCEL_PATH` | Excel report location | |
| `GOOGLE_CREDENTIALS_FILE`, `SHEET_ID`, ... | Optional Google Sheets sync | |
| `EMBED_ALLOWED_ORIGINS` | Websites allowed to show the chat window | Blank = none |

> The `.env.example` file also lists settings for an optional WhatsApp / Infobip chat channel. That channel is **not connected** in the delivered solution (see [status](#project-status-what-is-done-and-what-is-not)); leave those lines blank.

Secret values (the Zapier URL, the admin password, `SUPABASE_SERVICE_KEY`, `DATABASE_URL`) belong only in `.env` or the host's settings - never in the code, the documents or GitHub.

---

## Connect email with Zapier

All emails are handed to **one Zapier webhook**. About 10 minutes, one Zap does everything.

1. In Zapier choose **Create Zap**. Trigger: **Webhooks by Zapier > Catch Hook** (leave "Pick off a child key" empty). Copy the **Custom Webhook URL** into `.env` as `ZAPIER_WEBHOOK_URL=` and restart the site.
2. In the portal open **Integrations > Send test payload**. In Zapier press **Test trigger** - you should see a record with all the fields.
3. Add a **Filter**: only continue if `send_email` (Text) **Exactly matches** `yes`. (Data-only events have `send_email = no` and stop here.)
4. Add the delivery step **Gmail > Send Email** (or Outlook, or Email by Zapier) and map:
   - **To** = `email_to`
   - **Subject** = `email_subject`
   - **Body** = `email_body` (plain text)
5. In the portal use **Integrations > Send test email**, check the inbox, then **Publish** the Zap.

This one Zap now sends all of these:

| `event` | Goes to | What it says |
|---|---|---|
| `application_received` | The candidate | Application received; if there is no reply within 14 business days, please consider it unsuccessful |
| `recruiter_notification` | `RECRUITMENT_LEAD_EMAIL` | Candidate, score, decision and keyword summary |
| `shortlist_email` | The candidate | Congratulations; interview within 5 business days on Google Meet |
| `selection_email` | The candidate | Stage set to **Selected**: congratulations and next steps |
| `rejection_email` | The candidate | Stage set to **Not selected**: a respectful decline |
| `intern_welcome_email` | The intern | Link to their private page |
| `human_escalation` | `RECRUITMENT_LEAD_EMAIL` | A chat visitor asked for a person |
| `human_escalation_ack` | The visitor | "We have passed your question to our team" |
| `application_rescreened`, `stage_changed`, `intern_placed`, `test` | Nobody | Data only (for Google Sheets, Slack and so on) |

Every payload also carries `candidate_name`, `email`, `phone`, `phone_international`, `position`, `score`, `status`, `stage`, `preferred_department`, `notes` and `timestamp`.

**Important**

- "Sent" in the portal means **Zapier accepted the webhook**. Whether Gmail delivered it is shown in the Zap's **Zap runs** history.
- If an earlier separate "application received" Zap uses the same webhook, **turn it off** or candidates get two emails.
- Email wording lives in `emails.py` (`selected`, `not_selected`, and so on).

---

## Put the database online with Supabase (optional)

**What Supabase is, in plain words:** an online database - a filing cabinet kept in the cloud instead of on the portal's own computer. Using it, the portal's records (applications, scores, interviews, interns, chat requests, email log and usage statistics) stay safe if the server restarts or is replaced. It is **optional**: without it the portal keeps everything in a local SQLite file and works fine.

**Set it up**

1. Create a project at <https://supabase.com> (New project). Choose a region close to your users and save the database password.
2. Open **SQL Editor > New query**, paste all of `supabase/schema.sql` and press **Run**. This creates the 15 tables, turns on Row Level Security and closes the public roles. It is safe to run again.
3. Connect the portal - **Route A, direct connection:** from **Project settings > Database > Connection string** copy the *Transaction pooler* URL, put your password in, and set `DATABASE_URL=...` in `.env`. Special characters in the password must be URL-encoded (`@` becomes `%40`).
   **Route B, web API (HTTPS):** if your network blocks the database port, set both `SUPABASE_URL` (the Project URL) and `SUPABASE_SERVICE_KEY` (the **secret** / service_role key, not the anon or publishable key). Route B ignores `DATABASE_URL`.
4. Restart, then run `python tools/check_db_connection.py` and open `/healthz` - it should say `"database": "postgres"` (or `"via": "web-api"`).
5. To move data already collected in SQLite: `python tools/migrate_sqlite_to_supabase.py --dry-run`, then run it again without `--dry-run`. Ids are kept, so interview and intern links keep working.

**Security:** Row Level Security is on for every table with no policies, so the public (anon) key can read nothing. Only the portal server, using the database password or secret key, reaches the data. If a key leaks, rotate it in Supabase.

More detail and the testing record: [`supabase/README.md`](supabase/README.md).

---

## Put the portal online (hosting)

With an online database (Supabase) the host needs no disk for data. Without it, SQLite is a *file*, so the host needs a disk that survives restarts - **do not use a free host with a temporary disk**, or the database and Excel file are wiped on every restart.

**Render (easiest)**

1. Push the repository to GitHub.
2. In Render choose **New > Blueprint** and pick the repository. `render.yaml` creates the web service and health check (`/healthz`).
3. Fill the variables marked *sync: false* in the Render dashboard: `ADMIN_PASSWORD`, `PUBLIC_BASE_URL`, `RECRUITMENT_LEAD_EMAIL`, `ZAPIER_WEBHOOK_URL`, and (if used) `DATABASE_URL` or `SUPABASE_URL` + `SUPABASE_SERVICE_KEY`.
4. Keep `COOKIE_SECURE=true` and `TRUST_PROXY=true` (already set in `render.yaml`).

**Railway** - add a Volume mounted at `/data` and set `DATABASE_PATH=/data/recruitment.db` (or use Supabase). The `Procfile` runs gunicorn.

**Your own server** - see `deploy/` for a `systemd` service (`recruitment-portal.service`) and an `nginx.conf`. Start command:

```bash
gunicorn app:app --bind 0.0.0.0:${PORT:-5000} --workers 2 --timeout 60
```

Behind HTTPS always set `COOKIE_SECURE=true` and `TRUST_PROXY=true`. The Excel report is a file on the server's disk, so on hosts with temporary disks download it before restarts (it is rewritten after every change).

---

## How recruiters use it

1. **Candidates** - ranked by score (or by the recruiters' own rating). Candidates who **Passed** (or were set to *Shortlisted*) have a green **Send shortlist email** button.
2. **Shortlist email** - hands the email to Zapier: congratulations, interview within 5 business days, Google Meet. You can add a date/time and paste a `https://meet.google.com/...` link on the candidate's page. The stage becomes *Interview invited* only if Zapier accepted the email.
3. **Interview and ranking** - record notes, rate Skills / Communication / Culture / Overall (1-5) and answer "Is this the right person for the job?" (Yes / Maybe / No). Several recruiters can each add their own.
4. **Interviews board** - ranks everyone interviewed by the recruiters' average rating.
5. **Decide** - on the candidate page choose **Selected** or **Not selected** under *Hiring stage*. A box "Email the candidate the result" appears (ticked). Press **Update stage**, confirm, and the email goes out through the same Zap.
   - Each result email is sent **once**; pressing again does not send it twice. If sending failed, press **Update stage** again to retry.
   - A candidate who was sent *Selected* cannot be sent *Not selected* (and the other way round).
   - Untick the box to change the stage without emailing.
6. **Requests** - when the chatbot cannot answer or the visitor asks for a person, the request is saved here and the recruitment lead and visitor are emailed. Reply by email, then mark it resolved.
7. **Stages** a candidate moves through: Applied, Shortlisted, Interview invited, Interviewed, Selected, Not selected.

---

## How candidates are scored

Each position has editable **criteria** (Recruiters > Criteria): required keywords, preferred keywords, minimum years of experience, minimum education and weights.

- **Experience** sub-score = `min(1, years found / minimum years)`. Years found is the largest number followed by *year(s)* or *yrs* in the CV.
- **Education** uses the ranks Diploma 1, Bachelor 2, Master 3, PhD 4 and the highest level found (whole words only).
- **Keywords** = share of required keywords found and share of preferred keywords found.
- **Score** = `100 x sum(weight x sub-score) / sum(weights)`.
- **Decision**
  - **Pass** - score 70 or more **and** the minimum years and education are met.
  - **Needs Review** - score from 60 up to 70 (a recruiter decides).
  - **Reject** - everything else. A perfect score still rejects if a hard requirement fails.
- An automatic Reject sends no email by itself; the 14-business-day wording in the confirmation email covers it.

Default positions: Research Fellow, Policy Analyst, Research Assistant, Data Analyst, Communications Officer, Program Manager, Administrative Assistant and Intern. The Intern settings are an assumption - adjust them.

In testing, **all 20 test CVs were decided as expected** (7 Pass, 6 Needs Review, 7 Reject).

---

## Interns, chatbot, Excel report and usage page

**Interns** - applicants choose *Intern* and an optional preferred department. After an intern is **Selected**, open **Interns** and place them in a department (Software Development, Data & Analytics, UX / UI Design, Quality Assurance, Cloud & DevOps, Cybersecurity, Research & Policy, Marketing & Communications, Operations & Administration) with a supervisor and start date. Starter courses are added automatically; post updates and press **Email the link**. The intern opens `/intern/<secret>`. Edit the department list in `config.py` (`DEPARTMENTS`).

**Chatbot** - open **Chatbot** in the menu to edit the 16 question-and-answer topics and see questions the bot could not answer. It matches the visitor's words to a topic, answers, and otherwise offers **Talk to a recruiter**. To show it on Think Tank's own website, see the instructions on the **Chatbot** page (it loads `/chat-widget` through `static/embed.js`, and `EMBED_ALLOWED_ORIGINS` must list the website).

**Excel report** - `recruitment_candidates.xlsx` is rewritten after every application, stage change, interview and placement. Download it from **Excel** in the menu. Sheets: Summary, Candidates (ranked, colour-coded, score bars), Interviews, Interns.

**Usage page** (`/admin/usage`) - visitors per day, page views, form opened versus application sent, chatbot questions answered or not understood, devices, browsers and referring sites. It records the day, event kind, page *pattern* (never secret links), status, device type, browser name, referring *site name* and an anonymous daily visitor code. It **never** records IP addresses, cookies, names, emails, message text or query strings, and it skips visitors who send *Do Not Track*. Turn it off with `TRACK_USAGE=false`. Mention this in your privacy notice.

---

## Testing

```bash
python -m unittest discover -s tests -v
```

The suite has **180 tests**: 168 run and 12 are skipped by default (they need a real Postgres), with **0 failures**. It covers applying and validation, the confirmation email, scoring (including a 20-CV batch through the real PDF reader), shortlist rules, interview records, selected / not selected emails, interns, the chatbot and hand-off, usage tracking, security checks, failure tolerance (Zapier down), and that **only Zapier sends email**.

It was run in three modes:

| Mode | How |
|---|---|
| 1. SQLite (default) | `python -m unittest discover -s tests` |
| 2. Real local PostgreSQL 16 | `TEST_POSTGRES=1 python -m unittest discover -s tests` |
| 3. Simulated Supabase web API (calls the real `portal_sql` function) | `TEST_POSTGRES=1 TEST_REST=1 python -m unittest discover -s tests` |

An end-to-end run through the real server with a **stand-in for Zapier** produced 54 emails, all with the correct recipient and subject. A real Supabase project and a live public host were **not** tested yet.

---

## Project layout

```text
app.py              Flask app: pages, admin, API, login wall, rate limits, security headers
service.py          Business rules: apply, re-screen, stage changes (with emails), interviews, interns, hand-off
screener.py         Scoring: experience, education, keywords, hard requirements, decision
parsers.py          Reads PDF, DOCX and TXT CVs with friendly errors
database.py         The 15 tables, migrations, queries (SQLite, Postgres, or Supabase web API)
pgcompat.py         Lets the same queries run on Postgres; web-API client; portal_sql setup
integrations.py     Zapier webhook calls, payloads, phone-number normalising, test helpers
emails.py           All email wording
excel_export.py     Four-sheet Excel report
chatbot.py          FAQ matching, greetings, human-request detection, fallback
usage.py            Anonymous usage statistics
config.py           Settings helpers, default positions, FAQ, departments, stages
sheets.py           Optional Google Sheets sync
bot.py, whatsapp.py, infobip/   Optional WhatsApp / Infobip chat channel (NOT connected - see status)
templates/          Jinja pages (form, thank-you, dashboard, candidates, interns, chatbot, usage, ...)
static/             CSS and vanilla JavaScript (chat window, embed.js, widget)
supabase/           schema.sql and the Supabase guide
tools/              make_supabase_schema.py, migrate_sqlite_to_supabase.py, check_db_connection.py
deploy/             systemd service and nginx config
tests/              180 tests
render.yaml         Render Blueprint
Procfile            gunicorn start command
requirements.txt    Pinned dependencies
.env.example        Every setting, with safe defaults (no secrets)
schema.sql          SQLite schema (reference)
```

---

## Security and privacy

- **Change the default password `0000`** before anyone else can reach the site. The login locks out after 5 wrong tries (5 minutes).
- The repository holds **no passwords, keys or tokens**. `.env`, databases (`*.db`), Excel files (`*.xlsx`) and service-account files are excluded by `.gitignore`. Test data uses `example.org` addresses.
- **If a secret is ever committed by mistake, rotate it** (create a new Zapier Catch Hook, change the password, rotate the Supabase key) - deleting the commit does not remove it from history.
- The database and Excel file hold personal information (names, phone numbers, CV text). Treat them under **POPIA / GDPR**: the form records consent; delete applications you no longer need; choose your Supabase region carefully.
- Applicant text is always escaped (no HTML injection) and Excel cells are stored as text (no formula injection).
- The chatbot is rule-based; nothing is sent to an AI service.
- Everything the portal sends to Zapier is a fixed set of fields; Zapier then sees the candidate's name, email and the message text, so use a Zapier account that Think Tank controls.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `Could not import 'app'` | You are in the wrong folder. `cd` into the folder with `app.py`. |
| "NOT sent: ZAPIER_WEBHOOK_URL not set" | Put the webhook address in `.env` (same folder as `app.py`) and restart. |
| Portal says "handed to Zapier" but no email arrives | Open the Zap's **Zap runs**: the Filter probably stopped it (`send_email` must match `yes`) or the Gmail step errored. |
| `SSLError` / `CERTIFICATE_VERIFY_FAILED` in the Integrations log | Your network inspects HTTPS. Run `pip install truststore`, restart, and press **Send test payload** again. |
| A candidate got two emails | An old extra Zap is also emailing them. Turn it off. |
| Emails land in spam | Send from a proper address or domain in Gmail / Outlook and ask recipients to mark it as not spam. |
| PDF says "could not read" | Scanned-image PDFs have no text. Use a text PDF or DOCX. |
| Start-up fails with a **connection timeout** to Supabase | The database port is blocked by the network. Run `python tools/check_db_connection.py`; if it reports no answer, use the web-API route (`SUPABASE_URL` + `SUPABASE_SERVICE_KEY`). A placeholder such as `[YOUR-PASSWORD]` left in `DATABASE_URL` is also reported. |
| "Tables are missing" in Supabase | Paste `supabase/schema.sql` into the SQL editor, run it, restart. |
| The terminal seems frozen | The site is running in that window - open a second terminal for other commands. |

---

## Project status: what is done and what is not

| Area | Status |
|---|---|
| Apply, screen, rank, shortlist, interview, selected / not selected, interns | **Built and tested** |
| FAQ chatbot with editable answers and human hand-off; chat window for a website | **Built and tested** |
| Dashboard, Excel report, usage page | **Built and tested** |
| Email through Zapier | **Working** (confirmed by the team; end-to-end test used a stand-in) |
| Online database (Supabase) | **Partly working.** Tested on a local Postgres 16 and a simulated web API. **Not yet confirmed against the team's own Supabase project.** |
| Public deployment | **Still to do.** Runs on a local server; publish with Render, Railway or your own server |
| SMS messages | **Not built** (removed from scope by a change request) |
| Interview reminder 24 hours before | **Not built** (roadmap) |
| WhatsApp / Infobip chat channel | **Not connected.** The code and tests exist, but the team could not connect the Infobip account in time, so it is not part of the working solution. Leave the Infobip settings blank. |
| Individual recruiter accounts, audit log, candidate deletion and retention rules | **Roadmap** (the portal currently uses one shared recruiter password) |

**Suggested next steps for Think Tank:** (1) publish the portal at a Think Tank address; (2) run `tools/check_db_connection.py` against a real Supabase project and confirm; (3) change the recruiter password and review the chatbot answers and scoring criteria; (4) add individual recruiter accounts and a privacy notice before using real applicant data; (5) add SMS and the 24-hour reminder if wanted ;(6) Add Infobip to the application for the chatbot to be agentic 

---

## Credits and licence

Built by **Group 12** (IFS325 / IFS353): Gomolemo Tsoagong (Project Manager), Tererai Gwande, Natasha Kabuya, Jason Brink and Viwe Gonya, for Think Tank Software Solutions.

Concepts only - no code was copied. The per-job hiring pipeline, per-round candidate ratings and side-by-side comparison were inspired by [SpotAxis](https://github.com/Assystant/SpotAxis) (MIT licence). The interview stage with Google Meet and the scorecard idea were inspired by [OpenATS](https://github.com/chamals3n4/OpenATS) (Apache 2.0 licence).

**Licence:** not yet chosen. Add a `LICENSE` file before sharing the code more widely.
