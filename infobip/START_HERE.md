# Import the chatbot into Infobip and connect it to your website

You asked for one file to import. Here is what Infobip actually allows, so you do not lose time:

| What | Can Infobip import it from a file? | What this project gives you |
|---|---|---|
| **Intents** (the ways people ask each question) | **Yes.** `.csv`, semicolon separated, no header (documented by Infobip) | `generated/1_intents_import.csv` and `generated/2_important_words_import.csv` |
| **Answers and dialogs** | Only through Infobip's own `.export` file, whose layout Infobip does not publish | `generated/3_dialog_answers.md`: every answer, ready to paste |
| A whole chatbot | Only a `.export` file made by Infobip's *Export* button | Not possible to generate without guessing. Send me an export of any small bot and I can build a matching one |

So the import is two parts: **import the intents (one click), then paste the answers into dialogs.**
Infobip's own steps for the CSV are on its [Intents page](https://www.infobip.com/docs/answers/ai-chatbots/intents).

---

## Step 1. Put your company's real information in (5 minutes)

The bot knows the hiring process and the open positions from this portal. It does **not** know your company's
address, hours, phone, services or what you do, and it will not make them up. Open `company_info.json` in Notepad
and fill in what is true:

```json
{
  "about": "One to three sentences about what the company does.",
  "services": "What you offer.",
  "location": "Street, city.",
  "hours": "Mon-Fri 08:00-17:00.",
  "phone": "021 000 0000",
  "email": "info@yourcompany.org",
  "website": "https://www.yourcompany.org"
}
```
Anything you leave empty is simply left out.

## Step 2. Generate the files

In PowerShell, in the project folder (with the virtual environment active):

```powershell
python infobip/make_infobip_files.py --hr-email recruitment@yourcompany.org
```
This writes the three files into `infobip/generated/`. It checks them first (no phrase used by two intents, enough
phrases per intent, no semicolons). The same command with `--sync-portal --refresh-keywords` also adds the new
company answers to your portal's existing chatbot, so the website chat and WhatsApp know the same things.

The files in the zip were made **without** company information and without a recruitment email, so the company
questions (about, services, location, hours, contact) are not in them yet. Run the command again after Step 1.

## Step 3. Create the chatbot in Infobip and import the intents

1. In Infobip open **Answers > Chatbots > Create chatbot**. Give it a name, choose the **channel** (see Step 5),
   language English. Choose the **AI chatbot** type, the one that has an **Intents** tab (a rule-based bot uses
   Keywords instead).
2. Open the **Intents** tab > **Import**. First click **Download example** and check that your file looks the same
   (semicolons, no header). Choose `1_intents_import.csv` > **Import**.
3. Optional: import `2_important_words_import.csv` the same way.
4. Open `3_dialog_answers.md`. For each answer: **Add dialog**, name it like the heading, set the dialog's
   **Intent** to the intent named under the heading, add one **Text** element and paste the answer.
   Start with Welcome, Open_Positions, How_To_Apply, Hiring_Timeline and Human_Agent. The bot works as soon as a few
   dialogs exist.
5. Set the fallback (the answer for things the bot does not understand) to the **Fallback** text at the end of the file.
6. Use Infobip's **Simulator**, then activate the chatbot.
7. Use the three dots > **Export** once it works. That `.export` is your own importable copy.

A person who asks for a human gets the answer "email the recruitment team". If your Infobip plan includes
Conversations you can use the **To Agent** element there instead.

Changing something later: edit `infobip/bot_content.py` (phrases) or `company_info.json` and run Step 2 again.
Re-importing a CSV may add the same phrases twice, so delete the old intent's phrases first.

## Step 4. Check it before you rely on it

* Ask the Simulator the questions in your own words, not only the training phrases.
* The files were checked for format only. Infobip's own language engine was not available here, so how well it
  recognises questions is for you to see in the Simulator.
* As a rough guide to how clearly the questions differ, this portal's simple keyword bot recognised 131 of 137
  training phrases, but only 14 of 20 fresh questions I wrote afterwards. Add more phrases to any intent that
  misses, in `bot_content.py`.

## Step 5. Connect it to your website

**Option A: Infobip Live Chat widget** (the Infobip bot on your site)

1. In Infobip: **Channels and Numbers > Live Chat > Create widget > Installation & Security**.
2. Copy the snippet shown there and paste it inside the `<head>` of your site's main HTML file, then save and
   publish the site. Use https. Only one page should carry the snippet if visitors can see several.
3. Make the chatbot answer on that widget: create the chatbot with the **Live Chat** channel (it is one of the
   channels Answers supports) and select your widget as the sender if Infobip offers it.

Things I could not confirm: Infobip's pages that I could read do not show the click path that attaches an Answers
chatbot to a Live Chat widget, so if step 3 is not obvious on your screen, ask Infobip support: "attach Answers
chatbot X to Live Chat widget Y". Live Chat is an add-on to Infobip's Conversations product, so it may need to be
switched on for your account first.

**Option B: this portal's own chat button** (works today, no Infobip needed, same answers)

Paste this just before `</body>` on your pages (replace the address with your portal's public https address):

```html
<script src="https://YOUR-PORTAL-ADDRESS/static/embed.js" async></script>
```
`infobip/website_example.html` shows it in a page you can open locally. This is the same bot you edit under
**Admin > Chatbot**, and the only thing it needs is that the portal is online. It is the quickest way to get the
chat onto your site.

**Option C: WhatsApp** is in `SETUP.md` (section B), also through Infobip.

Pick one answer path per channel: do not run the Infobip bot and the portal bot on the same WhatsApp number or the
same widget, or visitors get two replies.
