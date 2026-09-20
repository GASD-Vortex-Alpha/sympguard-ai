"""
Tests for backend/triage.py.

Run: pytest tests/test_triage.py   OR   python3 tests/test_triage.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import nlp_extraction as nlp
import risk_assessment as ra
import triage
from symptom_analysis import analyzer
from safety.red_flag_engine import run_safety_check


def _classify(text):
    norm = nlp.normalize(text)
    extracted = nlp.extract_symptoms(text)
    matches = analyzer.analyze(extracted)
    risk = ra.assess_risk(matches, norm)
    safety = run_safety_check(norm)
    return triage.classify(
        risk["risk_level"], risk["red_flags"], matches,
        safety_is_emergency=safety.is_emergency,
        driving_match_id=risk.get("driving_match_id"),
    )


def test_safety_emergency_always_wins_regardless_of_matches():
    result = _classify("I have crushing chest pain radiating to my arm and shortness of breath")
    assert result.category == triage.EMERGENCY


def test_stroke_signs_are_emergency():
    result = _classify("sudden severe weakness on one side of my body and slurred speech")
    assert result.category == triage.EMERGENCY


def test_mild_generic_symptoms_are_not_emergency():
    result = _classify("itchy eyes and sneezing with a runny nose")
    assert result.category != triage.EMERGENCY


def test_vague_symptoms_with_no_kb_match_are_self_care():
    result = _classify("I feel a bit tired today")
    assert result.category == triage.SELF_CARE_MONITORING


def test_reasoning_names_the_condition_that_actually_drove_the_risk_level():
    """Regression test for a real bug found during development: triage used
    to reason about matches[0] (highest CONFIDENCE) even when a DIFFERENT,
    lower-confidence match was what actually drove risk_level to
    'moderate'. Now it must use risk_assessment's driving_match_id."""
    norm = nlp.normalize("I have a runny nose and mild cough")
    extracted = nlp.extract_symptoms("I have a runny nose and mild cough")
    matches = analyzer.analyze(extracted)
    risk = ra.assess_risk(matches, norm)
    result = triage.classify(risk["risk_level"], risk["red_flags"], matches, driving_match_id=risk.get("driving_match_id"))
    # The driving match should be named in the reasoning, and its claimed
    # severity in the text must match its ACTUAL severity field.
    driving = next(m for m in matches if m.condition_id == risk["driving_match_id"])
    assert driving.name in result.reasoning
    assert driving.severity in result.reasoning


def test_specific_multi_symptom_match_reaches_urgent_evaluation():
    result = _classify(
        "I have fever, chills, muscle aches, fatigue, headache, cough, sore throat, and runny nose"
    )
    assert result.category == triage.URGENT_MEDICAL_EVALUATION


def test_four_categories_are_all_reachable():
    seen = {
        _classify("I have crushing chest pain and shortness of breath").category,
        _classify("frequent urination, burning urination, and pelvic pain").category,
        _classify("I have joint pain and stiffness in my knees for the past month").category,
        _classify("I feel a bit tired today").category,
    }
    assert seen == {
        triage.EMERGENCY,
        triage.URGENT_MEDICAL_EVALUATION,
        triage.ROUTINE_MEDICAL_CONSULTATION,
        triage.SELF_CARE_MONITORING,
    }


if __name__ == "__main__":
    import traceback
    tests = [(name, fn) for name, fn in list(globals().items()) if name.startswith("test_") and callable(fn)]
    passed, failed = 0, 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
            passed += 1
        except Exception:
            print(f"FAIL  {name}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
