"""
Pre-detection of onset timing and severity from the user's initial free-text
description.

Why this exists: the two generic_intro_questions (questions/question_bank.json)
always ask "When did this start?" and "How severe is it?" -- useful defaults,
but redundant and mildly annoying if the person already said "since this
morning" or "it's really severe" in their very first message. This module
looks for that, and if found, main.py pre-fills the answer so
question_engine.next_batch() skips asking it again.

Deliberately conservative: only returns a value when the phrasing is
reasonably unambiguous. Returning nothing just means the question gets asked
normally -- a missed detection costs one extra tap, so there's no pressure to
be clever/aggressive here at the risk of mis-detecting.
"""

import re

# Ordered so more specific / longer patterns are checked before shorter,
# more general ones that could otherwise match a substring of them
# (e.g. "2 weeks ago" must be checked before a bare "\d+ days? ago").
_ONSET_PATTERNS = [
    (r"\bjust (started|began|now)\b|\ba few minutes? ago\b|\bwithin the last hour\b", "Within the last hour"),
    (r"\b(\d+)\s*(hour|hr)s?\s*ago\b", "Within the last hour"),  # handled specially below for >1hr, see _refine_hours
    (r"\btoday\b|\bthis morning\b|\bthis afternoon\b|\bthis evening\b|\bearlier today\b|\btonight\b", "Today"),
    (r"\bmore than (a |1 )?(two|2) weeks?\b|\ba month ago\b|\bfor (weeks|months)\b|\bover a month\b|\bseveral weeks\b",
     "More than 2 weeks ago"),
    (r"\b(\d+)\s*weeks?\s*ago\b", None),  # resolved numerically below
    (r"\bfor\s*(\d+)\s*weeks?\b", None),  # resolved numerically below
    (r"\byesterday\b|\bsince yesterday\b|\ba couple of days ago\b|\ba few days ago\b", "1-3 days ago"),
    (r"\b(\d+)\s*days?\s*ago\b", None),  # resolved numerically below
    (r"\bfor\s*(\d+)\s*days?\b|\bsince\s*(\d+)\s*days?\b", None),  # resolved numerically below
    (r"\blast week\b|\ba week ago\b|\bfor a week\b", "More than 3 days ago"),
]


def _resolve_numeric(text: str):
    """Handles '<N> days/weeks ago' and 'for <N> days/weeks' with the actual
    number bucketed into the right range, since a fixed phrase list can't
    cover every N. Also tolerates filler words ("for the past 2 days")."""
    m = re.search(r"\b(\d+)\s*days?\s*ago\b", text)
    if not m:
        m = re.search(r"\b(?:for|since)(?:\s+the)?(?:\s+past)?(?:\s+about|\s+around|\s+roughly)?\s+(\d+)\s*days?\b", text)
    if m:
        n = int(m.group(1))
        if n <= 3:
            return "1-3 days ago"
        return "More than 3 days ago"

    m = re.search(r"\b(\d+)\s*weeks?\s*ago\b", text)
    if not m:
        m = re.search(r"\bfor(?:\s+the)?(?:\s+past)?(?:\s+about|\s+around|\s+roughly)?\s+(\d+)\s*weeks?\b", text)
    if m:
        return "More than 2 weeks ago"

    if re.search(r"\bfor(?:\s+the)?(?:\s+past)?\s+(a\s+)?months?\b|\ba month ago\b", text):
        return "More than 2 weeks ago"

    m = re.search(r"\b(\d+)\s*(hour|hr)s?\s*ago\b", text)
    if m:
        n = int(m.group(1))
        return "Within the last hour" if n <= 1 else "Today"
    if re.search(r"\ban? (hour|hr)s?\s*ago\b", text):
        return "Within the last hour"

    return None


def detect_onset(raw_text: str) -> str:
    """Returns one of the onset_timing choice options, or None if the text
    doesn't clearly state when symptoms started."""
    text = raw_text.lower()

    numeric = _resolve_numeric(text)
    if numeric:
        return numeric

    for pattern, label in _ONSET_PATTERNS:
        if label is None:
            continue  # numeric ones already handled above
        if re.search(pattern, text):
            return label

    return None


_SEVERITY_SEVERE = re.compile(
    r"\bsevere\b|\bexcruciating\b|\bunbearable\b|\bintense\b|\bextreme(ly)?\b|"
    r"\breally bad\b|\bvery bad\b|\bworst\b|\bcan'?t (function|move|bear it)\b|\bagoniz(ing|e)\b"
)
_SEVERITY_MILD = re.compile(
    r"\bmild(ly)?\b|\bslight(ly)?\b|\ba little\b|\bbarely notic(e|eable)\b|\bnot (that |too )?bad\b|\bminor\b"
)
_SEVERITY_MODERATE = re.compile(r"\bmoderate(ly)?\b|\bnoticeable\b|\bmanageable\b")


def detect_severity(raw_text: str) -> str:
    """Returns one of the overall_severity choice options, or None."""
    text = raw_text.lower()
    # Check severe/mild before moderate -- "not that bad" etc. are more
    # specific/definitive than a bare mention of "moderate".
    if _SEVERITY_SEVERE.search(text):
        return "Severe - hard to ignore or function"
    if _SEVERITY_MILD.search(text):
        return "Mild - barely noticeable"
    if _SEVERITY_MODERATE.search(text):
        return "Moderate - noticeable, manageable"
    return None


def detect_intro_answers(raw_text: str) -> dict:
    """Convenience wrapper -- returns {question_id: answer} for whichever of
    onset_timing / overall_severity were confidently detected, ready to
    pre-fill into a session's `answered` dict."""
    answers = {}
    onset = detect_onset(raw_text)
    if onset:
        answers["onset_timing"] = onset
    severity = detect_severity(raw_text)
    if severity:
        answers["overall_severity"] = severity
    return answers
