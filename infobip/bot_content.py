"""What the chatbot knows, written once.

Each intent has:
    name      the intent name in Infobip (letters, digits and underscores only)
    faq       the portal FAQ question that holds its answer (None = a fixed answer below, or a company answer that
              only exists when company_info.json has the information)
    phrases   training phrases: different ways a person might ask it (no semicolons - the import file uses them)
    words     optional "important words": (word, [synonyms])

Edit freely, then run:  python infobip/make_infobip_files.py
The generator checks the file (no duplicate phrases, enough phrases per intent, no semicolons) before writing.
"""

INTENTS = [
    # ------------------------------------------------------------------ conversation basics
    dict(name="Welcome", faq=None, phrases=[
        "Hi", "Hello", "Hey", "Good morning", "Good afternoon", "Good evening", "Howzit", "Hello there", "Hi there",
        "Hey there", "Start", "Hallo"], words=[]),
    dict(name="Goodbye", faq=None, phrases=[
        "Bye", "Goodbye", "See you later", "That is all", "I am done", "No thanks that is all", "Bye bye",
        "Talk to you later", "Have a good day"], words=[]),
    dict(name="Thanks", faq=None, phrases=[
        "Thanks", "Thank you", "Thanks a lot", "Many thanks", "Cheers", "Great thanks", "Awesome thank you",
        "Thank you so much", "Thanks for your help"], words=[]),
    dict(name="Human_Agent", faq=None, phrases=[
        "I want to talk to a person", "Can I speak to a human", "Connect me to an agent", "I need a real person",
        "Speak to a recruiter", "Talk to someone", "Can someone call me", "I want to speak to the recruitment team",
        "Live agent please", "Get me a human"], words=[("agent", ["human", "person", "recruiter", "representative"])]),

    # ------------------------------------------------------------------ the hiring process
    dict(name="Application_Received", faq="How will I know my application was received?", phrases=[
        "How will I know my application was received", "Did you get my application", "Did my application go through",
        "Will I get a confirmation email", "I applied but got no confirmation", "How do I know you received my CV",
        "Was my application submitted successfully", "Do I get an email after applying", "Where is my confirmation",
        "Has my application been received"], words=[("confirmation", ["received", "acknowledgement", "receipt"])]),
    dict(name="Hiring_Timeline", faq="How long does the hiring process take?", phrases=[
        "How long does the hiring process take", "How long until I hear back", "How long will it take to get a response",
        "When will I hear from you", "What is the timeline for hiring", "How many days until a decision",
        "How long do I have to wait for feedback", "What if I do not hear back", "How soon will you reply",
        "When will I know if I was successful"], words=[("timeline", ["duration", "wait", "how long", "days"])]),
    dict(name="Shortlisted_Next_Steps", faq="What happens if I am shortlisted?", phrases=[
        "What happens if I am shortlisted", "What is the next step after shortlisting", "I was shortlisted what now",
        "How will you invite me to an interview", "What happens after I pass the screening",
        "How will I be told about an interview", "When will the interview happen after shortlisting",
        "What do you do after you shortlist someone"], words=[("shortlisted", ["shortlist", "selected", "passed"])]),
    dict(name="Interview_Preparation", faq="How do I prepare for the Google Meet interview?", phrases=[
        "How do I prepare for the interview", "Tips for the Google Meet interview", "How does the video interview work",
        "What should I do before the interview", "How should I prepare for the Google Meet call",
        "What do I need for the online interview", "Any interview tips", "Is the interview online",
        "Do I need a camera for the interview"], words=[("interview", ["meeting", "google meet", "video call"])]),
    dict(name="Offer_Documents", faq="What documents will I need if I am offered the job?", phrases=[
        "What documents will I need if I am offered the job", "Which documents do I need to bring",
        "What paperwork do I need for onboarding", "Do I need to send my ID",
        "What do I need to give you if I get the job", "Which certificates do I have to provide",
        "What is needed after an offer", "Do you need references"], words=[("documents", ["paperwork", "certificates", "id"])]),

    # ------------------------------------------------------------------ working here
    dict(name="Working_Hours", faq="What are the working hours?", phrases=[
        "What are the working hours", "What time do I start work", "What time do you finish work",
        "How many hours do I work per week", "Do you work shifts", "What is the work schedule",
        "When does the working day start", "What hours will I work"], words=[("hours", ["schedule", "shifts", "times"])]),
    dict(name="Remote_Work", faq="Can I work remotely?", phrases=[
        "Can I work remotely", "Is remote work possible", "Do you offer hybrid work", "Can I work from home",
        "Is the job on site or remote", "Do I have to work in the office", "Is work from home allowed",
        "Do you have hybrid arrangements"], words=[("remote", ["hybrid", "home", "wfh", "on-site"])]),
    dict(name="Salary_And_Pay", faq="How and when will I be paid?", phrases=[
        "How and when will I be paid", "What is the salary", "When is payday", "How much do you pay",
        "What is the stipend for interns", "When do I get my salary", "Do you pay interns", "How is payment done",
        "What is the pay date"], words=[("salary", ["pay", "stipend", "wage", "payment", "payroll"])]),
    dict(name="Equipment", faq="What equipment will I get?", phrases=[
        "What equipment will I get", "Will I get a laptop", "Do you provide a computer", "Which software will I use",
        "What tools will be provided", "Do I need to bring my own laptop", "What devices do I receive",
        "Will you supply equipment"], words=[("laptop", ["computer", "devices", "tools", "equipment"])]),
    dict(name="First_Week", faq="What is the first week like?", phrases=[
        "What is the first week like", "What happens on my first day", "How does onboarding work",
        "What is the induction like", "Who will I meet in my first week", "What will I do when I start",
        "Tell me about orientation", "What should I expect on day one"], words=[("onboarding", ["induction", "orientation", "first day"])]),
    dict(name="Probation_And_Leave", faq="What is the probation period and how much leave do I get?", phrases=[
        "What is the probation period", "How much leave do I get", "How many days of annual leave",
        "Do you offer sick leave", "What benefits do employees get", "How long is probation", "What holiday do I get",
        "Tell me about leave and benefits"], words=[("leave", ["holiday", "vacation", "benefits", "sick"])]),

    # ------------------------------------------------------------------ internships
    dict(name="Intern_Departments", faq="What departments can interns work in?", phrases=[
        "What departments can interns work in", "Which departments do you have for interns",
        "Where can I be placed as an intern", "Which teams take interns", "What internship areas are available",
        "Can I choose my department as an intern", "List the intern departments", "Do you have internships in design"],
         words=[("internship", ["intern", "interns", "placement"])]),
    dict(name="Intern_Updates_Courses", faq="How will interns get updates and course recommendations?", phrases=[
        "How will interns get updates", "What courses are recommended for interns",
        "How do interns get course recommendations", "Where do I see my intern updates",
        "What learning support do interns get", "How will I know which courses to take",
        "Do interns get a personal page", "What is the intern link"], words=[("courses", ["course", "training", "learning"])]),
    dict(name="Contact_Hr", faq="Who can I contact with other questions?", phrases=[
        "Who can I contact with other questions", "How can I contact HR", "What is the recruitment email",
        "Who do I email about my application", "Where can I send a question", "How do I reach the recruitment team",
        "What is the HR contact", "I have another question who do I ask"], words=[("hr", ["human resources", "recruitment", "recruiter"])]),

    # ------------------------------------------------------------------ the company and joining it
    dict(name="Open_Positions", faq="What positions are open?", phrases=[
        "What positions are open", "What jobs do you have", "Which vacancies are available", "Are you hiring",
        "What roles can I apply for", "List your open positions", "Do you have any vacancies",
        "What careers are available", "Which jobs are you recruiting for"],
         words=[("vacancies", ["jobs", "positions", "openings", "roles", "careers"])]),
    dict(name="How_To_Apply", faq="How do I apply?", phrases=[
        "How do I apply", "How can I submit my CV", "Where do I send my application", "How do I apply for a job",
        "What is the application process", "Can I upload my CV", "How do I submit an application",
        "Where is the application form", "What file types can I upload for my CV", "How do I apply for an internship"],
         words=[("apply", ["application", "submit", "upload", "cv", "resume"])]),
    dict(name="About_Company", faq="What does {org} do?", phrases=[
        "What does your company do", "Tell me about the company", "Who are you", "What is {org}",
        "What kind of company is this", "Tell me about your organisation", "What is your mission",
        "Who runs this company", "Tell me more about {org}"], words=[]),
    dict(name="Services_Offered", faq="What services do you offer?", phrases=[
        "What services do you offer", "What do you sell", "What products do you have",
        "What can your company do for me", "Do you build software", "Which services are available",
        "What solutions do you provide", "What are your offerings"], words=[("services", ["products", "solutions", "offerings"])]),
    dict(name="Company_Location", faq="Where is your office?", phrases=[
        "Where are you located", "Where is your office", "What is your address", "Where is the company based",
        "How do I get to your office", "Which city are you in", "Can I visit your office", "Where is your head office"],
         words=[("address", ["office", "located", "directions", "location"])]),
    dict(name="Opening_Hours", faq="What are your opening hours?", phrases=[
        "What are your opening hours", "When are you open", "What time does your office open",
        "Which days are you open", "When can I phone you", "What are your business hours",
        "Are you open on weekends", "What time do you close"], words=[("open", ["opening", "closed", "business hours"])]),
    dict(name="Contact_Details", faq="What are your contact details?", phrases=[
        "What is your phone number", "What is your company email", "How can I contact the company",
        "Do you have a contact number", "What is your website", "Where can I reach you",
        "What is your telephone number", "Give me your contact details"], words=[("phone", ["telephone", "number", "call", "contact details"])]),
]

# Fixed answers for the conversation basics (the others come from the portal FAQ).
FIXED_ANSWERS = {
    "Welcome": "Hello! I'm the {org} assistant. I can answer questions about working here, our hiring process, "
               "internships and the company. What would you like to know?",
    "Goodbye": "Thank you for chatting with {org}. Good luck, and goodbye!",
    "Thanks": "You're welcome! Is there anything else you would like to know?",
    "Human_Agent": "Of course. Please email the recruitment team at {hr_email} and a person will reply to you.",
}

FALLBACK_ANSWER = ("I'm not sure about that one yet. You can ask me about applying, the hiring process, working at {org}, "
                   "internships or the company. To reach a person, email the recruitment team at {hr_email}.")
