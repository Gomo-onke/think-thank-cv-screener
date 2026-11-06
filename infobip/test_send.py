"""Check your Infobip WhatsApp settings by sending ONE text message.

    python infobip/test_send.py 27821234567 "Hello from the portal"

The number must be in international format without + (digits only). WhatsApp only allows a free-text message
inside 24 hours after that person last wrote to your WhatsApp number, so first send "hi" to your number from the
phone you are testing with. Prints Infobip's answer, so a wrong key or sender is easy to see.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import whatsapp  # noqa: E402


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    if not whatsapp.sending_configured():
        sys.exit("Set INFOBIP_BASE_URL, INFOBIP_API_KEY and INFOBIP_WHATSAPP_SENDER in .env first.")
    res = whatsapp.send_text("".join(ch for ch in sys.argv[1] if ch.isdigit()), " ".join(sys.argv[2:]))
    print("OK - Infobip accepted the message" if res["success"] else "FAILED", "\n", res["status_code"], res["detail"])


if __name__ == "__main__":
    main()
