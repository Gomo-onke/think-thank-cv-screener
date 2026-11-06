# Think Tank Software Solutions - Recruitment Portal

A Python **Flask + HTML + CSS** website (SQLite database, Excel report, and **all emails sent through a Zapier webhook**) with a clean
white / blue / black design.

| Who | What they see | Password? |
|---|---|---|
| **Applicants** (public) | Application form with CV upload, a thank-you page, an FAQ chatbot | No |
| **Recruiters** | Dashboard, scores and ranking, every application detail, shortlist-email button, interview notes + personal ranking, interns, chatbot editor, criteria, integrations, Excel download | **Yes - once per session** (default `0000`) |
| **Interns** (after being placed) | Their own private page: updates + recommended courses | Secret link only |

Applicants are **never shown their score or decision** - only "application received".

---

## Chatbot on your website and WhatsApp (Infobip)

The same FAQ chatbot can be shown on any website with one line of HTML, answer on WhatsApp through Infobip, or be
called from a chatbot built in Infobip Answers. See **`infobip/START_HERE.md`** (import the FAQ and company information into Infobip, connect it to your website) and **`infobip/SETUP.md`** (WhatsApp). Emails still go only
through Zapier; Infobip is used only for the WhatsApp chat channel. New `.env` settings: `INFOBIP_WEBHOOK_SECRET`,
`INFOBIP_BASE_URL`, `INFOBIP_API_KEY`, `INFOBIP_WHATSAPP_SENDER`, `BOT_API_KEY`, `EMBED_ALLOWED_ORIGINS`.

## Online database and usage tracking (Supabase)

Set `DATABASE_URL` and every candidate, result and chat request is saved in an online Supabase database; **Admin > Usage** shows how the website is used (no IP addresses or names stored). Steps, security and the data-migration tool: [`supabase/README.md`](supabase/README.md).

## 1. Run it on your computer (Windows PowerShell)

```powershell
cd path\to\think-tank-recruitment-portal
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
if (!(Test-Path .env)) { copy .env.example .env }
python -m flask --app app run
```

Open <http://127.0.0.1:5000>. Applicants use `/`; recruiters click **Recruiter login** and type the password once.
The PowerShell window must stay open while the site runs (press Ctrl+C to stop it).
Edit `.env` in Notepad (not in PowerShell), then stop and restart the site.

Run the tests: `python -m unittest discover -s tests -v`

## 2. How to put everything together

1. **Run it** (above) and submit a test application at `/`. You land on the thank-you page.
2. **Log in** at `/admin/login` with the password (default `0000`). Open **Candidates** - your test applicant is scored.
3. **Change the password**: set `ADMIN_PASSWORD=` in `.env` and restart.
4. **Zapier = every email.** The portal never talks to an email provider itself. It hands each finished email to your Zapier webhook and your Zap delivers it. Set it up in section 2a below, then put the webhook address in `.env` as `ZAPIER_WEBHOOK_URL=` and restart.
   *No webhook = no emails.* The portal says so plainly instead of pretending ("NOT sent: ZAPIER_WEBHOOK_URL not set").
5. **Recruiter copy**: set `RECRUITMENT_LEAD_EMAIL=` in `.env` and the recruitment lead also gets a summary email (candidate, score, decision) for every new application. Leave it blank to turn that off.
6. **Test**: **Integrations → Send test payload** (so Zapier can see the fields), then **Send test email** and check the inbox.
7. **Excel**: `recruitment_candidates.xlsx` (beside the database) is rewritten after every application, stage change, interview and placement. Download it any time from the **Excel** link in the menu. Sheets: Summary, Candidates (ranked, colour-coded, score bars), Interviews, Interns.
8. **Human hand-off**: when the chatbot cannot answer (or the visitor asks for a person) it offers **Talk to a recruiter**. The request is saved and listed under **Requests** in the menu, and Zapier emails the recruitment lead and the visitor. Reply to the visitor by email, then mark the request resolved.
9. **Chatbot**: open **Chatbot** in the menu and **review every answer** - the supplied ones are generic samples about the hiring process, not real company policy. Questions the bot could not answer are listed so you can add them.
10. **Criteria**: open **Criteria** to edit positions, keywords, weights and the Pass / Needs Review thresholds. The **Intern** position's settings are an assumption - adjust them.
11. **Put it online** (section 5) so applicants can reach it.

## 2a. Build the Zap (about 10 minutes, one Zap does everything)

1. In Zapier click **Create Zap**. Trigger: **Webhooks by Zapier → Catch Hook** (leave "Pick off a child key" empty). Copy the **Custom Webhook URL** into `.env` as `ZAPIER_WEBHOOK_URL=`, save, restart the site.
2. In the site: **Integrations → Send test payload**. Back in Zapier press **Test trigger**; you should see a record with all the fields.
3. Add a **Filter** step: *Only continue if* `send_email` **(Text) Exactly matches** `yes`.
   (Data-only events - re-screens, stage changes, placements - have `send_email = no` and stop here.)
4. Add the delivery step: **Gmail → Send Email** (or Outlook, or **Email by Zapier**), and map:
   * **To** → `email_to`
   * **Subject** → `email_subject`
   * **Body** → `email_body` (plain text; for Gmail set *Body Type* to plain)
   * **From name** → *Think Tank Software Solutions Recruitment* (optional)
5. In the site: **Integrations → Send test email** (type your own address). Test the Zap step, then **Publish**.
6. Done. This one Zap now sends **all** of these automatically:

| `event` | Email goes to | Content |
|---|---|---|
| `application_received` | the candidate | "We have received your application ... if you do not hear from us within 14 business days, please consider it unsuccessful" |
| `recruiter_notification` | `RECRUITMENT_LEAD_EMAIL` | candidate, score, decision, keyword summary |
| `human_escalation` | `RECRUITMENT_LEAD_EMAIL` | a chat visitor pressed **Talk to a recruiter** (name, email, question) |
| `human_escalation_ack` | the visitor | "we have passed your question to our recruitment team" |
| `shortlist_email` | the candidate | congratulations, interview within 5 business days, Google Meet details (button on the Candidates page) |
| `selection_email` | the candidate | stage set to **Selected**: congratulations, what happens next (formal offer, documents, reply to confirm) |
| `rejection_email` | the candidate | stage set to **Not selected**: a respectful "we will not be taking your application forward" |
| `intern_welcome_email` | the intern | the personal page link |
| `application_rescreened`, `stage_changed`, `intern_placed`, `test` | nobody | data only (use for Google Sheets, Slack, ...) |

Every payload also carries `candidate_name`, `email`, `phone`, `phone_international`, `position`, `score`, `status`, `stage`, `preferred_department`, `notes`, `timestamp`, so you can add extra steps (log to a Google Sheet, post to Slack, send an SMS with a Zapier SMS app) without changing the website.

**Important:** "sent" on the website means *Zapier accepted the webhook*. Whether Gmail then delivered it is shown in the Zap's **Zap runs** history. If you earlier built a separate "application received" Zap on this webhook, **turn it off** or candidates get two emails.

## 3. The recruiter workflow

1. **Candidates** page: ranked by score (or by the recruiters' own rating). Candidates who **Passed** (or whom you set to *Shortlisted*) get a green **Send shortlist email** button on their row.
2. The button hands the shortlist email to Zapier, which emails the candidate: congratulations, **interview within the next 5 business days**, **Google Meet** video call. On the candidate's page you can also add the date/time and paste a `https://meet.google.com/…` link. The stage becomes *Interview invited* only if Zapier accepted the email.
3. **Interview & ranking** page: record the discussion notes, rate Skills / Communication / Culture / Overall (1-5) and answer **"Is this the right person for the job?"** (Yes / Maybe / No). Several recruiters can each add their own. Then press **Select candidate** or **Not selected**.
4. **Interviews** page ranks everyone interviewed by the recruiters' average rating.

### Emailing the result when the hiring stage changes

On a candidate's page, pick **Selected** or **Not selected** under *Hiring stage*. A box *"Email the candidate the result"* appears (ticked); press **Update stage**, confirm, and the email goes out through the same Zap (no change to the Zap is needed). Details:
* Each email is sent **once per candidate**; pressing the button again does not send it twice. If sending failed (for example Zapier is not set up), press **Update stage** again to retry.
* If a candidate was already sent *Selected*, the *Not selected* email is refused (and the other way round), so nobody receives two contradictory emails. Contact them directly instead.
* Untick the box to change the stage without emailing. Edit the wording in `emails.py` (`selected`, `not_selected`).

## 4. Interns

Applicants choose **Intern** as the position and an optional preferred department. After an intern is **Selected**, open **Interns** and place them in a department (Software Development, Data & Analytics, UX / UI Design, Quality Assurance, Cloud & DevOps, Cybersecurity, Research & Policy, Marketing & Communications, Operations & Administration), with a supervisor and start date. Starter courses are added automatically; add your own too. Post **updates** addressed to the intern and press **Email the link** (sent through Zapier) - the intern opens their private page (`/intern/<secret>`) to read updates and see which courses to take. Edit the department list in `config.py` (`DEPARTMENTS`).

## 5. Hosting

With `DATABASE_URL` set (Supabase) the host needs no disk at all. Without it, SQLite is a **file**, so wherever the site runs needs a disk that survives restarts.
* **Render** (easiest): push to GitHub → Render → *New → Blueprint* → pick the repo (`render.yaml` is included; with Supabase no disk is needed). Fill the secret variables in the Render dashboard.
* **Railway**: add a Volume, mount it at `/data`, set `DATABASE_PATH=/data/recruitment.db`.
* **Your own server**: see `deploy/` (systemd service + nginx).
* Behind HTTPS set `COOKIE_SECURE=true` and `TRUST_PROXY=true`.

Do **not** use a free host with a temporary disk - the database and Excel file would be wiped on every restart.

## 6. Security and privacy notes

* `0000` can be guessed in seconds. The login locks out after 5 wrong tries (5 minutes), but **change it** before real use.
* The Excel file and database contain personal information (names, phones, CVs). Treat them accordingly (POPIA / GDPR): the form records consent, and you should delete applications you no longer need.
* Applicant text is always escaped (no HTML injection) and Excel cells are stored as text (no formula injection).
* The chatbot is rule-based: nothing is sent to an AI service.
* WhatsApp chats pass through Infobip. The portal keeps a person's WhatsApp number only when they ask for a recruiter (in Admin > Requests), plus a short-lived conversation state; ordinary questions are not stored with their number. The chat bubble and the WhatsApp greeting ask people not to send ID numbers or passwords.
* The chat endpoints for Infobip refuse every call unless `INFOBIP_WEBHOOK_SECRET` / `BOT_API_KEY` is set and matches, so nobody else can make your Infobip account send WhatsApp messages.

## 7. Troubleshooting

| Problem | Fix |
|---|---|
| `Could not import 'app'` | You are in the wrong folder. `cd` into the project folder (where `app.py` is). |
| `skipped: ZAPIER_WEBHOOK_URL not set` | `.env` must be in the same folder as `app.py`, contain the real URL, and the site must be restarted. |
| "The email was NOT sent: skipped: ZAPIER_WEBHOOK_URL not set" | Put the webhook address in `.env` (section 2a) and restart. |
| Website says "handed to Zapier" but no email arrives | Open the Zap's **Zap runs**: the Filter probably stopped it (`send_email` must match `yes`) or the Gmail step errored. |
| Integrations log says `SSLError` / `CERTIFICATE_VERIFY_FAILED` | Your network inspects HTTPS. Run `pip install truststore` (or `pip install --use-feature=truststore truststore`), restart the site, press **Send test payload** again. |
| Candidate got two emails | An old extra Zap is also emailing them. Turn it off. |
| Emails land in spam | Send from a proper address/domain in Gmail/Outlook, and ask recipients to mark it as not spam. |
| PDF says "could not read" | Scanned image PDFs have no text. Use a text PDF/DOCX or paste the text. |
| PowerShell seems frozen | The site is running in that window - open a second PowerShell for other commands. |

## 8. Files

`app.py` routes · `bot.py` text-chat conversation (WhatsApp / API) · `whatsapp.py` Infobip WhatsApp channel · `static/embed.js` website chat button · `infobip/` setup guide and helper scripts · `service.py` business rules · `screener.py` scoring · `database.py` SQLite + Postgres schema · `pgcompat.py` Postgres adapter · `usage.py` usage tracking · `supabase/` online-database guide and schema · `tools/` schema generator and SQLite→Supabase migration · `integrations.py` Zapier webhooks · `emails.py` message wording · `excel_export.py` Excel · `chatbot.py` FAQ bot · `config.py` choices and defaults · `templates/` + `static/` pages and styling · `schema.sql` SQLite schema (reference) · `tests/`.

## Credits and inspiration

Concepts only - no code was copied. The per-job hiring pipeline, per-round candidate ratings and side-by-side comparison were inspired by
[SpotAxis](https://github.com/Assystant/SpotAxis) (MIT licence); the interview stage with Google Meet and the scorecard idea by
[OpenATS](https://github.com/chamals3n4/OpenATS) (Apache 2.0 licence).
