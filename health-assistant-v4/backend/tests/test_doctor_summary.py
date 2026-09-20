"""
Tests for backend/doctor_summary.py.

Run: pytest tests/test_doctor_summary.py   OR   python3 tests/test_doctor_summary.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import nlp_extraction as nlp
from symptom_analysis import analyzer
import risk_assessment as ra
import triage
import doctor_summary as ds
from questions import question_engine as qe


def _build(text, answered):
    extracted = nlp.extract_symptoms(text)
    matches = analyzer.analyze(extracted)
    risk = ra.assess_risk(matches, nlp.normalize(text))
    result = triage.classify(risk["risk_level"], risk["red_flags"], matches, driving_match_id=risk.get("driving_match_id"))
    queue = qe.build_queue(extracted)
    answers = qe.answers_summary(queue, answered)
    return ds.build_summary(text, extracted, answers, matches, risk["red_flags"], result.category, result.label)


def test_summary_never_calls_itself_a_medical_record():
    summary = _build("I have a headache", {})
    full_text = summary["plain_text"].lower()
    assert "medical record" in full_text  # should MENTION it, to say it's NOT one
    assert "not a medical record" in full_text


def test_summary_includes_original_text_verbatim():
    text = "I have a bad headache since this morning, worse than usual"
    summary = _build(text, {})
    assert summary["original_description"] == text
    assert text in summary["plain_text"]


def test_summary_reflects_actual_answers_given():
    summary = _build("I have a headache", {"onset_timing": "Today", "headache_worst_ever": "No"})
    qa_pairs = summary["associated_symptoms_and_answers"]
    answers_given = {qa["answer"] for qa in qa_pairs}
    assert "No" in answers_given
    assert summary["onset"] == "Today"


def test_summary_includes_discussion_questions():
    summary = _build("I have a headache", {})
    assert len(summary["questions_to_discuss_with_clinician"]) > 0


def test_summary_notes_red_flags_when_present():
    summary = _build("I have crushing chest pain", {})
    assert len(summary["red_flags_noted"]) > 0
    assert any("chest pain" in q for q in summary["questions_to_discuss_with_clinician"])


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
