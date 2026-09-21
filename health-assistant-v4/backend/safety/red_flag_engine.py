"""
Safety Engine — deterministic red-flag detection.
----------------------------------------------------
This module is intentionally independent of the AI/analysis pipeline. It
never calls, imports, or waits on `ai_provider.py`, and nothing in this file
can be softened by an LLM's output.

Pipeline position (see main.py):

    raw input
        -> run_safety_check()          <-- this module, pass 1 (early exit)
        -> adaptive questions
        -> symptom analysis / evidence / AI explanation
        -> run_safety_check() again    <-- this module, pass 2 (final validation)
        -> response assembled from whichever pass found a red flag

Because the *same* function is called before and after the AI step, and its
output always wins over whatever risk level the analysis stage computed, an
emergency flag can never be "explained away" by an LLM. See
`docs/SAFETY_ENGINE.md` for the non-exhaustiveness disclosure required
before this is trusted for anything beyond a hackathon demo.

Detection has two layers:
1. Single-phrase red flags (extends risk_assessment.RED_FLAGS with a larger,
   more systematically organized set, grouped by clinical category purely
   for readability/testability -- the categories are not used for scoring).
2. Combination rules: pairs/sets of phrases that are only dangerous
   *together* (e.g. "chest pain" alone is in the single-phrase list already,
   but some combinations are meaningful even when neither phrase alone would
   be, such as sudden severe headache + vision changes).

Both layers are plain substring checks over normalized text -- no ML, no
network call, nothing that can fail silently or be rate-limited. This
matches the "must run independently of the LLM" and "must work with zero
API keys" requirements.
"""

from dataclasses import dataclass, field

try:
    from nlp_extraction import NEGATION_WORDS
except ImportError:  # pragma: no cover - fallback if imported standalone
    NEGATION_WORDS = {
        "no", "not", "without", "never", "none", "denies", "denied",
        "isn't", "wasn't", "don't", "doesn't", "didn't", "haven't", "hasn't",
        "aren't", "can't", "won't", "couldn't", "shouldn't", "wouldn't",
    }

NEGATION_WINDOW = 4  # how many preceding words count as "right before this phrase"

# ---------------------------------------------------------------------------
# Phrase matching helper.
#
# A naive `phrase in text` substring check misses common natural phrasing
# where the words of a red-flag phrase appear in a different order or with
# a small word in between -- e.g. the phrase "face drooping" should also
# catch "face IS drooping" or "drooping on one side of my face", and
# "throat closing" should catch "throat IS closing". Missing these in a
# safety engine is worse than a rare false positive, so matching here is
# order-independent word-proximity: every word of the phrase must appear
# within a small window of the text, in any order.
#
# It's negation-aware for the same reason nlp_extraction.py is: "I do NOT
# have chest pain" must not raise an emergency flag. A match only counts if
# none of the NEGATION_WINDOW words immediately before it is a negation cue.
# This is a real safety trade-off, not a free improvement -- see
# docs/SAFETY_ENGINE.md for why single-phrase negation handling is not a
# substitute for clinical judgment (sarcasm, double negatives, and
# negation scoped over a whole sentence rather than one clause can all
# still slip past a window-based check).
# ---------------------------------------------------------------------------

def _phrase_match_start(text_words: list, phrase_words: list, slack: int = 3) -> int:
    """Returns the start index of the first window containing every word in
    phrase_words (any order), or -1 if no such window exists."""
    window_len = len(phrase_words) + slack
    phrase_set = set(phrase_words)
    for i in range(len(text_words)):
        window = set(text_words[i : i + window_len])
        if phrase_set <= window:
            return i
    return -1


def _phrase_in_text(normalized_text: str, phrase: str) -> bool:
    """True if `phrase` appears in `normalized_text` and is not negated."""
    text_words = normalized_text.split()
    phrase_words = phrase.split()
    slack = 3 if len(phrase_words) > 1 else 0
    idx = _phrase_match_start(text_words, phrase_words, slack=slack)
    if idx == -1:
        return False
    window_len = len(phrase_words) + slack
    # A negation cue counts whether it sits just before the matched window
    # ("I don't [have] chest pain") or inside it ("chest [pain isn't] there")
    # -- with a window this small (phrase length + slack), checking the
    # whole span plus a short lead-in is more reliable than assuming the
    # phrase words start exactly at `idx`. Phrase words themselves are
    # excluded from that check -- a couple of red-flag phrases (e.g.
    # "can't breathe") legitimately contain a word ("can't") that is *also*
    # a negation cue, and without this exclusion the phrase would negate
    # itself and never match.
    phrase_word_set = set(phrase_words)
    context = text_words[max(0, idx - NEGATION_WINDOW) : idx + window_len]
    if any(w in NEGATION_WORDS and w not in phrase_word_set for w in context):
        return False
    return True


# ---------------------------------------------------------------------------
# Layer 1: single-phrase red flags, grouped by category for readability only.
# ---------------------------------------------------------------------------

RED_FLAG_GROUPS = {
    "airway_breathing": {
        "can't breathe", "cannot breathe", "difficulty breathing",
        "not breathing", "blue lips", "choking", "gasping for air",
        "stridor",
        # Colloquial equivalents of "difficulty breathing" found missing
        # during the end-to-end eval.
        "trouble breathing", "trouble catching my breath",
        "struggling to breathe", "hard time breathing",
    },
    "cardiac": {
        "chest pain", "crushing chest pain", "chest pressure",
        "chest tightness",
        # "tight"/"tightness" are different literal words -- exact-word
        # phrase matching means "chest tightness" never matches someone who
        # says their chest "feels tight". Adding the adjective form directly
        # rather than building a stemming/equivalence layer, consistent with
        # how this file already lists both "facial drooping"/"face drooping".
        "chest tight", "chest feels tight",
    },
    "neurological": {
        "facial drooping", "face drooping", "slurred speech",
        "sudden confusion", "sudden numbness", "sudden weakness one side",
        "worst headache of my life", "thunderclap headache",
        "seizure", "unresponsive", "unconscious", "loss of consciousness",
    },
    "bleeding_trauma": {
        "severe bleeding", "uncontrolled bleeding", "bleeding heavily",
        "deep wound", "major trauma",
    },
    "allergic": {
        "throat closing", "swelling of the throat", "swelling of face and throat",
        "anaphylaxis",
    },
    "mental_health": {
        "suicidal", "suicide", "want to end my life", "self harm", "self-harm",
        # Colloquial phrasings that mean the same thing but don't contain the
        # literal words above -- found missing during the honest end-to-end
        # eval (eval_pipeline.py): "thoughts of ending my life" was not being
        # flagged at all because it shares no exact phrase with the list.
        "thoughts of ending my life", "thoughts of suicide", "want to die",
        "wanna die", "don't want to live", "no reason to live",
        "kill myself", "ending it all", "better off dead",
        "plan to kill myself", "have a plan to end my life",
    },
    "obstetric": {
        "heavy bleeding pregnant", "severe abdominal pain pregnant",
    },
    "pediatric_temperature": {
        "infant not responding", "baby limp", "seizure in infant",
    },
}

RED_FLAGS = {phrase for group in RED_FLAG_GROUPS.values() for phrase in group}


def _flag_category(phrase: str) -> str:
    for category, phrases in RED_FLAG_GROUPS.items():
        if phrase in phrases:
            return category
    return "other"


# ---------------------------------------------------------------------------
# Layer 2: combination rules. Each rule fires only if ALL of its `any_of`
# groups have at least one matching phrase present. Kept deliberately small
# and conservative -- false negatives here just mean layer 1 or the AI
# explanation still applies; false positives cost the user nothing worse
# than an unnecessary "seek care" nudge, so we lean toward catching more.
# ---------------------------------------------------------------------------

@dataclass
class CombinationRule:
    rule_id: str
    label: str
    # each element is a set of phrases; the rule fires if text contains at
    # least one phrase from EVERY set in this list
    any_of: list = field(default_factory=list)
    rationale: str = ""


COMBINATION_RULES = [
    CombinationRule(
        rule_id="cardiac_dyspnea",
        label="Possible cardiac emergency",
        any_of=[
            {"chest pain", "chest pressure", "chest tightness", "chest tight", "chest feels tight"},
            {"shortness of breath", "difficulty breathing", "cannot breathe", "can't breathe",
             "sweating", "trouble breathing", "trouble catching my breath",
             "struggling to breathe", "hard time breathing"},
        ],
        rationale="Chest pain/pressure combined with breathing difficulty or sweating is a "
                   "classic heart-attack symptom pattern.",
    ),
    CombinationRule(
        rule_id="stroke_fast",
        label="Possible stroke (FAST signs)",
        any_of=[
            {"facial drooping", "face drooping", "slurred speech", "sudden weakness one side",
             "sudden numbness", "sudden confusion"},
        ],
        rationale="Any single FAST sign (Face, Arms, Speech, Time) on its own already warrants "
                   "emergency care; grouped here as a named pattern for the explanation text.",
    ),
    CombinationRule(
        rule_id="thunderclap_headache_neuro",
        label="Possible neurological emergency",
        any_of=[
            {"worst headache of my life", "thunderclap headache", "sudden severe headache"},
            {"vision changes", "blurred vision", "double vision", "vomiting", "stiff neck",
             "confusion"},
        ],
        rationale="A sudden, severe ('worst of my life') headache combined with vision change, "
                   "vomiting, or neck stiffness needs urgent evaluation to rule out serious "
                   "neurological causes.",
    ),
    CombinationRule(
        rule_id="allergic_airway",
        label="Possible severe allergic reaction",
        any_of=[
            {"hives", "rash", "swelling"},
            {"throat closing", "swelling of the throat", "difficulty breathing",
             "cannot breathe", "can't breathe", "dizziness", "fainting"},
        ],
        rationale="Skin symptoms (hives/swelling) combined with airway or circulatory symptoms "
                   "is the pattern for anaphylaxis, which can progress rapidly.",
    ),
    CombinationRule(
        rule_id="high_fever_stiff_neck",
        label="Possible meningitis pattern",
        # V4 fix (from honest eval): fever + stiff neck is ALREADY the
        # classic meningitis warning-sign pair on its own -- requiring a
        # third symptom (confusion/photophobia/rash) on top of that missed
        # real cases where someone reports exactly those two things and
        # nothing else. Confusion/photophobia/rash still matter clinically
        # but shouldn't gate escalation when the core pair is present.
        any_of=[
            {"high fever", "fever"},
            {"stiff neck", "neck stiffness"},
        ],
        rationale="Fever combined with neck stiffness is the classic meningitis warning-sign "
                   "pair and needs urgent evaluation on its own.",
    ),
    CombinationRule(
        rule_id="syncope_altered_mental_status",
        label="Possible serious cause of fainting",
        any_of=[
            {"fainted", "fainting", "passed out", "loss of consciousness"},
            {"confusion", "confused", "disoriented", "couldn't remember"},
        ],
        rationale="Fainting combined with confusion or disorientation on waking can indicate a "
                   "cardiac, neurological, or other serious cause rather than simple fainting, "
                   "and needs urgent evaluation.",
    ),
]


@dataclass
class SafetyResult:
    is_emergency: bool
    matched_phrases: list
    matched_combinations: list  # list of dicts: {rule_id, label, rationale}

    def to_dict(self) -> dict:
        return {
            "is_emergency": self.is_emergency,
            "matched_phrases": self.matched_phrases,
            "matched_combinations": self.matched_combinations,
        }


def detect_red_flags(normalized_text: str) -> list:
    """Layer 1 only -- kept as a standalone function so risk_assessment.py's
    existing call shape keeps working unmodified."""
    return sorted(phrase for phrase in RED_FLAGS if _phrase_in_text(normalized_text, phrase))


def detect_combinations(normalized_text: str) -> list:
    """Layer 2. Returns matched combination rules as plain dicts."""
    matches = []
    for rule in COMBINATION_RULES:
        if all(
            any(_phrase_in_text(normalized_text, phrase) for phrase in group)
            for group in rule.any_of
        ):
            matches.append({
                "rule_id": rule.rule_id,
                "label": rule.label,
                "rationale": rule.rationale,
            })
    return matches


def run_safety_check(normalized_text: str) -> SafetyResult:
    """
    The single entry point the rest of the app should call. Combines both
    detection layers into one deterministic yes/no plus the evidence for it.

    normalized_text should already be lowercased/punctuation-stripped (see
    nlp_extraction.normalize) so phrase matching is reliable regardless of
    how the user capitalized or punctuated their input.
    """
    phrases = detect_red_flags(normalized_text)
    combos = detect_combinations(normalized_text)
    return SafetyResult(
        is_emergency=bool(phrases or combos),
        matched_phrases=phrases,
        matched_combinations=combos,
    )


def combined_normalized_text(*fragments: str) -> str:
    """
    Helper for the "final validation" pass: the safety engine needs to see
    the ORIGINAL free-text input plus every follow-up-question answer
    concatenated together, since a red flag might only surface in an answer
    ("Did you have any chest pain?" -> "yes, and it's crushing") rather than
    the initial description. Import nlp_extraction.normalize at the call
    site to normalize each fragment before passing it here, or pass
    already-normalized fragments -- this just joins them.
    """
    return " ".join(f for f in fragments if f)


def matched_categories(result: SafetyResult) -> set:
    """
    Which RED_FLAG_GROUPS categories fired, purely for routing (e.g. "this
    looks like a mental-health crisis, surface the crisis helpline
    alongside 112/108" vs "this looks medical, surface general emergency
    numbers"). Not used for scoring -- is_emergency is already decided.
    """
    return {_flag_category(p) for p in result.matched_phrases}
