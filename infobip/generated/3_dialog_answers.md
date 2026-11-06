# Dialog answers for the Think Tank Software Solutions chatbot

Infobip cannot import answers from a file, so create one **dialog per row** below, give it the **intent** shown (Dialog > Intent settings), and add one **Text** element containing the answer. Copy the text exactly.

20 dialogs. Do the first ones first - the chatbot already works as soon as a few dialogs exist.

## 1. Welcome
**Intent:** `Welcome`

```
Hello! I'm the Think Tank Software Solutions assistant. I can answer questions about working here, our hiring process, internships and the company. What would you like to know?
```

## 2. Goodbye
**Intent:** `Goodbye`

```
Thank you for chatting with Think Tank Software Solutions. Good luck, and goodbye!
```

## 3. Thanks
**Intent:** `Thanks`

```
You're welcome! Is there anything else you would like to know?
```

## 4. Human Agent
**Intent:** `Human_Agent`

```
Of course. Please email the recruitment team and a person will reply to you.
```

## 5. Application Received
**Intent:** `Application_Received`

```
You will receive an email straight after you apply. If you do not hear from Think Tank Software Solutions within 14 business days of applying, please treat your application as unsuccessful.
```

## 6. Hiring Timeline
**Intent:** `Hiring_Timeline`

```
We aim to let shortlisted candidates know quickly. If you have not heard from us within 14 business days, your application was not successful on this occasion.
```

## 7. Shortlisted Next Steps
**Intent:** `Shortlisted_Next_Steps`

```
You will get an email congratulating you and inviting you to an interview within the next 5 business days. Interviews take place as a Google Meet video call.
```

## 8. Interview Preparation
**Intent:** `Interview_Preparation`

```
Join from a quiet place with a stable internet connection, and test your camera and microphone beforehand. Have your CV to hand, read the job description again, and prepare examples of your work.
```

## 9. Offer Documents
**Intent:** `Offer_Documents`

```
You will usually be asked for a copy of your ID, your qualifications, your bank details and contact details for references. HR will confirm the exact list in your offer email.
```

## 10. Working Hours
**Intent:** `Working_Hours`

```
Your working hours and where you will work (on-site, hybrid or remote) are confirmed in your offer letter and contract. HR will walk you through them during onboarding.
```

## 11. Remote Work
**Intent:** `Remote_Work`

```
Remote and hybrid arrangements depend on the role and department. They are confirmed in your offer letter, so please ask HR or your hiring manager.
```

## 12. Salary And Pay
**Intent:** `Salary_And_Pay`

```
Your salary or stipend and pay date are set out in your offer letter and contract. Contact the recruitment team if you have a payroll question.
```

## 13. Equipment
**Intent:** `Equipment`

```
Your department will confirm the equipment and software you need for your role before you start.
```

## 14. First Week
**Intent:** `First_Week`

```
You will be welcomed by HR, introduced to your team and supervisor, and given access to the systems you need. Your supervisor will explain what you will be working on.
```

## 15. Probation And Leave
**Intent:** `Probation_And_Leave`

```
Probation, leave and other benefits are set out in your employment contract. HR will explain them in detail when you join.
```

## 16. Intern Departments
**Intent:** `Intern_Departments`

```
Interns can be placed in: Software Development, Data & Analytics, UX / UI Design, Quality Assurance, Cloud & DevOps, Cybersecurity, Research & Policy, Marketing & Communications, Operations & Administration. Tell us your preferred department when you apply, and the team will place you where you can learn the most.
```

## 17. Intern Updates Courses
**Intent:** `Intern_Updates_Courses`

```
Once you are placed, you will receive a personal link by email. It shows your department, updates from the team under your name, and the courses recommended to help you grow in your role.
```

## 18. Contact Hr
**Intent:** `Contact_Hr`

```
Please email the recruitment team.
```

## 19. Open Positions
**Intent:** `Open_Positions`

```
Think Tank Software Solutions recruits for these roles: Research Fellow, Policy Analyst, Research Assistant, Data Analyst, Communications Officer, Program Manager, Administrative Assistant. We also take on interns. Choose your position on the application form; the recruitment team can tell you which are open right now.
```

## 20. How To Apply
**Intent:** `How_To_Apply`

```
Use the application form on our careers page: choose the position, fill in your details, upload your CV (PDF, DOCX or TXT, up to 10 MB) or paste its text, tick the consent box and submit. You will receive a confirmation email. For an internship choose Intern and your preferred department.
```

## Fallback (the "Default" / fallback action for messages the bot does not understand)

```
I'm not sure about that one yet. You can ask me about applying, the hiring process, working at Think Tank Software Solutions, internships or the company. To reach a person, email the recruitment team.
```
