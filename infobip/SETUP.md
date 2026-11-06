# The chatbot on your website, on WhatsApp, and inside Infobip

> **Importing the FAQ and company information into an Infobip chatbot, and the Infobip website widget:** see `START_HERE.md`.

One bot, three doors. All of them answer from the same questions (**Admin > Chatbot**) and send a person's
"talk to a recruiter" request to **Admin > Requests** and, through Zapier, to the recruiter's email.

| Door | What the visitor uses | You need |
|---|---|---|
| **A. Website** | a chat button on any page | one line of HTML |
| **B. WhatsApp** | your WhatsApp number | an Infobip WhatsApp sender, a public https address for this portal |
| **C. Infobip Answers** | a chatbot you build in Infobip that calls this portal | the same, plus 10 minutes in Infobip |

Emails still go **only through Zapier**. Infobip is used only for WhatsApp chat.

---

## A. Put the chatbot on your website

Paste this line just before `</body>` on every page that should show the chat button (the exact line is also shown
under **Admin > Chatbot**):

```html
<script src="https://YOUR-PORTAL-ADDRESS/static/embed.js" async></script>
```

Options on that tag: `data-label="Ask us"`, `data-position="left"`, `data-color="#1D4ED8"`.

* Your portal must be reachable by visitors. If your website is `https://...`, the portal must be `https://...` too
  (browsers block http inside https).
* To stop other sites showing your chat, set `EMBED_ALLOWED_ORIGINS=https://www.yoursite.org` in `.env`.
* The chat window is the portal's `/chat-widget` page in a frame, so nothing on the host page can read it.

## B. WhatsApp through Infobip (recommended)

How it works: a person writes to your WhatsApp number -> Infobip forwards the message to the portal -> the portal
works out the answer -> the portal sends it back through Infobip. You do **not** need to build anything in Infobip
Answers for this.

1. **Make the portal reachable.** Infobip cannot reach `localhost`. Deploy it (see the main README, section 4) or,
   for a demo, use a tunnel such as `cloudflared` or `ngrok` and use the https address it prints.
2. **Create two secrets** and put the Infobip details in `.env`, then restart the portal:

   ```
   INFOBIP_WEBHOOK_SECRET=<long random text>      # python -c "import secrets; print(secrets.token_urlsafe(32))"
   INFOBIP_BASE_URL=xxxxx.api.infobip.com         # shown on your Infobip home page and API keys page
   INFOBIP_API_KEY=<an Infobip API key>
   INFOBIP_WHATSAPP_SENDER=27821234567            # your WhatsApp sender, digits only
   ```
3. **Tell Infobip where to send incoming WhatsApp messages.** In the Infobip web interface, open your WhatsApp
   sender and set its incoming-messages forwarding (also called inbound / MO forwarding) to:

   ```
   https://YOUR-PORTAL-ADDRESS/webhooks/infobip/whatsapp?secret=<INFOBIP_WEBHOOK_SECRET>
   ```
   The menu names differ between Infobip accounts and I could not check them in your account, so if you cannot find
   the setting, ask Infobip support for "forward incoming WhatsApp messages to a URL". The portal accepts the
   secret as `?secret=`, as an `X-Webhook-Secret` header, as `Authorization: Bearer <secret>`, or as the password
   of Basic authentication, so use whichever your Infobip screen offers.
4. **Test.** From your phone, send "hello" to your WhatsApp number. You should get the greeting and a numbered menu.
   Look at **Admin > Integrations > Activity log**: a green `infobip whatsapp_reply` row means Infobip accepted the
   reply. A red row shows Infobip's own error text (wrong key, wrong sender, no permission, ...).
5. **Without a phone:** `python infobip/chat_in_terminal.py` runs the same conversation in your terminal, and
   `python infobip/test_send.py 27821234567 "hello"` sends one real WhatsApp to check your Infobip settings.

What the person sees on WhatsApp: answers followed by a numbered list ("You can ask me: 1. ... 0. Talk to a
recruiter"). They type a number to pick a question, or 0 to reach a person. The bot then asks for their name and an
optional email, and saves the request with their WhatsApp number, so the recruiter can answer on WhatsApp.

Good to know:
* WhatsApp only allows free-text replies within 24 hours of the person's last message. The bot only ever replies,
  so this is always satisfied. Starting a chat yourself needs an approved template message (not included).
* Your Infobip plan, trial limits and WhatsApp message charges apply. Check them on your Infobip account.
* Infobip may send the same message twice; the portal answers each message id once.
* A number can receive at most 60 answers an hour (loop and abuse guard).

## C. A chatbot that lives inside Infobip Answers (the "import" route)

Infobip's own import takes a `.export` file made by Infobip's **Export** button. Infobip does not publish how that
file is written, so this project cannot generate one without guessing, and a wrong guess would fail to import.
Instead, build the small dialog below once (about 10 minutes). It is only a shell: all the answers stay in this
portal, so you never retype the FAQ in Infobip.

Use this route if you want the bot to be listed under **Answers > Chatbots** (for example to use Infobip's To Agent
hand-over, tags or reports). Use route B if you only want WhatsApp to work. **Do not switch both on for the same
WhatsApp number**, or the person gets two answers.

1. In `.env` set `BOT_API_KEY=<long random text>` and restart. The portal must be reachable on https.
2. In Infobip: **Answers > Chatbots > Create chatbot**, channel WhatsApp (or the channel you want).
3. In the chatbot's main dialog add these elements in order:

   | # | Element | Setting |
   |---|---|---|
   | 1 | **Save user response** | Save the person's message in a new text attribute `userText` |
   | 2 | **API** | Import this cURL (the element has an *Import from cURL* option): `infobip/answers_api_call.curl`. Replace the address and key. For `{{userId}}` pick the attribute that holds the person's phone number or session id, and `{{userText}}` is the attribute from step 1. Timeout 10 s. |
   | 3 | **API** (same element) | **Response** tab: save the JSON path `reply` into attribute `botReply` and `handoff` into `botHandoff` |
   | 4 | **Send message** | Text: `{{botReply}}` |
   | 5 | **To Dialog** | Go back to element 1, so the conversation continues |

   Infobip does not let an API element's *Request* tab use the raw "last received message", which is why step 1 saves
   it into your own attribute first. If the API call fails, set its fallback to a message such as "Sorry, I cannot
   answer right now" and a **To Agent** or **Close session** element.
4. Choose the **Sender**, run Infobip's built-in **Simulator**, then publish.
5. **Export** the chatbot (three dots > Export). That `.export` file is now your own importable copy: use
   **Import chatbot** to create it again in another Infobip account.

What the API returns, so you can map more fields if you like:

```json
{"ok": true, "reply": "text to show", "handoff": "none | asking | submitted", "matched": true, "escalation_id": null}
```
Errors: `401` wrong key, `503` `BOT_API_KEY` not set on the portal, `400` missing `user_id`, `429` too many messages.

If you export any small chatbot from your Infobip account and send me the `.export` file, a ready-made importable bot
can be generated from its real structure.

## Troubleshooting

| What you see | What to do |
|---|---|
| No reply on WhatsApp, nothing in the Activity log | Infobip is not reaching the portal. Check the forwarding URL, that the portal is public https, and the `?secret=` value. Test: `curl -X POST "https://YOUR-PORTAL/webhooks/infobip/whatsapp?secret=WRONG"` must answer 401, and with the right secret 400 (empty body). |
| Webhook answers `503` | `INFOBIP_WEBHOOK_SECRET` is empty in `.env`, or the portal was not restarted. |
| Activity log: `skipped: INFOBIP_BASE_URL, INFOBIP_API_KEY and INFOBIP_WHATSAPP_SENDER must all be set` | Fill all three in `.env` and restart. |
| Activity log: red `infobip whatsapp_reply` with an HTTP error | Read the text next to it: 401 = wrong API key or base URL; a sender error = `INFOBIP_WHATSAPP_SENDER` is not your registered number; a window error = the person has not written to you in the last 24 hours. |
| `SSLError` / `CERTIFICATE_VERIFY_FAILED` | Your network inspects HTTPS: `pip install truststore`, restart. |
| Two answers per message | Route B and route C are both on for this number. Turn one off. |
| Chat button missing on your website | Open the browser console (F12). `blocked` or mixed-content messages mean the portal is http while the site is https, or `EMBED_ALLOWED_ORIGINS` does not list your site. |

## What was and was not verified

* Verified here: the conversation logic, the webhook (secret, duplicates, errors), the API (key, rate limit), the
  website embed on a different origin in a real browser (desktop and phone width), and the database upgrade
  (117 automated tests).
* **Not** verified: a live Infobip account. The sandbox could not reach Infobip. The request to send a WhatsApp text
  (`POST /whatsapp/1/message/text`, header `Authorization: App <key>`) and the incoming-message format
  (`results[].from`, `messageId`, `message.type`, `message.text`) follow Infobip's published WhatsApp API as far as
  it could be read; the Infobip documentation pages for them could not be opened here, so please confirm the first
  real message with `infobip/test_send.py`. The Infobip menu names in step B3 and C are described, not checked.
