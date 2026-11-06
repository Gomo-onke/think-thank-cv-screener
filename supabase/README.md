# Put the database online with Supabase

The portal can keep **all candidate details, screening results, interviews, interns, chat requests and website-usage
statistics** in an online Supabase (Postgres) database instead of a local file. Nothing changes on the website; you
only set one setting, `DATABASE_URL`. Without it the portal keeps using the local SQLite file as before.

What is saved online: every field of the application form, the CV **text** (not the CV file itself), the score and
decision, the hiring stage, interviews, interns, FAQ, chat requests, the email log, and the usage events below.

## 1. Create the Supabase project (5 minutes)

1. Sign in at https://supabase.com > **New project**. Choose a region close to your users (South Africa: *eu-west*
   is usually the nearest) and set a **database password**. Save it - you need it in step 3.
2. Open **SQL Editor > New query**, paste the whole of [`schema.sql`](schema.sql) and press **Run**.
   This creates the tables and turns on security (see "Security" below). It is safe to run again.
3. Open **Project settings > Database > Connection string**. Pick the **Transaction pooler** (port 6543) if you host on
   Render/Railway/any server; pick **Direct** (port 5432) only if your host supports IPv6. Copy the URL and put your
   password where it says `[YOUR-PASSWORD]`. It looks like:

       postgresql://postgres.abcdefghij:YOUR-PASSWORD@aws-0-eu-west-1.pooler.supabase.com:6543/postgres

   If the password contains characters such as `@ : / # ?`, URL-encode them (`@` becomes `%40`).

## 2. Connect the portal

Install the driver once (it is in `requirements.txt`):

    pip install -r requirements.txt

**On your computer**: add this line to `.env`

    DATABASE_URL=postgresql://postgres.abcdefghij:YOUR-PASSWORD@aws-0-eu-west-1.pooler.supabase.com:6543/postgres

then start the portal as usual (`python app.py`). Open `http://localhost:5000/healthz` - it should say
`"database": "postgres"`. Submit a test application, then look in Supabase > **Table Editor > candidates**: the row is
there.

**On Render**: Dashboard > your service > **Environment** > add `DATABASE_URL` (same value). The persistent disk is
no longer needed for the database (the Excel report file still uses the disk if you keep downloading it; it can be
regenerated at any time from the dashboard).

### 2b. If your network blocks the database port: use the web API instead

Some networks (campus Wi-Fi, firewalls, security software) let you open the database port but drop the traffic, so the
portal times out. Supabase's web API uses ordinary HTTPS, which works almost everywhere.

1. Run the **latest** [`schema.sql`](schema.sql) in the SQL editor (it adds one function, `portal_sql`, which the portal
   calls; only the `service_role` key may run it).
2. Supabase > Project settings > **API Keys**: copy the **Project URL** and the **secret key** (the `service_role` key; on newer
   projects it starts with `sb_secret_`). **Not** the anon / publishable key: with Row Level Security on, that one can read nothing.
3. In `.env` (or Render's environment settings) set

       SUPABASE_URL=https://abcdefghij.supabase.co
       SUPABASE_SERVICE_KEY=your-secret-key

   When both are set the portal uses the web API and ignores `DATABASE_URL`. Restart, then run `python tools\check_db_connection.py`
   and open `/healthz`: it should say `"via": "web-api"`.

What to know about this mode:
* The secret key bypasses Row Level Security and can do **everything** to your database. Treat it like the database password:
  server settings only, never in the browser, never in git. If it leaks, rotate it in Supabase.
* It is slower: every query is a web request, so pages that run many queries (the dashboard) take a little longer.
* Each statement is its own transaction (no rollback of several statements together). The portal saves each step on its own, so
  normal use is unaffected, but a crash between two steps of one action can leave it half done.
* Tables are not created automatically in this mode: run `schema.sql` yourself (the portal checks and tells you if it is missing).
* The portal only ever sends its own fixed queries; visitor input is passed as values and escaped by the database
  (`quote_literal`), and tests cover quotes, `;`, `--` and `$1` inside values.

## 3. Move the data you already have (optional)

If you already collected candidates in the old SQLite file (`recruitment.db`):

    python tools/migrate_sqlite_to_supabase.py --dry-run     # shows what would be copied
    python tools/migrate_sqlite_to_supabase.py               # copies it (safe to run twice)

Ids are kept, so interview links and the intern private links keep working.

## 4. See how the website is used

Sign in as a recruiter and open **Usage** in the top menu (`/admin/usage`): visitors per day, page views, how many people
opened the form versus sent an application, chatbot questions answered or not understood, WhatsApp messages, devices,
browsers and where visitors came from. You can also query the `usage_events` table directly in Supabase.

What is recorded for each visit: the day, the kind of event, the page *pattern* (e.g. `/intern/<token>`, never the
secret link itself), the HTTP status, device type, browser name, the referring **site name**, and an anonymous
visitor code that changes every day.

What is **never** recorded: IP addresses, the full browser string, cookies, names, emails, message text or query strings.
Visitors whose browser sends *Do Not Track* / *Global Privacy Control* are skipped. Switch tracking off with
`TRACK_USAGE=false`. Events older than `USAGE_RETENTION_DAYS` (default 400) are deleted automatically.
Mention this in your privacy notice.

## Security (important)

* Row Level Security is **on** for every table, with no policies, and the `anon` / `authenticated` roles have no
  privileges. Anyone who finds your project URL or the public *anon key* can therefore read **nothing**.
* Only the portal server can read and write, using the database password in `DATABASE_URL`. Keep that value secret:
  put it only in `.env` (not committed to git) and your host's environment settings. Never put it in a web page.
* The `settings` table holds the site's session secret, so this matters. If the password ever leaks, reset it in
  Supabase > Project settings > Database and update `DATABASE_URL`.
* Candidate details are personal information (POPIA / GDPR). Choose a region you are comfortable with, and delete
  applications you no longer need.

## Other settings

| Setting | Meaning |
|---|---|
| `SKIP_SCHEMA_SETUP=true` | Do not check/create tables at start-up (use after you ran `schema.sql` yourself and want the fastest boot). |
| `TRACK_USAGE=false` | Turn website usage tracking off. |
| `USAGE_RETENTION_DAYS=400` | How long usage events are kept. |

## Changing the tables later

The tables are defined once in `database.py`. After changing them, run `python tools/make_supabase_schema.py` to
regenerate `supabase/schema.sql` (a test fails if it is out of date), and run the new file in the SQL editor.
New columns on candidates and requests are added automatically at start-up.

## How this was tested

The whole test suite (`python -m unittest discover -s tests`) passes on SQLite, and also on a **real local Postgres 16**
(`TEST_POSTGRES=1 python -m unittest discover -s tests`), including the schema file, Row Level Security, the
migration and the usage tracking. The web-API route is tested with `TEST_POSTGRES=1 TEST_REST=1`: the whole suite runs through a stand-in
for Supabase's HTTPS endpoint that calls the real `portal_sql` function on Postgres. A live Supabase project, the real HTTPS
call (including how Supabase's newer `sb_secret_` keys are sent) and the `psycopg` driver itself could not be tested in the
build environment (no internet access to PyPI/Supabase), so do the quick check once on your side
(`python tools\check_db_connection.py`).
