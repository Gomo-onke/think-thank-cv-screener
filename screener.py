"""Pure scoring logic (no DB, no network). Identical in Build 1 and Build 2.

Rubric
------
score = 100 * (w_exp*experience + w_edu*education + w_req*required + w_pref*preferred) / sum(w)

  experience = min(1, years_found / min_years)          (1.0 when min_years is 0)
  education  = min(1, found_rank / min_rank)            (PhD=4 .. Diploma=1)
  required   = share of must-have keywords found
  preferred  = share of nice-to-have keywords found

Decision
--------
  hard requirements met  = years_found >= min_years AND education rank >= min rank
                           (AND every must-have keyword, if the
                           `require_all_required_keywords` setting is "1")
  Pass          -> hard met and score >= pass_threshold (default 70)
  Needs Review  -> hard met and review_threshold <= score < pass_threshold (60-70)
  Reject        -> a hard requirement is missing, or score < review_threshold
"""
from __future__ import annotations

import re

from config import DEFAULT_SETTINGS, EDU_LABEL, EDU_RANK

# Highest rank wins, so check from PhD downwards. Word boundaries stop "ba"
# matching inside "database", "msc" inside other words, etc.
_EDU_PATTERNS = [
    (4, re.compile(r"\bph\.?\s?d\b|\bdoctorate\b|\bdoctoral\b")),
    (3, re.compile(r"\bmasters?\b|\bmba\b|\bm\.?\s?sc\b")),
    (2, re.compile(r"\bbachelors?\b|\bb\.?\s?sc\b|\bba\b|\bb\.?\s?eng\b")),
    (1, re.compile(r"\bdiploma\b")),
]

_YEARS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)")


def parse_keywords(value: str | list[str]) -> list[str]:
    """'a, b ,c' -> ['a','b','c'] (lower-cased, de-duplicated, order kept)."""
    items = value if isinstance(value, list) else str(value or "").replace("\n", ",").split(",")
    seen, out = set(), []
    for k in items:
        k = k.strip().lower()
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def edu_rank_from_label(label: str) -> int:
    return EDU_RANK.get((label or "").strip().lower(), 0)


def detect_education(text: str) -> int:
    t = (text or "").lower()
    for rank, pattern in _EDU_PATTERNS:
        if pattern.search(t):
            return rank
    return 0


def detect_years(text: str) -> float:
    vals = [float(m) for m in _YEARS_RE.findall((text or "").lower())]
    return max(vals) if vals else 0.0


def keyword_found(keyword: str, text_lower: str) -> bool:
    """Case-insensitive substring match.

    Very short keywords (<= 2 chars, e.g. "r" for the R language) would match
    nearly every CV as a raw substring, so those must stand alone as a token.
    """
    if len(keyword) <= 2:
        return re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text_lower) is not None
    return keyword in text_lower


def screen_cv(cv_text: str, position: dict, settings: dict | None = None) -> dict:
    """Score a CV against one position dict (a row from the `positions` table)."""
    s = {**DEFAULT_SETTINGS, **(settings or {})}
    pass_t = float(s["pass_threshold"])
    review_t = float(s["review_threshold"])
    need_all_kw = str(s["require_all_required_keywords"]) == "1"

    text = (cv_text or "").lower()
    min_years = float(position["min_years"] or 0)
    min_rank = edu_rank_from_label(position["min_education"])
    required = parse_keywords(position["required_keywords"])
    preferred = parse_keywords(position["preferred_keywords"])

    years = detect_years(text)
    edu_rank = detect_education(text)
    req_hits = [k for k in required if keyword_found(k, text)]
    pref_hits = [k for k in preferred if keyword_found(k, text)]

    exp_score = 1.0 if min_years <= 0 else min(1.0, years / min_years)
    edu_score = 1.0 if min_rank <= 0 else min(1.0, edu_rank / min_rank)
    req_score = len(req_hits) / len(required) if required else 1.0
    pref_score = len(pref_hits) / len(preferred) if preferred else 1.0

    weights = {k: float(position[k] or 0) for k in ("w_exp", "w_edu", "w_req", "w_pref")}
    total_w = sum(weights.values()) or 1.0
    raw = (weights["w_exp"] * exp_score + weights["w_edu"] * edu_score
           + weights["w_req"] * req_score + weights["w_pref"] * pref_score) / total_w
    score = round(100 * raw, 1)

    # Hard requirements
    failures = []
    if years < min_years:
        failures.append(f"experience {years:g} yrs is below the {min_years:g} yrs required")
    if edu_rank < min_rank:
        found = EDU_LABEL[edu_rank]
        failures.append(f"education ({found}) is below the minimum ({EDU_LABEL[min_rank]})")
    req_missing = [k for k in required if k not in req_hits]
    if need_all_kw and req_missing:
        failures.append("missing must-have keywords: " + ", ".join(req_missing))
    hard_ok = not failures

    if hard_ok and score >= pass_t:
        status = "Pass"
    elif hard_ok and score >= review_t:
        status = "Needs Review"
    else:
        status = "Reject"

    notes = [f"Score {score}/100"]
    if failures:
        notes.append("Hard requirement(s) not met: " + "; ".join(failures))
    elif status != "Pass":
        notes.append(f"Hard requirements met but score is below {pass_t:g}")
    if req_missing and not (need_all_kw and req_missing):
        notes.append("Missing required keywords: " + ", ".join(req_missing))

    return {
        "position": position["name"],
        "score": score,
        "status": status,
        "hard_requirements_met": hard_ok,
        "hard_failures": failures,
        "notes": ". ".join(notes),
        "years_found": years,
        "min_years": min_years,
        "education_found": EDU_LABEL[edu_rank],
        "education_found_rank": edu_rank,
        "education_required": EDU_LABEL[min_rank],
        "education_required_rank": min_rank,
        "sub_scores": {
            "experience": round(exp_score, 3),
            "education": round(edu_score, 3),
            "required_keywords": round(req_score, 3),
            "preferred_keywords": round(pref_score, 3),
        },
        "weights": weights,
        "weighted_points": {
            "experience": round(100 * weights["w_exp"] * exp_score / total_w, 1),
            "education": round(100 * weights["w_edu"] * edu_score / total_w, 1),
            "required_keywords": round(100 * weights["w_req"] * req_score / total_w, 1),
            "preferred_keywords": round(100 * weights["w_pref"] * pref_score / total_w, 1),
        },
        "required_found": req_hits,
        "required_missing": req_missing,
        "preferred_found": pref_hits,
        "preferred_missing": [k for k in preferred if k not in pref_hits],
        "thresholds": {"pass": pass_t, "review": review_t, "require_all_required_keywords": need_all_kw},
    }
