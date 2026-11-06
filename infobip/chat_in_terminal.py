"""Chat with the bot in this window - no server, Infobip or WhatsApp needed. Same code path as WhatsApp.

    python infobip/chat_in_terminal.py            (type 0 to talk to a recruiter, Ctrl+C to stop)

Uses the database named in .env (DATABASE_PATH), so a "talk to a recruiter" request you finish here really appears
under Admin > Requests. Use a throw-away DATABASE_PATH if you only want to experiment.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot  # noqa: E402
import database as db  # noqa: E402


def main() -> None:
    db.init_db()
    conn = db.get_conn()
    user = "27820000000"                       # pretend WhatsApp number
    print("Type a message. Ctrl+C to stop.\n")
    try:
        first = True
        while True:
            text = input("you > ") if not first else "hello"
            if first:
                print("you > hello")
                first = False
            print("\nbot >", bot.handle(conn, "whatsapp", user, text)["reply"], "\n")
    except (KeyboardInterrupt, EOFError):
        print()


if __name__ == "__main__":
    main()
