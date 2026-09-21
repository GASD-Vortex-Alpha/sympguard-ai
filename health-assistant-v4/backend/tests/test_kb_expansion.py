"""
Regression tests for the V4 knowledge-base expansion (29 -> 70 conditions)
and the nlp_extraction.py proximity-matching fix that came out of testing it.

Run: pytest tests/test_kb_expansion.py   OR   python3 tests/test_kb_expansion.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import nlp_extraction as nlp
from symptom_analysis import analyzer
import risk_assessment as ra
import triage
from safety.red_flag_engine import run_safety_check

KB_PATH = Path(__file__).parent.parent / "knowledge_base.json"


def test_knowledge_base_has_at_least_70_conditions():
    kb = json.load(open(KB_PATH))
    assert len(kb["conditions"]) >= 70


def test_no_duplicate_condition_ids():
    kb = json.load(open(KB_PATH))
    ids = [c["id"] for c in kb["conditions"]]
    assert len(ids) == len(set(ids))


def test_all_related_condition_references_are_valid():
    kb = json.load(open(KB_PATH))
    ids = {c["id"] for c in kb["conditions"]}
    for c in kb["conditions"]:
        for r in c.get("related_conditions", []):
            assert r in ids, f"{c['id']} references unknown related_condition {r}"


def _full_pipeline(text):
    norm = nlp.normalize(text)
    extracted = nlp.extract_symptoms(text)
    matches = analyzer.analyze(extracted)
    risk = ra.assess_risk(matches, norm)
    safety = run_safety_check(norm)
    result = triage.classify(risk["risk_level"], risk["red_flags"], matches,
                              safety_is_emergency=safety.is_emergency,
                              driving_match_id=risk.get("driving_match_id"))
    return extracted, matches, result


def test_extraction_handles_reordered_multiword_phrases():
    """Regression test: nlp_extraction used to require a symptom phrase to
    appear as a near-exact substring. Natural phrasing that reorders or
    inserts a word into a multi-word phrase ("tenderness in my calf" vs. the
    KB's "tenderness in calf") extracted nothing at all. Found while testing
    the new Deep Vein Thrombosis entry -- a plausible, clearly-worded DVT
    description extracted zero symptoms before this fix."""
    extracted, matches, result = _full_pipeline(
        "my leg is swollen red and warm on one side with tenderness in my calf"
    )
    assert len(extracted) > 0
    assert any(m.condition_id == "deep_vein_thrombosis" for m in matches)
    assert result.category == triage.EMERGENCY


def test_bells_palsy_and_stroke_both_surface_for_face_drooping():
    """Regression test: the KB only had 'facial drooping' as a symptom
    phrase, but a very natural way to describe this is 'my face is
    drooping' -- which contains the word 'face', not 'facial'. Different
    words, not a typo, so even proximity matching couldn't bridge it. Fixed
    by adding 'face drooping' as an explicit synonym to both stroke and
    bells_palsy (matching what the safety engine's phrase list already had).
    Both conditions should now show up as possible explanations, and the
    result must still be EMERGENCY regardless -- these two are supposed to
    be indistinguishable without a clinical exam."""
    extracted, matches, result = _full_pipeline("my face is drooping on one side and I am drooling")
    assert "face drooping" in extracted
    match_ids = {m.condition_id for m in matches}
    assert "stroke" in match_ids
    assert "bells_palsy" in match_ids
    assert result.category == triage.EMERGENCY


def test_new_emergency_conditions_reach_emergency_triage():
    for text in [
        "I feel very thirsty, frequent urination, fruity smelling breath, and confusion",
        "sudden shortness of breath, sharp chest pain, coughing up blood",
    ]:
        _, matches, result = _full_pipeline(text)
        assert result.category == triage.EMERGENCY, f"expected EMERGENCY for: {text}"


def test_new_mild_conditions_do_not_over_trigger_emergency():
    for text in [
        "I have a red itchy ring shaped rash on my arm",
        "lower back pain after lifting a heavy box, worse when I move",
    ]:
        _, matches, result = _full_pipeline(text)
        assert result.category != triage.EMERGENCY, f"unexpectedly EMERGENCY for: {text}"


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
