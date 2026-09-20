"""
Evidence / Sources module.
----------------------------
"Never fabricate citations. If a result has no reliable source, state that
clearly" -- this module exists specifically to honor that rule, which means
it deliberately does NOT attach a specific journal/article citation to each
condition, because none were verified for this project (see knowledge_base.json
_meta: "structured starting scaffold, not validated medical content").

What this DOES provide, honestly:
1. Exactly which extracted symptoms overlapped with which matched condition
   (the real evidence the match is based on -- already computed by
   symptom_analysis.py, just surfaced here explicitly).
2. A clear, honest statement of what kind of source the knowledge base is
   (curated scaffold, not clinically verified per-entry) and where a user
   could independently look up general information on a topic.

Retrieval today is the same keyword-overlap scoring symptom_analysis.py
already does -- re-exposed here rather than duplicated, so introducing a
real retrieval backend (e.g. embeddings over a vetted medical corpus, or a
vector DB) later only means changing get_evidence()'s internals, not any
caller.
"""

GENERAL_REFERENCE_SOURCES = [
    "MedlinePlus (U.S. National Library of Medicine)",
    "Mayo Clinic patient education",
    "World Health Organization (WHO) fact sheets",
    "NHS (UK) health A-Z",
]

KB_DISCLOSURE = (
    "This assessment is generated from a curated internal knowledge base of "
    "condition-symptom patterns. The knowledge base is a structured "
    "educational scaffold and has NOT been individually verified, per "
    "entry, against a specific peer-reviewed source or clinical guideline. "
    "Treat every match as a starting point for a conversation with a "
    "clinician, not a verified citation."
)


def get_evidence(matches: list) -> list:
    """
    matches: list of ConditionMatch (from symptom_analysis.py) or
    dict-like objects with the same fields.

    Returns one evidence entry per match: what was actually matched
    (traceable, real), plus an honest source disclosure (not fabricated).
    """
    evidence = []
    for m in matches:
        matched_symptoms = m.matched_symptoms if hasattr(m, "matched_symptoms") else m["matched_symptoms"]
        name = m.name if hasattr(m, "name") else m["name"]
        condition_id = m.condition_id if hasattr(m, "condition_id") else m["condition_id"]
        category = m.category if hasattr(m, "category") else m.get("category", "")

        evidence.append({
            "condition_id": condition_id,
            "condition_name": name,
            "matched_on": matched_symptoms,
            "source_type": "curated_knowledge_base",
            "source_disclosure": KB_DISCLOSURE,
            "general_reference_suggestions": GENERAL_REFERENCE_SOURCES,
            "category": category,
        })
    return evidence


def methodology_summary() -> dict:
    """For GET /api/sources -- explains the approach generally, not tied to
    one result. Shown once, e.g. on an 'About the evidence' page/section."""
    return {
        "how_matching_works": (
            "Symptoms are extracted from your free-text description using phrase "
            "matching against the knowledge base's vocabulary (with basic typo "
            "tolerance and negation handling, e.g. 'no fever' is not counted as "
            "a symptom). Each condition in the knowledge base is then scored by "
            "how much its known symptom pattern overlaps with what you described."
        ),
        "what_the_confidence_number_is_not": (
            "It is a simple overlap score (coverage + precision of matched "
            "symptoms), not a calibrated medical probability and not a diagnosis "
            "confidence. It is intentionally recall-biased -- tuned to surface "
            "possibilities rather than rule them out."
        ),
        "kb_disclosure": KB_DISCLOSURE,
        "general_reference_suggestions": GENERAL_REFERENCE_SOURCES,
        "safety_engine_note": (
            "Emergency/red-flag detection runs as a separate, independent, "
            "deterministic check -- it does not depend on the knowledge-base "
            "matching above, and its result can never be downgraded by it."
        ),
    }
