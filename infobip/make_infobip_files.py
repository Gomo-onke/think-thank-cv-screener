"""Build the files for an Infobip Answers chatbot from the portal's FAQ and company_info.json.

    python infobip/make_infobip_files.py                      write the files into infobip/generated/
    python infobip/make_infobip_files.py --hr-email hr@x.org  use this recruitment email in the answers
    python infobip/make_infobip_files.py --check              also test the training phrases against the portal bot
    python infobip/make_infobip_files.py --sync-portal        add missing company answers to your existing database
        (add --refresh-keywords to also update the matching keywords of the standard questions)

Files written:
    1_intents_import.csv          IMPORT this in Answers > your chatbot > Intents > Import (training phrases)
    2_important_words_import.csv  optional second import (important words and synonyms)
    3_dialog_answers.md           the answer to paste into each dialog (Infobip cannot import answers from a file)

The two CSV files follow Infobip's documented intent import format: .csv, semicolon separated, no header row,
no empty rows, one line per "Training_Phrase;Intent" or "Important_Word;Intent;Synonym1,Synonym2".
"""
import argparse
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import chatbot  # noqa: E402
import config  # noqa: E402
from bot_content import FALLBACK_ANSWER, FIXED_ANSWERS, INTENTS  # noqa: E402

OUT = os.path.join(HERE, "generated")
MIN_PHRASES = 8


def fill(text: str) -> str:
    return text.replace("{org}", config.ORGANISATION_NAME)


def validate() -> list[str]:
    problems, seen = [], {}
    for it in INTENTS:
        name = it["name"]
        if not name.replace("_", "").isalnum():
            problems.append(f"{name}: intent names may only use letters, digits and underscores")
        if len(it["phrases"]) < MIN_PHRASES:
            problems.append(f"{name}: only {len(it['phrases'])} training phrases (need at least {MIN_PHRASES})")
        for ph in it["phrases"]:
            key = fill(ph).strip().lower().rstrip("?.!")
            if ";" in ph or "\n" in ph:
                problems.append(f"{name}: phrase contains ';' or a line break: {ph!r}")
            if key in seen and seen[key] != name:
                problems.append(f"phrase used by two intents ({seen[key]} and {name}): {ph!r}")
            seen[key] = name
        for word, syns in it["words"]:
            if ";" in word or any(";" in s or "," in s for s in syns):
                problems.append(f"{name}: important word or synonym contains ';' or ',': {word!r}")
    names = [i["name"] for i in INTENTS]
    problems += [f"intent name used twice: {n}" for n, c in Counter(names).items() if c > 1]
    return problems


def answers() -> tuple[dict, list[str]]:
    """{intent: answer text} for every intent that has an answer, and the names left out for lack of information."""
    by_question = {q: a for q, a, _k in config.DEFAULT_FAQ}
    got, missing = {}, []
    for it in INTENTS:
        if it["name"] in FIXED_ANSWERS:
            got[it["name"]] = chatbot.render(FIXED_ANSWERS[it["name"]])
        elif it["faq"] in by_question:
            got[it["name"]] = chatbot.render(by_question[it["faq"]])
        else:
            missing.append(it["name"])
    return got, missing


def write_files(got: dict) -> None:
    os.makedirs(OUT, exist_ok=True)
    phrase_lines, word_lines = [], []
    for it in INTENTS:
        if it["name"] not in got:
            continue
        phrase_lines += [f"{fill(p)};{it['name']}" for p in it["phrases"]]
        word_lines += [f"{w};{it['name']};{','.join(s)}" for w, s in it["words"]]
    with open(os.path.join(OUT, "1_intents_import.csv"), "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(phrase_lines) + "\n")
    with open(os.path.join(OUT, "2_important_words_import.csv"), "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(word_lines) + "\n")

    md = [f"# Dialog answers for the {config.ORGANISATION_NAME} chatbot", "",
          "Infobip cannot import answers from a file, so create one **dialog per row** below, give it the **intent** shown "
          "(Dialog > Intent settings), and add one **Text** element containing the answer. Copy the text exactly.", "",
          f"{len(got)} dialogs. Do the first ones first - the chatbot already works as soon as a few dialogs exist.", ""]
    for i, it in enumerate((x for x in INTENTS if x["name"] in got), start=1):
        md += [f"## {i}. {it['name'].replace('_', ' ')}", f"**Intent:** `{it['name']}`", "", "```", got[it["name"]], "```", ""]
    md += ["## Fallback (the \"Default\" / fallback action for messages the bot does not understand)", "", "```",
           chatbot.render(FALLBACK_ANSWER), "```", ""]
    with open(os.path.join(OUT, "3_dialog_answers.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))


def check_against_portal(got: dict) -> None:
    """Run every training phrase through the portal's own FAQ matcher (a rough test of how clearly the questions
    differ; Infobip's own language engine is a different system)."""
    faqs = [{"id": i, "question": q, "answer": a, "keywords": k} for i, (q, a, k) in enumerate(config.DEFAULT_FAQ, 1)]
    by_q = {f["question"]: f["id"] for f in faqs}
    total = right = 0
    print("\nPortal matcher on the training phrases (intents that have a portal FAQ):")
    for it in INTENTS:
        if it["name"] not in got or it["faq"] not in by_q:
            continue
        misses = []
        for p in it["phrases"]:
            r = chatbot.reply(fill(p), faqs)
            total += 1
            if r["faq_id"] == by_q[it["faq"]]:
                right += 1
            else:
                misses.append(p)
        print(f"  {it['name']:<24} {len(it['phrases']) - len(misses)}/{len(it['phrases'])}" +
              (f"   missed: {misses}" if misses else ""))
    print(f"  TOTAL {right}/{total}")


def sync_portal(refresh_keywords: bool = False) -> None:
    """Add answers missing from the portal database. With refresh_keywords, also replace the keywords of the standard
    questions with the current defaults (your own answers are never touched)."""
    import database as db
    db.init_db()
    conn = db.get_conn()
    existing = {f["question"]: f for f in db.list_faq(conn)}
    order = max([f["sort_order"] for f in existing.values()] or [0])
    added = refreshed = 0
    for q, a, k in config.DEFAULT_FAQ:
        if q not in existing:
            order += 1
            db.save_faq(conn, None, q, a, k, order)
            added += 1
        elif refresh_keywords and existing[q]["keywords"] != k:
            f = existing[q]
            db.save_faq(conn, f["id"], q, f["answer"], k, f["sort_order"])
            refreshed += 1
    conn.close()
    print(f"Portal database: {added} answer(s) added, {refreshed} keyword list(s) refreshed, "
          f"{len(existing)} already there.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hr-email", default="", help="recruitment email shown in answers (default: RECRUITMENT_LEAD_EMAIL)")
    ap.add_argument("--check", action="store_true", help="test the phrases against the portal's FAQ matcher")
    ap.add_argument("--sync-portal", action="store_true", help="add missing answers to the portal database")
    ap.add_argument("--refresh-keywords", action="store_true",
                    help="with --sync-portal: also update the matching keywords of the standard questions")
    args = ap.parse_args()
    if args.hr_email:
        config.RECRUITMENT_LEAD_EMAIL = args.hr_email
    problems = validate()
    if problems:
        sys.exit("Fix these first:\n  " + "\n  ".join(problems))
    got, missing = answers()
    write_files(got)
    phrases = sum(len(i["phrases"]) for i in INTENTS if i["name"] in got)
    print(f"Wrote {len(got)} intents, {phrases} training phrases to {OUT}")
    if missing:
        print("Left out because company_info.json has no information for them yet: " + ", ".join(missing))
    if not config.RECRUITMENT_LEAD_EMAIL:
        print("Note: no recruitment email set, so answers say 'the recruitment team' (use --hr-email you@company.org).")
    if args.check:
        check_against_portal(got)
    if args.sync_portal:
        sync_portal(args.refresh_keywords)


if __name__ == "__main__":
    main()
