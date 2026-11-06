"""Rule-based FAQ chatbot (no external AI service, nothing leaves your server).

Each FAQ has a question, an answer and comma-separated keywords. A visitor's message is
matched to the FAQ with the best keyword/word overlap. Unmatched questions are logged so the
recruitment team can add answers for them (Admin > FAQ chatbot).
"""
from __future__ import annotations

import re

import config

_STOP = {"a", "an", "the", "is", "are", "was", "were", "be", "do", "does", "did", "i", "me", "my", "you", "your",
         "we", "our", "to", "of", "in", "on", "at", "for", "and", "or", "it", "this", "that", "can", "will",
         "would", "should", "what", "when", "where", "who", "how", "if", "get", "got", "have", "has", "about",
         "with", "am", "so", "there", "any", "much", "many", "please"}
_GREET = {"hi", "hello", "hey", "howzit", "sup", "good", "morning", "afternoon", "evening", "heita", "hallo", "yo"}
_THANKS = {"thanks", "thank", "thx", "cheers", "ta", "appreciate", "ok", "okay", "great", "cool"}

_HUMAN = re.compile(r"\b(human|real person|live agent|live person|representative|operator)\b|"
                    r"\b(speak|talk|chat|call)\s+(to|with)\s+(a\s+|an\s+|the\s+)?(person|someone|somebody|recruiter|agent|human)\b|"
                    r"\b(call|contact|phone)\s+me\b")
MIN_SCORE = 3
MAX_LEN = 300


def _stem(word: str) -> str:
    """Very light stemming so "remotely" matches "remote", "applying" matches "apply", "jobs" matches "job"."""
    if len(word) > 6 and word.endswith("ly"):
        return word[:-2]
    if len(word) > 5 and word.endswith("ing"):
        return word[:-3]
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def _words(text: str) -> list[str]:
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", (text or "").lower())]


def hr_contact() -> str:
    return config.RECRUITMENT_LEAD_EMAIL or "the recruitment team"


def render(answer: str) -> str:
    if not config.RECRUITMENT_LEAD_EMAIL:             # "email the team at the team" reads badly: drop the address
        answer = answer.replace(" at {hr_email}", "")
    return answer.replace("{org}", config.ORGANISATION_NAME).replace("{hr_email}", hr_contact())


def suggestions(faqs: list[dict], exclude_id: int | None = None, n: int = 5) -> list[str]:
    return [f["question"] for f in faqs if f["id"] != exclude_id][:n]


def reply(message: str, faqs: list[dict]) -> dict:
    """Return {"answer", "matched", "faq_id", "escalate" (offer the human hand-off), "suggestions"}."""
    text = (message or "").strip()[:MAX_LEN]
    all_words = _words(text)
    content = {w for w in all_words if w not in {_stem(s) for s in _STOP}}
    padded = " " + " ".join(all_words) + " "

    if all_words and set(all_words) <= {_stem(w) for w in _GREET}:
        return {"answer": f"Hello! I can answer questions about working at {config.ORGANISATION_NAME}. "
                          f"Pick a question below or type your own.",
                "matched": True, "faq_id": None, "escalate": False, "suggestions": suggestions(faqs)}
    if all_words and set(all_words) <= {_stem(w) for w in _THANKS} | {_stem(w) for w in _GREET}:
        return {"answer": "You're welcome! Is there anything else you would like to know?",
                "matched": True, "faq_id": None, "escalate": False, "suggestions": suggestions(faqs)}

    if _HUMAN.search(text.lower()):
        return {"answer": "Of course. I can pass your question to the recruitment team and a person will reply by "
                          "email. Please press \"Talk to a recruiter\" below.",
                "matched": True, "faq_id": None, "escalate": True, "suggestions": []}

    best, best_score = None, 0
    for faq in faqs:
        score = 0
        seen_phrases = set()                          # "job" and "jobs" are one keyword once stemmed: count it once
        for phrase in (p.strip() for p in faq["keywords"].split(",")):
            pw = _words(phrase)
            if not pw or tuple(pw) in seen_phrases:
                continue
            seen_phrases.add(tuple(pw))
            if f" {' '.join(pw)} " in padded:
                score += 4 if len(pw) > 1 else 3
        q_words = {w for w in _words(faq["question"]) if w not in {_stem(s) for s in _STOP}}
        score += len(content & q_words)
        if score > best_score:
            best, best_score = faq, score

    if best and best_score >= MIN_SCORE:
        return {"answer": render(best["answer"]), "matched": True, "faq_id": best["id"],
                "escalate": False, "suggestions": suggestions(faqs, exclude_id=best["id"])}
    return {"answer": "I'm not sure about that one yet. You can choose one of the questions below, or press "
                      "\"Talk to a recruiter\" and a person on the recruitment team will reply by email.",
            "matched": False, "faq_id": None, "escalate": True, "suggestions": suggestions(faqs)}
