"""
Tests for backend/questions/question_engine.py.

Run: pytest tests/test_question_engine.py   OR   python3 tests/test_question_engine.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import nlp_extraction as nlp
from questions import question_engine as qe
from safety.red_flag_engine import run_safety_check


def test_build_queue_starts_with_generic_intro():
    queue = qe.build_queue(["headache"])
    assert queue[0]["id"] == "onset_timing"
    assert queue[1]["id"] == "overall_severity"


def test_build_queue_never_exceeds_max_questions():
    queue = qe.build_queue(["headache", "chest pain", "fever", "cough"])
    assert len(queue) <= qe.MAX_QUESTIONS


def test_build_queue_falls_back_when_no_topic_matches():
    queue = qe.build_queue(["some symptom nothing matches"])
    ids = [q["id"] for q in queue]
    assert "fallback_associated" in ids or "onset_timing" in ids  # generic intro always present


def test_next_batch_returns_batches_and_finishes():
    queue = qe.build_queue(["headache"])
    answered = {}
    total_asked = 0
    for _ in range(10):
        batch = qe.next_batch(queue, answered)
        if batch["done"]:
            break
        for q in batch["questions"]:
            answered[q["id"]] = "No" if q["type"] == "yes_no" else q["options"][0]
            total_asked += 1
    assert total_asked > 0
    assert total_asked <= qe.MAX_QUESTIONS


def test_critical_answer_stops_early():
    queue = qe.build_queue(["headache"])
    answered = {"onset_timing": "Today", "overall_severity": "Mild - barely noticeable"}
    batch = qe.next_batch(queue, answered)
    assert batch["done"] is False  # not yet -- worst_ever hasn't been asked
    answered["headache_onset_speed"] = "Gradually"
    answered["headache_worst_ever"] = "Yes"  # this IS a standalone red flag -> should stop
    batch2 = qe.next_batch(queue, answered)
    assert batch2["done"] is True
    assert batch2["stop_reason"] == "critical_answer"


def test_extract_signals_maps_yes_answers_to_red_flag_phrases():
    queue = qe.build_queue(["headache"])
    answered = {"headache_worst_ever": "Yes"}
    signals = qe.extract_signals(queue, answered)
    assert "worst headache of my life" in signals


def test_extract_signals_ignores_no_answers():
    queue = qe.build_queue(["headache"])
    answered = {"headache_worst_ever": "No", "headache_vision": "No"}
    signals = qe.extract_signals(queue, answered)
    assert signals == []


def test_full_flow_sudden_headache_plus_vision_changes_is_emergency():
    """End-to-end: build queue, simulate answers, feed signals back into the
    safety engine -- this is exactly what main.py's /api/symptoms/analyze
    does for the final validation pass."""
    text = "I have a bad headache since this morning"
    extracted = nlp.extract_symptoms(text)
    queue = qe.build_queue(extracted)
    answered = {
        "onset_timing": "Within the last hour",
        "overall_severity": "Severe - hard to ignore or function",
        "headache_onset_speed": "Suddenly",
        "headache_worst_ever": "No",
        "headache_vision": "Yes",
        "headache_fever": "No",
    }
    signals = qe.extract_signals(queue, answered)
    combined = nlp.normalize(text + " " + " ".join(signals))
    result = run_safety_check(combined)
    assert result.is_emergency is True


def test_answers_summary_is_human_readable():
    queue = qe.build_queue(["headache"])
    answered = {"onset_timing": "Today"}
    summary = qe.answers_summary(queue, answered)
    assert summary[0]["question"] == "When did this start?"
    assert summary[0]["answer"] == "Today"


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
