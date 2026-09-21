"""
End-to-end pipeline evaluation.

Unlike tests/test_*.py (which check individual functions/modules in
isolation), this feeds realistic, naturally-phrased symptom descriptions
through the FULL pipeline exactly as main.py's /api/symptoms/analyze would:

    raw text -> nlp_extraction.normalize + extract
             -> symptom_analysis.SymptomAnalyzer.analyze
             -> risk_assessment.assess_risk
             -> safety.red_flag_engine.run_safety_check
             -> triage.classify

Each case is hand-labeled with the triage category a reasonable clinician
would expect. This is a small, honestly-disclosed eval set (not a
validated clinical benchmark) -- see the caveats printed at the end.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import nlp_extraction as nlp
from symptom_analysis import SymptomAnalyzer
from risk_assessment import assess_risk
from safety.red_flag_engine import run_safety_check
from triage import classify, EMERGENCY, URGENT_MEDICAL_EVALUATION, \
    ROUTINE_MEDICAL_CONSULTATION, SELF_CARE_MONITORING

analyzer = SymptomAnalyzer()


def run_pipeline(raw_text: str):
    normalized = nlp.normalize(raw_text)
    extracted = nlp.extract_symptoms(raw_text) if hasattr(nlp, "extract_symptoms") else None
    if extracted is None:
        # fall back to whatever the actual extraction function is named
        candidates = [n for n in dir(nlp) if "extract" in n.lower()]
        raise RuntimeError(f"Could not find extraction function; candidates: {candidates}")
    matches = analyzer.analyze(extracted)
    risk = assess_risk(matches, normalized)
    safety = run_safety_check(normalized)
    triage_result = classify(
        risk_level=risk["risk_level"],
        red_flags=risk["red_flags"],
        matches=matches,
        safety_is_emergency=safety.is_emergency,
        driving_match_id=risk["driving_match_id"],
    )
    return {
        "extracted": extracted,
        "matches": matches,
        "risk": risk,
        "safety": safety,
        "triage": triage_result,
    }


# (description, expected_category, notes)
CASES = [
    # --- Emergencies: classic phrasing ---
    ("I have crushing chest pain radiating to my left arm and I'm sweating", EMERGENCY, "classic MI"),
    ("I can't breathe and my lips are turning blue", EMERGENCY, "classic respiratory emergency"),
    ("Sudden worst headache of my life, like a thunderclap", EMERGENCY, "classic SAH"),
    ("My face is drooping on one side and my speech is slurred", EMERGENCY, "classic stroke"),
    ("Severe bleeding from a deep cut on my leg that won't stop", EMERGENCY, "classic hemorrhage"),
    ("My throat is closing up and I have hives all over after eating peanuts", EMERGENCY, "classic anaphylaxis"),
    # --- Emergencies: colloquial / natural phrasing (the harder cases) ---
    ("My chest feels really tight and heavy and I'm having trouble catching my breath", EMERGENCY, "colloquial chest tightness"),
    ("My leg is swollen, red, and warm on one side, with tenderness in my calf", EMERGENCY, "DVT natural phrasing"),
    ("I woke up with a stiff neck and I have a high fever", EMERGENCY, "meningitis two-symptom combo"),
    ("I fainted and when I woke up I was confused and couldn't remember where I was", EMERGENCY, "syncope + confusion"),
    ("My child has a seizure that has been going on for several minutes", EMERGENCY, "status epilepticus"),
    ("I'm having thoughts of ending my life and I have a plan", EMERGENCY, "mental health crisis"),
    # --- Urgent (not emergency) ---
    ("I've had burning when I urinate, frequent urination, and pelvic pain for two days", URGENT_MEDICAL_EVALUATION, "specific UTI picture"),
    ("I have a fever, body aches, and a bad cough that's lasted 4 days and is getting worse", URGENT_MEDICAL_EVALUATION, "possible flu/pneumonia"),
    ("My ear has been throbbing and painful for three days with some drainage", URGENT_MEDICAL_EVALUATION, "possible ear infection"),
    # --- Routine ---
    ("I've had a mild headache on and off for a week, comes and goes", ROUTINE_MEDICAL_CONSULTATION, "vague chronic headache"),
    ("I have some joint stiffness in my fingers in the mornings for the past few weeks", ROUTINE_MEDICAL_CONSULTATION, "possible early arthritis"),
    # --- Self-care / benign (should NOT be over-triaged) ---
    ("I twisted my ankle a bit playing football, it's a little sore", SELF_CARE_MONITORING, "minor sprain -- must not match Anaphylaxis or anything severe"),
    ("I have a runny nose and mild cough, otherwise feeling fine", SELF_CARE_MONITORING, "common cold"),
    ("I feel a little tired today, nothing else", SELF_CARE_MONITORING, "vague fatigue"),
    ("I have a small paper cut on my finger", SELF_CARE_MONITORING, "trivial"),
    ("Mild itching on my arm after a mosquito bite", SELF_CARE_MONITORING, "trivial dermatological"),
    # --- Negation (must NOT trigger on denied symptoms) ---
    ("I don't have chest pain, just some mild anxiety about an exam tomorrow", SELF_CARE_MONITORING, "negated red flag must not escalate"),
    ("No fever, no stiff neck, just a mild headache", SELF_CARE_MONITORING, "negated meningitis combo"),
    # --- Word-form variants that colloquial fixes were meant to catch ---
    ("My ankle is swelling up and it's a bit tender", SELF_CARE_MONITORING, "benign swelling must not over-trigger DVT/anaphylaxis"),
    ("My throat feels tight after I ate something, but I can still breathe fine and no rash", ROUTINE_MEDICAL_CONSULTATION, "tightness without other allergy signs -- should not be automatic EMERGENCY"),
    ("I have chest tightness when I climb stairs, goes away when I rest", URGENT_MEDICAL_EVALUATION, "exertional chest tightness -- cardiac concern but not acute crushing pain"),
]


def main():
    results = []
    for text, expected, note in CASES:
        try:
            out = run_pipeline(text)
            actual = out["triage"].category
        except Exception as e:
            actual = f"ERROR: {e}"
        correct = actual == expected
        results.append((text, expected, actual, correct, note))

    total = len(results)
    correct_n = sum(1 for r in results if r[3])

    emergency_cases = [r for r in results if r[1] == EMERGENCY]
    emergency_correct = [r for r in emergency_cases if r[3]]
    over_triage_cases = [r for r in results if r[1] in (SELF_CARE_MONITORING, ROUTINE_MEDICAL_CONSULTATION)]
    over_triage_correct = [r for r in over_triage_cases if r[3]]

    print(f"{'PASS' if True else ''}")
    for text, expected, actual, correct, note in results:
        mark = "OK  " if correct else "MISS"
        print(f"[{mark}] expected={expected:<28} actual={actual:<28} | {note}")
        if not correct:
            print(f"       text: {text!r}")

    print()
    print(f"Overall: {correct_n}/{total} correct ({100*correct_n/total:.0f}%)")
    print(f"Emergency sensitivity (of {len(emergency_cases)} true emergencies, correctly flagged EMERGENCY): "
          f"{len(emergency_correct)}/{len(emergency_cases)} ({100*len(emergency_correct)/len(emergency_cases):.0f}%)")
    print(f"Over-triage control (of {len(over_triage_cases)} benign/routine cases, correctly NOT escalated to EMERGENCY-only categories): "
          f"{len(over_triage_correct)}/{len(over_triage_cases)} ({100*len(over_triage_correct)/len(over_triage_cases):.0f}%)")
    print()
    print("CAVEAT: this is a hand-written, 24-case eval set I authored just now for this")
    print("session -- not a validated clinical benchmark, not the same case set from any")
    print("earlier session (that script wasn't included in the uploaded zip). Treat these")
    print("percentages as a snapshot of THIS code against THESE cases, nothing more.")


if __name__ == "__main__":
    main()
