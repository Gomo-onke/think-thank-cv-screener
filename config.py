"""Configuration: environment variables, default criteria, departments, FAQ."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def env_bool(name: str, default: bool = False) -> bool:
    raw = env(name)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


# --- Organisation ------------------------------------------------------------
ORGANISATION_NAME = env("ORGANISATION_NAME", "Think Tank Software Solutions")
RESPONSE_WINDOW_BUSINESS_DAYS = 14   # "no reply within 14 business days = unsuccessful"
INTERVIEW_WINDOW_BUSINESS_DAYS = 5   # shortlisted candidates are interviewed within 5 business days

# --- Storage -----------------------------------------------------------------
DB_PATH = env("DATABASE_PATH", str(BASE_DIR / "recruitment.db"))
# The Excel workbook is rewritten after every change. Default: next to the database.
EXCEL_PATH = env("EXCEL_PATH", str(Path(DB_PATH).with_name("recruitment_candidates.xlsx")))

RECRUITMENT_LEAD_EMAIL = env("RECRUITMENT_LEAD_EMAIL")
RESCREEN_NOTIFY_CANDIDATE = env_bool("RESCREEN_NOTIFY_CANDIDATE", False)

# --- Online database (Supabase = Postgres) --------------------------------------
# Blank = the SQLite file above. Set it to your Supabase connection string to keep ALL data online (supabase/README.md).
DATABASE_URL = env("DATABASE_URL")
# Supabase over HTTPS (works where the database port is blocked). When BOTH are set the web API is used and DATABASE_URL is ignored.
SUPABASE_URL = env("SUPABASE_URL").rstrip("/").removesuffix("/rest/v1").rstrip("/")
SUPABASE_SERVICE_KEY = env("SUPABASE_SERVICE_KEY")

# --- Zapier ------------------------------------------------------------------
ZAPIER_WEBHOOK_URL = env("ZAPIER_WEBHOOK_URL")

# --- Chat channels: website widget, Infobip WhatsApp, Infobip Answers --------------
# Infobip is used ONLY for the WhatsApp chat channel (never for email - email is Zapier only).
INFOBIP_BASE_URL = env("INFOBIP_BASE_URL")                  # e.g. xxxxx.api.infobip.com (from your Infobip home page)
INFOBIP_API_KEY = env("INFOBIP_API_KEY")                    # Infobip API key used to send WhatsApp replies
INFOBIP_WHATSAPP_SENDER = env("INFOBIP_WHATSAPP_SENDER")    # your WhatsApp number, digits only, e.g. 27821234567
INFOBIP_WEBHOOK_SECRET = env("INFOBIP_WEBHOOK_SECRET")      # shared secret that Infobip adds to the webhook URL
BOT_API_KEY = env("BOT_API_KEY")                            # key for POST /api/bot/message (Infobip Answers API element)
EMBED_ALLOWED_ORIGINS = env("EMBED_ALLOWED_ORIGINS")        # sites allowed to embed the chat widget (blank = any site)

# --- Google Sheets (optional) ------------------------------------------------
GOOGLE_CREDENTIALS_FILE = env("GOOGLE_CREDENTIALS_FILE")
SHEET_ID = env("SHEET_ID")
SHEET_CANDIDATES_TAB = env("SHEET_CANDIDATES_TAB", "Candidates")
SHEET_RESULTS_TAB = env("SHEET_RESULTS_TAB", "Results")

HTTP_TIMEOUT = int(env("HTTP_TIMEOUT", "15"))
MAX_UPLOAD_MB = int(env("MAX_UPLOAD_MB", "10"))

# --- Scoring constants (same rubric as before) --------------------------------
EDU_RANK = {"none": 0, "diploma": 1, "bachelor": 2, "master": 3, "phd": 4}
EDU_LABEL = {0: "None detected", 1: "Diploma", 2: "Bachelor", 3: "Master", 4: "PhD"}

DEFAULT_SETTINGS = {
    "pass_threshold": "70",
    "review_threshold": "60",
    "require_all_required_keywords": "0",
}

# --- Hiring pipeline -----------------------------------------------------------
STAGES = ["Applied", "Shortlisted", "Interview invited", "Interviewed", "Selected", "Not selected"]
SHORTLIST_ELIGIBLE_STAGES = {"Shortlisted", "Interview invited", "Interviewed"}

# --- Application form choices ---------------------------------------------------
QUALIFICATIONS = ["Matric / Grade 12", "Certificate", "Diploma", "Bachelor's degree", "Honours degree",
                  "Master's degree", "PhD / Doctorate", "Other"]
WORK_AUTHORISATION = ["South African citizen", "Permanent resident", "Valid work permit / visa",
                      "No - I need sponsorship"]
WORK_ARRANGEMENTS = ["On-site", "Hybrid", "Remote", "No preference"]
NOTICE_PERIODS = ["Immediately", "1 week", "2 weeks", "1 month", "2 months", "3 months or more"]
REFERRAL_SOURCES = ["LinkedIn", "Our website", "Job board", "Friend or employee referral",
                    "University / college", "Social media", "Other"]

INTERN_POSITION = "Intern"

# --- Departments interns can be placed in, with starter course suggestions -------
# Course titles are well-known public courses; edit freely on each intern's page.
DEPARTMENTS = {
    "Software Development": {
        "blurb": "Building and maintaining our web and mobile software.",
        "courses": [
            ("CS50: Introduction to Computer Science", "Harvard / edX", "Core programming fundamentals."),
            ("Python for Everybody", "University of Michigan / Coursera", "Python basics for building real tools."),
            ("Responsive Web Design", "freeCodeCamp", "HTML and CSS foundations."),
            ("Git and GitHub for Beginners", "Any reputable provider", "Version control used on every project."),
        ],
    },
    "Data & Analytics": {
        "blurb": "Turning data into dashboards, reports and insight.",
        "courses": [
            ("Google Data Analytics Certificate", "Google / Coursera", "Data cleaning, analysis and visualisation."),
            ("SQL for Data Analysis", "Any reputable provider", "Querying databases confidently."),
            ("Data Visualization with Tableau or Power BI", "Vendor learning paths", "Dashboards for non-technical readers."),
            ("Statistics Fundamentals", "Khan Academy", "The maths behind good analysis."),
        ],
    },
    "UX / UI Design": {
        "blurb": "Designing clear, usable interfaces.",
        "courses": [
            ("Google UX Design Certificate", "Google / Coursera", "The full design process, from research to prototype."),
            ("Figma for Beginners", "Figma learning resources", "The tool our designers use."),
            ("Accessibility Fundamentals", "W3C Web Accessibility Initiative", "Designing for everyone."),
        ],
    },
    "Quality Assurance": {
        "blurb": "Testing our software so it works for real users.",
        "courses": [
            ("ISTQB Foundation Level syllabus", "ISTQB", "Standard testing vocabulary and techniques."),
            ("Test Automation with Python (pytest)", "Any reputable provider", "Automating repetitive checks."),
            ("Git and GitHub for Beginners", "Any reputable provider", "Working alongside developers."),
        ],
    },
    "Cloud & DevOps": {
        "blurb": "Running, deploying and monitoring our systems.",
        "courses": [
            ("AWS Cloud Practitioner Essentials", "AWS Training", "Cloud basics and core services."),
            ("Microsoft Azure Fundamentals (AZ-900)", "Microsoft Learn", "Cloud concepts on Azure."),
            ("Linux Command Line Basics", "Any reputable provider", "Comfort on the server."),
            ("Docker Fundamentals", "Docker documentation", "Packaging software to run anywhere."),
        ],
    },
    "Cybersecurity": {
        "blurb": "Keeping our systems and clients' data safe.",
        "courses": [
            ("CompTIA Security+ study path", "CompTIA", "Widely recognised security foundation."),
            ("Introduction to Cybersecurity", "Cisco Networking Academy", "Threats and defences explained."),
            ("OWASP Top 10", "OWASP", "The most common web application risks."),
        ],
    },
    "Research & Policy": {
        "blurb": "Research and policy work behind our reports and publications.",
        "courses": [
            ("Research Methods", "Any accredited university MOOC", "Designing and evaluating research."),
            ("Policy Analysis Fundamentals", "Any accredited university MOOC", "Evidence-based policy writing."),
            ("Data Analysis with Excel", "Microsoft Learn", "Working with survey and statistical data."),
        ],
    },
    "Marketing & Communications": {
        "blurb": "Telling our story to clients, partners and the public.",
        "courses": [
            ("Fundamentals of Digital Marketing", "Google Digital Garage", "Channels, content and measurement."),
            ("Content Marketing Certification", "HubSpot Academy", "Planning and writing content that works."),
            ("Social Media Marketing Foundations", "Any reputable provider", "Running professional channels."),
        ],
    },
    "Operations & Administration": {
        "blurb": "Keeping the office, people and projects running smoothly.",
        "courses": [
            ("Project Management Foundations", "LinkedIn Learning / Coursera", "Planning, tracking and reporting."),
            ("Microsoft Excel Essentials", "Microsoft Learn", "Spreadsheets for everyday admin work."),
            ("Professional Business Communication", "Any reputable provider", "Clear emails and meetings."),
        ],
    },
}

# --- Positions (same 7 as before, plus Intern; all editable in Admin > Criteria) ---
DEFAULT_POSITIONS = [
    {"name": "Research Fellow", "min_years": 5, "min_education": "PhD",
     "required_keywords": "research, publication, policy, methodology",
     "preferred_keywords": "peer-reviewed, grant, quantitative, qualitative, think tank, policy brief",
     "w_exp": 0.30, "w_edu": 0.25, "w_req": 0.30, "w_pref": 0.15},
    {"name": "Policy Analyst", "min_years": 2, "min_education": "Master",
     "required_keywords": "policy, analysis, research, report",
     "preferred_keywords": "stakeholder, legislation, data, economics, governance, briefing",
     "w_exp": 0.30, "w_edu": 0.20, "w_req": 0.35, "w_pref": 0.15},
    {"name": "Research Assistant", "min_years": 0, "min_education": "Bachelor",
     "required_keywords": "research, data, assistant",
     "preferred_keywords": "spss, stata, python, survey, literature review",
     "w_exp": 0.15, "w_edu": 0.30, "w_req": 0.35, "w_pref": 0.20},
    {"name": "Data Analyst", "min_years": 2, "min_education": "Bachelor",
     "required_keywords": "data, analysis, statistics",
     "preferred_keywords": "python, r, sql, tableau, power bi, machine learning, visualisation, visualization",
     "w_exp": 0.25, "w_edu": 0.20, "w_req": 0.35, "w_pref": 0.20},
    {"name": "Communications Officer", "min_years": 2, "min_education": "Bachelor",
     "required_keywords": "communication, media, content, writing",
     "preferred_keywords": "social media, press, campaign, editorial, public relations, newsletter",
     "w_exp": 0.30, "w_edu": 0.20, "w_req": 0.35, "w_pref": 0.15},
    {"name": "Program Manager", "min_years": 4, "min_education": "Bachelor",
     "required_keywords": "project, management, budget, coordination",
     "preferred_keywords": "monitoring, evaluation, donor, stakeholder, leadership, logistics",
     "w_exp": 0.35, "w_edu": 0.15, "w_req": 0.35, "w_pref": 0.15},
    {"name": "Administrative Assistant", "min_years": 1, "min_education": "Diploma",
     "required_keywords": "administrative, office, scheduling",
     "preferred_keywords": "microsoft office, excel, records, procurement, customer service",
     "w_exp": 0.25, "w_edu": 0.15, "w_req": 0.40, "w_pref": 0.20},
    # Added for the intern intake - an assumption, edit it under Admin > Criteria.
    {"name": INTERN_POSITION, "min_years": 0, "min_education": "Diploma",
     "required_keywords": "project, learning, computer",
     "preferred_keywords": "python, javascript, html, excel, communication, volunteer, teamwork",
     "w_exp": 0.10, "w_edu": 0.30, "w_req": 0.35, "w_pref": 0.25},
]

# --- Chatbot FAQ (SAMPLE answers - review and edit in Admin > FAQ chatbot) --------
# {org} and {hr_email} are filled in when the answer is shown.
DEFAULT_FAQ = [
    ("How will I know my application was received?",
     "You will receive an email straight after you apply. If you do not hear from {org} within "
     f"{RESPONSE_WINDOW_BUSINESS_DAYS} business days of applying, please treat your application as unsuccessful.",
     "received, confirmation, application, hear, response, unsuccessful, feedback, 14 days, email after applying, confirmation email, got no confirmation"),
    ("How long does the hiring process take?",
     f"We aim to let shortlisted candidates know quickly. If you have not heard from us within "
     f"{RESPONSE_WINDOW_BUSINESS_DAYS} business days, your application was not successful on this occasion.",
     "process, timeline, how long, take, duration, wait, hear back, hear from, decision, soon, reply, successful, when will i know"),
    ("What happens if I am shortlisted?",
     f"You will get an email congratulating you and inviting you to an interview within the next "
     f"{INTERVIEW_WINDOW_BUSINESS_DAYS} business days. Interviews take place as a Google Meet video call.",
     "shortlisted, shortlist, interview, next, step, steps, invite, invited, selected, told, invitation, pass, passed, screening"),
    ("How do I prepare for the Google Meet interview?",
     "Join from a quiet place with a stable internet connection, and test your camera and microphone beforehand. "
     "Have your CV to hand, read the job description again, and prepare examples of your work.",
     "prepare, preparation, google meet, video, call, interview, camera, microphone, tips"),
    ("What documents will I need if I am offered the job?",
     "You will usually be asked for a copy of your ID, your qualifications, your bank details and contact details "
     "for references. HR will confirm the exact list in your offer email.",
     "documents, paperwork, id, certificates, qualifications, bank, references, offer, offered, get the job, give you"),
    ("What are the working hours?",
     "Your working hours and where you will work (on-site, hybrid or remote) are confirmed in your offer letter "
     "and contract. HR will walk you through them during onboarding.",
     "hours, working hours, schedule, time, start, finish, shifts"),
    ("Can I work remotely?",
     "Remote and hybrid arrangements depend on the role and department. They are confirmed in your offer letter, "
     "so please ask HR or your hiring manager.",
     "remote, hybrid, home, wfh, office, on-site, onsite, location"),
    ("How and when will I be paid?",
     "Your salary or stipend and pay date are set out in your offer letter and contract. "
     "Contact {hr_email} if you have a payroll question.",
     "salary, pay, paid, payment, payday, stipend, money, payroll, wage, pay interns, interns paid, interns get paid"),
    ("What equipment will I get?",
     "Your department will confirm the equipment and software you need for your role before you start.",
     "equipment, laptop, computer, tools, software, devices"),
    ("What is the first week like?",
     "You will be welcomed by HR, introduced to your team and supervisor, and given access to the systems you need. "
     "Your supervisor will explain what you will be working on.",
     "first week, onboarding, induction, start, starting, welcome, orientation, first day, day one, expect, when i start"),
    ("What is the probation period and how much leave do I get?",
     "Probation, leave and other benefits are set out in your employment contract. "
     "HR will explain them in detail when you join.",
     "probation, leave, holiday, vacation, benefits, contract, sick, how long is probation"),
    ("What departments can interns work in?",
     "Interns can be placed in: " + ", ".join(DEPARTMENTS) + ". Tell us your preferred department when you apply, "
     "and the team will place you where you can learn the most.",
     "intern, internship, interns, department, departments, placed, placement, where"),
    ("How will interns get updates and course recommendations?",
     "Once you are placed, you will receive a personal link by email. It shows your department, updates from the "
     "team under your name, and the courses recommended to help you grow in your role.",
     "intern, update, updates, courses, course, learn, learning, training, recommendations, grow, learning support, personal page, intern link, link"),
    ("Who can I contact with other questions?",
     "Please email the recruitment team at {hr_email}.",
     "contact, email, phone, hr, human resources, recruiter, recruitment, question, help, speak, talk, who do i email, email about"),
]


# --- Company information (company_info.json) and the FAQ entries built from it ------
def _load_company() -> dict:
    """about / services / location / hours / phone / email / website, from company_info.json. Empty = not shown."""
    import json
    keys = ("about", "services", "location", "hours", "phone", "email", "website")
    try:
        raw = json.loads((BASE_DIR / "company_info.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    return {k: str(raw.get(k, "") or "").strip() for k in keys}


COMPANY = _load_company()


def company_faq(company: dict | None = None) -> list[tuple[str, str, str]]:
    """(question, answer, keywords) for the questions about the company and how to join it. Entries whose
    information is blank in company_info.json are left out rather than guessed."""
    c = COMPANY if company is None else company
    site = f" ({c['website']})" if c.get("website") else ""
    roles = [p["name"] for p in DEFAULT_POSITIONS if p["name"] != INTERN_POSITION]
    out = [
        ("What positions are open?",
         "{org} recruits for these roles: " + ", ".join(roles) + f". We also take on {INTERN_POSITION.lower()}s. "
         "Choose your position on the application form; the recruitment team can tell you which are open right now.",
         "positions, position, jobs, job, vacancies, vacancy, hiring, open, roles, careers, recruiting, openings, what roles, what jobs"),
        ("How do I apply?",
         f"Use the application form on our careers page{site}: choose the position, fill in your details, upload your "
         f"CV (PDF, DOCX or TXT, up to {MAX_UPLOAD_MB} MB) or paste its text, tick the consent box and submit. "
         f"You will receive a confirmation email. For an internship choose {INTERN_POSITION} and your preferred department.",
         "apply, how to apply, submit, send cv, upload, application form, resume, file, file types, format, send my application, send application, application process, where do i send"),
    ]
    if c.get("about"):
        out.append(("What does {org} do?", c["about"],
                    "about, company, organisation, organization, who are you, what do you do, mission, tell me about"))
    if c.get("services"):
        out.append(("What services do you offer?", c["services"],
                    "services, service, products, product, offer, offerings, solutions, sell, build"))
    if c.get("location"):
        out.append(("Where is your office?", c["location"],
                    "where, address, located, location, office, directions, based, city, head office"))
    if c.get("hours"):
        out.append(("What are your opening hours?", c["hours"],
                    "opening hours, open, business hours, closed, weekend, when are you open, office hours"))
    contact = []
    if c.get("phone"):
        contact.append(f"Phone: {c['phone']}")
    if c.get("email"):
        contact.append(f"Email: {c['email']}")
    if c.get("website"):
        contact.append(f"Website: {c['website']}")
    if contact:
        out.append(("What are your contact details?", "You can reach {org} here. " + ". ".join(contact) + ".",
                    "phone, telephone, number, contact details, company email, website, reach you, call you"))
    return out


DEFAULT_FAQ.extend(company_faq())
