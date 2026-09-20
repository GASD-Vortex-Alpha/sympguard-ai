"""
Triage Engine
---------------
Maps the existing 3-level risk_assessment output (low/moderate/urgent) plus
the top matched condition's severity into the 4 categories the brief asks
for. Deterministic, rule-based, explainable -- no AI involved, and nothing
downstream can downgrade an EMERGENCY result (main.py enforces this by
computing triage AFTER the final safety validation pass and never letting
the AI-generated explanation text influence which category is chosen).
"""

from dataclasses import dataclass

EMERGENCY = "EMERGENCY"
URGENT_MEDICAL_EVALUATION = "URGENT_MEDICAL_EVALUATION"
ROUTINE_MEDICAL_CONSULTATION = "ROUTINE_MEDICAL_CONSULTATION"
SELF_CARE_MONITORING = "SELF_CARE_MONITORING"

LABELS = {
    EMERGENCY: "Emergency",
    URGENT_MEDICAL_EVALUATION: "Urgent Medical Evaluation",
    ROUTINE_MEDICAL_CONSULTATION: "Routine Medical Consultation",
    SELF_CARE_MONITORING: "Self-Care / Monitoring",
}

# A moderate-risk match above this confidence is treated as needing prompt
# (same-day/next-day) evaluation rather than a routine, non-urgent visit.
# Kept as a single named constant rather than a magic number so the
# threshold is easy to find, discuss, and adjust in one place.
#
# Chosen empirically against symptom_analysis.py's confidence formula
# (0.7*coverage + 0.3*precision): a vague 2-symptom overlap like "cough" +
# "runny nose" against Influenza's 8-symptom profile already scores ~0.475
# purely from the precision term, even though that presentation is not
# actually specific to flu. A fuller, more specific picture (e.g. 3+
# overlapping symptoms distinctive of one condition, like a UTI's "burning
# urination" + "frequent urination" + "pelvic pain") scores ~0.65+. 0.55 was
# picked as the line between those two, not from any clinical validation --
# see knowledge_base.json's _meta disclosure.
URGENT_EVALUATION_CONFIDENCE_THRESHOLD = 0.55


@dataclass
class TriageResult:
    category: str
    label: str
    reasoning: str

    def to_dict(self) -> dict:
        return {"category": self.category, "label": self.label, "reasoning": self.reasoning}


def classify(
    risk_level: str,
    red_flags: list,
    matches: list,
    safety_is_emergency: bool = False,
    driving_match_id: str = None,
) -> TriageResult:
    """
    risk_level: "low" | "moderate" | "urgent" (from risk_assessment.assess_risk)
    red_flags: list from the same call
    matches: list of ConditionMatch, already sorted by confidence desc
    driving_match_id: risk_assessment.assess_risk()'s "driving_match_id" --
        the condition that actually caused risk_level to escalate. This is
        NOT always matches[0]: a low-confidence "Influenza" match can drive
        risk to "moderate" while a higher-confidence "Common Cold" match
        (mild severity) sits at the top of the match list. Reasoning about
        matches[0] instead of the real driving match would describe the
        wrong condition and the wrong severity.
    safety_is_emergency: result of the independent safety-engine check (see
        safety/red_flag_engine.py) -- if True, this ALWAYS wins, regardless
        of what risk_level/matches say. This is the enforcement point for
        "AI must not downgrade an emergency safety result": nothing upstream
        of this parameter can talk this function out of EMERGENCY.
    """
    if safety_is_emergency or risk_level == "urgent" or red_flags:
        return TriageResult(
            category=EMERGENCY,
            label=LABELS[EMERGENCY],
            reasoning="An independent safety check found emergency indicators. This overrides "
                      "everything else in the assessment.",
        )

    by_id = {m.condition_id: m for m in matches}
    driving = by_id.get(driving_match_id) if driving_match_id else None
    top = matches[0] if matches else None

    if risk_level == "moderate":
        # driving should always be set when risk_level == "moderate" (see
        # risk_assessment.assess_risk), but fall back to top defensively
        # rather than crashing if that invariant ever changes.
        reference = driving or top
        if reference and reference.severity == "emergency":
            # Shouldn't normally happen (severity=emergency should already
            # have produced risk_level="urgent"), but if it ever does, don't
            # let a "moderate" label undersell it.
            return TriageResult(
                category=EMERGENCY,
                label=LABELS[EMERGENCY],
                reasoning=f"'{reference.name}' is a condition the knowledge base marks as emergency-severity.",
            )
        if reference and reference.confidence >= URGENT_EVALUATION_CONFIDENCE_THRESHOLD:
            return TriageResult(
                category=URGENT_MEDICAL_EVALUATION,
                label=LABELS[URGENT_MEDICAL_EVALUATION],
                reasoning=f"'{reference.name}' matched with {reference.severity} severity and "
                          f"confidence {reference.confidence} -- worth same-day or next-day "
                          f"medical attention.",
            )
        if reference:
            return TriageResult(
                category=ROUTINE_MEDICAL_CONSULTATION,
                label=LABELS[ROUTINE_MEDICAL_CONSULTATION],
                reasoning=f"'{reference.name}' matched with {reference.severity} severity, but at "
                          f"low enough confidence ({reference.confidence}) that this looks like a "
                          f"routine, non-urgent consultation rather than same-day care.",
            )
        return TriageResult(
            category=ROUTINE_MEDICAL_CONSULTATION,
            label=LABELS[ROUTINE_MEDICAL_CONSULTATION],
            reasoning="Symptoms suggest a condition worth discussing with a clinician, but "
                      "without indicators that this needs same-day care.",
        )

    # risk_level == "low"
    if top:
        return TriageResult(
            category=SELF_CARE_MONITORING,
            label=LABELS[SELF_CARE_MONITORING],
            reasoning=f"'{top.name}' matched with {top.severity} severity -- generally manageable "
                      f"with self-care, monitoring for changes.",
        )
    return TriageResult(
        category=SELF_CARE_MONITORING,
        label=LABELS[SELF_CARE_MONITORING],
        reasoning="No strong match against the knowledge base and no emergency indicators. "
                  "Monitor symptoms and consult a healthcare provider if they persist or worsen.",
    )
