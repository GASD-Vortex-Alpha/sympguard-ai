"""
NLP & Symptom Extraction Module
--------------------------------
Corresponds to the "NLP & SYMPTOM EXTRACTION" stage in the architecture
diagram: takes raw user text and extracts structured symptom mentions.

Includes basic context understanding via negation detection -- "no fever" or
"denies chest pain" should NOT be extracted as the symptom, since including it
would corrupt everything downstream (analysis, risk assessment).
"""

import json
import re
from difflib import SequenceMatcher
from pathlib import Path

KB_PATH = Path(__file__).parent / "knowledge_base.json"

NEGATION_WORDS = {
    "no", "not", "without", "never", "none", "denies", "denied",
    # V4 fix: normalize() used to strip apostrophes before this set was ever
    # checked, so "isn't"/"wasn't" (and every other contraction) silently
    # never matched anything -- "I don't have a fever" extracted "fever" as
    # a present symptom. normalize() now keeps apostrophes, so the literal
    # contractions below are checked as-typed.
    "isn't", "wasn't", "don't", "doesn't", "didn't", "haven't", "hasn't",
    "aren't", "can't", "won't", "couldn't", "shouldn't", "wouldn't",
}


def _load_vocab() -> list:
    with open(KB_PATH, "r", encoding="utf-8") as f:
        kb = json.load(f)["conditions"]
    # Longest phrases first so "chest pain" matches before bare "pain"
    return sorted({s.lower() for c in kb for s in c["symptoms"]}, key=len, reverse=True)


VOCAB = _load_vocab()


def normalize(text: str) -> str:
    text = text.lower().strip()
    # V4 fix: keep apostrophes so contractions ("isn't", "don't") survive as
    # a single token -- they used to get split into e.g. "isn t", which
    # meant NEGATION_WORDS could never match them (see NEGATION_WORDS above).
    text = re.sub(r"[^\w\s']", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _fuzzy_contains(haystack: str, needle: str, threshold: float = 0.88) -> bool:
    """
    Substring match, or fuzzy sliding-window match for typo tolerance.

    The fuzzy path requires both a high similarity ratio AND a small absolute
    length difference between the window and the needle. Without the length
    gate, short common words can accidentally score high similarity against
    an unrelated symptom word (e.g. "eating" vs "sweating" scores 0.857 on
    ratio alone -- close enough to slip past a pure-ratio threshold, but
    they're different words, not a typo of each other). The gate keeps fuzzy
    matching doing its actual job (catching real typos like "hedache" for
    "headache") without also catching real-but-different words.
    """
    if needle in haystack:
        return True
    words = haystack.split()
    n = len(needle.split())
    for i in range(len(words) - n + 1):
        window = " ".join(words[i : i + n])
        if abs(len(window) - len(needle)) > 2:
            continue
        if SequenceMatcher(None, window, needle).ratio() >= threshold:
            return True
    return False


def _phrase_match_start(text_words: list, phrase_words: list, slack: int = 1) -> int:
    """Word-index of the first window containing every word in phrase_words
    (any order), or -1. See safety/red_flag_engine.py -- same technique,
    used here for the same reason: natural phrasing reorders or inserts a
    word into a multi-word symptom phrase ("leg swelling one side" vs. "my
    leg is swollen on one side"), and a strict substring/same-length-fuzzy
    check (_fuzzy_contains above) misses that entirely. A real gap found
    this way during V4 development: a Bell's Palsy / DVT description using
    natural phrasing extracted zero relevant symptoms even though the words
    were all there, just reordered -- see V4_CHANGELOG.md."""
    if len(phrase_words) < 2:
        return -1  # single words are already handled by the substring check
    window_len = len(phrase_words) + slack
    phrase_set = set(phrase_words)
    for i in range(len(text_words)):
        window = set(text_words[i : i + window_len])
        if phrase_set <= window:
            return i
    return -1


def _is_negated(normalized_text: str, phrase: str, window: int = 4) -> bool:
    """Context understanding: look a few words back from the phrase for
    negation cues. Works whether the phrase was found as an exact substring
    or only via proximity matching (see _phrase_match_start)."""
    text_words = normalized_text.split()
    phrase_words = phrase.split()

    idx = normalized_text.find(phrase)
    if idx != -1:
        word_idx = len(normalized_text[:idx].split())
        slack = 0
    else:
        word_idx = _phrase_match_start(text_words, phrase_words)
        if word_idx == -1:
            return False
        slack = 2

    window_len = len(phrase_words) + slack
    phrase_word_set = set(phrase_words)
    context = text_words[max(0, word_idx - window) : word_idx + window_len]
    # Exclude the phrase's own words from the negation check -- some phrases
    # legitimately contain a word that is ALSO a negation cue (e.g. "can't
    # breathe" contains "can't"), and without this exclusion such a phrase
    # would negate itself and never match (found and fixed in the safety
    # engine during V4 development; applied here for the same reason).
    return any(w in NEGATION_WORDS and w not in phrase_word_set for w in context)


def extract_symptoms(free_text: str) -> list:
    """Extract known symptom phrases from raw text, filtering out negated mentions."""
    normalized = normalize(free_text)
    words = normalized.split()
    found = []
    for phrase in VOCAB:
        matched = _fuzzy_contains(normalized, phrase) or _phrase_match_start(words, phrase.split()) != -1
        if matched and not _is_negated(normalized, phrase):
            found.append(phrase)
    return found
