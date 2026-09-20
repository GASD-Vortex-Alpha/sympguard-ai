"""
Recommendation Engine
-----------------------
Corresponds to the "RECOMMENDATION ENGINE" stage: turns the risk assessment
plus matched conditions into a personalized, safety-focused response --
self-care guidance, when to seek care, or an emergency alert.
"""

EMERGENCY_ALERT = (
    "Your symptoms may indicate a medical emergency. Call your local "
    "emergency number or go to the nearest emergency room immediately."
)
URGENT_CARE_MSG = (
    "These symptoms warrant prompt medical attention -- consider contacting "
    "a doctor or urgent care today."
)
MODERATE_CARE_MSG = (
    "Monitor your symptoms closely. If they persist beyond a few days or "
    "worsen, see a healthcare provider."
)
SELF_CARE_MSG = (
    "These symptoms are commonly manageable with rest and self-care. Seek "
    "medical advice if they persist or worsen."
)
NO_MATCH_MSG = (
    "We couldn't confidently match your description to a condition in our "
    "knowledge base. If symptoms are concerning or persistent, consult a "
    "healthcare provider directly."
)


def build_recommendation(risk_level: str, matches: list) -> dict:
    if risk_level == "urgent":
        headline = EMERGENCY_ALERT
    elif risk_level == "moderate":
        headline = URGENT_CARE_MSG
    elif matches:
        headline = SELF_CARE_MSG
    else:
        headline = NO_MATCH_MSG

    condition_advice = [{"condition": m.name, "advice": m.advice} for m in matches]

    # Surface first-aid text from every matched condition that has it, most
    # relevant (highest-confidence / most severe, since matches are already
    # sorted that way) first. Dedup in case two matches share identical text.
    first_aid_steps = []
    seen = set()
    for m in matches:
        if m.first_aid and m.first_aid not in seen:
            first_aid_steps.append(f"{m.name}: {m.first_aid}")
            seen.add(m.first_aid)

    return {"headline": headline, "condition_advice": condition_advice, "first_aid_steps": first_aid_steps}
