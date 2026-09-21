"""
Risk Assessment Module
------------------------
Corresponds to the "RISK ASSESSMENT" stage: classifies overall risk as
low / moderate / urgent, combining two independent signals:

1. The severity of whatever conditions AI Symptom Analysis matched
2. Direct red-flag phrase detection -- catches emergency language even when
   the knowledge-base overlap alone wouldn't have produced a strong match
   (e.g. a novel phrasing of a stroke symptom)

Red-flag detection is deliberately kept separate from the analysis stage so
it can never be "out-voted" by a low-confidence match -- a single red flag is
enough to escalate risk to urgent regardless of what else was found.
"""

# V4: red-flag phrase detection now lives in backend/safety/red_flag_engine.py
# (a larger, negation-aware, combination-rule-capable set used by the new
# adaptive-questions pipeline) so there's a single source of truth instead of
# two red-flag lists silently drifting apart. RED_FLAGS is re-exported here
# so any code that did `from risk_assessment import RED_FLAGS` keeps working.
from safety.red_flag_engine import RED_FLAGS, detect_red_flags as _detect_red_flags

RISK_ORDER = {"low": 0, "moderate": 1, "urgent": 2}
SEVERITY_TO_RISK = {"mild": "low", "moderate": "moderate", "emergency": "urgent"}

# A single weak symptom overlap (e.g. "nausea" alone matching a dozen
# conditions) shouldn't be enough to escalate risk on its own -- require a
# minimum confidence before a match's severity counts toward risk. Red flags
# bypass this entirely since they're an explicit, direct signal.
MIN_CONFIDENCE_FOR_ESCALATION = 0.25

# A higher-severity match should only escalate risk if it's a genuinely
# COMPETITIVE explanation, not just any match that happens to clear the
# floor above while trailing far behind a much stronger, milder match.
#
# Without this, a mild-severity condition can never appear as the "driving"
# match in the reasoning text even when it's clearly the best explanation --
# severity escalation only fires when RISK_ORDER strictly increases, and
# "mild" never increases past "low". So the instant ANY moderate-severity
# condition clears MIN_CONFIDENCE_FOR_ESCALATION, it permanently wins the
# narration slot, regardless of how much better a mild match's confidence
# is. Concretely: "I have a runny nose and mild cough" matches Common Cold
# and Influenza at IDENTICAL confidence (0.475 each, since their symptom
# lists are nearly the same length and both share these two symptoms) -- a
# perfectly reasonable tie to escalate on. But if Influenza had instead
# trailed well behind Common Cold (e.g. 0.30 vs 0.65, because the person
# also mentioned cold-specific symptoms like "sneezing" and "congestion"
# that aren't in Influenza's profile), the old logic would STILL let that
# weak, non-competitive Influenza match drive the reasoning text and name
# -- telling someone with a clear cold that "Influenza" is what was found,
# which erodes trust in the tool over repeated use ("why does it keep
# talking about flu when I said I have a cold").
COMPETITIVE_MARGIN = 0.15


def detect_red_flags(normalized_text: str) -> list:
    return _detect_red_flags(normalized_text)


def assess_risk(matches: list, normalized_text: str) -> dict:
    """
    matches: list of ConditionMatch from symptom_analysis (already sorted by
        confidence, descending)
    normalized_text: output of nlp_extraction.normalize()

    Returns {"risk_level": "low"|"moderate"|"urgent", "red_flags": [...], "reasoning": str}
    """
    red_flags = detect_red_flags(normalized_text)
    top_confidence = matches[0].confidence if matches else 0.0

    risk_level = "low"
    driving_match = None

    for m in matches:
        if m.confidence < MIN_CONFIDENCE_FOR_ESCALATION:
            continue
        if m.confidence < top_confidence - COMPETITIVE_MARGIN:
            # Clears the floor, but is trailing too far behind the best
            # match to be a fair, representative reason to escalate risk or
            # to name in the explanation -- skip it for escalation purposes
            # (it still appears in "Possible Explanations" at its own
            # confidence; this only affects risk_level/reasoning).
            continue
        candidate = SEVERITY_TO_RISK.get(m.severity, "low")
        if RISK_ORDER[candidate] > RISK_ORDER[risk_level]:
            risk_level = candidate
            driving_match = m
        elif RISK_ORDER[candidate] == RISK_ORDER[risk_level] and driving_match is not None:
            # Same resulting risk level -- prefer the more confident match
            # as the one actually named in the reasoning text.
            if m.confidence > driving_match.confidence:
                driving_match = m

    if red_flags and RISK_ORDER["urgent"] > RISK_ORDER[risk_level]:
        risk_level = "urgent"

    reasoning_parts = []
    if red_flags:
        reasoning_parts.append(f"red-flag terms detected: {', '.join(red_flags)}")
    if driving_match:
        reasoning_parts.append(
            f"'{driving_match.name}' matched with {driving_match.severity} severity "
            f"(confidence {driving_match.confidence})"
        )
    reasoning = "; ".join(reasoning_parts) or "no significant risk indicators found"

    return {
        "risk_level": risk_level,
        "red_flags": red_flags,
        "reasoning": reasoning,
        # V4: expose which specific match actually drove the risk_level
        # escalation (not necessarily the highest-CONFIDENCE match overall --
        # e.g. a low-confidence "Influenza" match can drive risk to
        # "moderate" even while a higher-confidence "Common Cold" match sits
        # at the top of the list). triage.py needs the real driving match,
        # not just matches[0], or it reasons about the wrong condition.
        "driving_match_id": driving_match.condition_id if driving_match else None,
    }
