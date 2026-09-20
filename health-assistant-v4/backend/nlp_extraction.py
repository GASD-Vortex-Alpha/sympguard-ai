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


def _is_negated(normalized_text: str, phrase: str, window: int = 3) -> bool:
    """Context understanding: look a few words back from the phrase for negation cues."""
    idx = normalized_text.find(phrase)
    if idx == -1:
        return False
    preceding = normalized_text[:idx].split()[-window:]
    return any(w in NEGATION_WORDS for w in preceding)


def extract_symptoms(free_text: str) -> list:
    """Extract known symptom phrases from raw text, filtering out negated mentions."""
    normalized = normalize(free_text)
    found = []
    for phrase in VOCAB:
        if _fuzzy_contains(normalized, phrase) and not _is_negated(normalized, phrase):
            found.append(phrase)
    return found
