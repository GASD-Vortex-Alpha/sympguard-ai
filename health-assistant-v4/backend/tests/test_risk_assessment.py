"""
Tests for backend/risk_assessment.py (V3 module, now backed by the shared
V4 safety engine internally -- signature unchanged).

Run: pytest tests/test_risk_assessment.py   OR   python3 tests/test_risk_assessment.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import nlp_extraction as nlp
import risk_assessment as ra
from symptom_analysis import analyzer


def _assess(text):
    norm = nlp.normalize(text)
    extracted = nlp.extract_symptoms(text)
    matches = analyzer.analyze(extracted)
    return ra.assess_risk(matches, norm)


def test_mild_symptoms_are_low_risk():
    result = _assess("I have a runny nose and sneezing")
    assert result["risk_level"] in ("low", "moderate")  # KB-dependent, but never urgent
    assert result["red_flags"] == []


def test_red_flag_forces_urgent_regardless_of_kb_match():
    result = _assess("I have crushing chest pain")
    assert result["risk_level"] == "urgent"
    assert "chest pain" in result["red_flags"]


def test_negated_red_flag_does_not_force_urgent():
    result = _assess("I don't have chest pain, just heartburn")
    assert "chest pain" not in result["red_flags"]


def test_driving_match_id_is_set_when_risk_is_moderate_or_urgent():
    result = _assess("I have fever, chills, muscle aches, fatigue, headache, cough, sore throat, and runny nose")
    if result["risk_level"] in ("moderate", "urgent"):
        assert result["driving_match_id"] is not None


def test_reasoning_is_never_empty():
    result = _assess("xyzzy nonsense text with no symptoms")
    assert result["reasoning"]


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
