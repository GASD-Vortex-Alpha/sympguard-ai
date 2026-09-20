"""
Tests for backend/first_aid/first_aid_service.py.

Run: pytest tests/test_first_aid.py   OR   python3 tests/test_first_aid.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from first_aid import first_aid_service as fa
from safety.red_flag_engine import run_safety_check
import nlp_extraction as nlp

REQUIRED_TOPICS = {
    "severe-bleeding", "burns", "choking", "fainting",
    "seizure", "suspected-stroke", "severe-allergic-reaction",
}


def test_all_required_topics_present():
    ids = {t["id"] for t in fa.list_topics()}
    assert REQUIRED_TOPICS <= ids


def test_every_topic_has_required_structure():
    for topic in fa.TOPICS:
        assert topic["immediate_steps"], f"{topic['id']} missing immediate_steps"
        assert topic["avoid"], f"{topic['id']} missing avoid"
        assert topic["when_to_call_emergency"], f"{topic['id']} missing when_to_call_emergency"
        assert topic["source"], f"{topic['id']} missing source"
        assert topic["last_reviewed"], f"{topic['id']} missing last_reviewed"


def test_no_dosages_or_drug_names_in_first_aid_content():
    """Brief requirement: 'Do not provide drug dosages.' Scan for common
    dosage-pattern red flags (a number immediately followed by mg/ml/mcg)."""
    import re
    dosage_pattern = re.compile(r"\d+\s*(mg|ml|mcg|milligram|gram)\b", re.IGNORECASE)
    for topic in fa.TOPICS:
        full_text = " ".join(topic["immediate_steps"] + topic["avoid"])
        assert not dosage_pattern.search(full_text), f"{topic['id']} appears to contain a dosage"


def test_get_topic_returns_none_for_unknown_id():
    assert fa.get_topic("not-a-real-topic") is None


def test_condition_id_mapping_is_conservative():
    # myocardial_infarction deliberately has NO first-aid topic entry --
    # guidance for it is "call emergency now", not a hands-on procedure.
    topics = fa.get_topics_for_condition_ids(["myocardial_infarction"])
    assert topics == []

    topics2 = fa.get_topics_for_condition_ids(["choking"])
    assert len(topics2) == 1
    assert topics2[0]["id"] == "choking"


def test_safety_result_maps_to_relevant_topic_even_without_kb_match():
    result = run_safety_check(nlp.normalize("hives all over and my throat is closing"))
    topics = fa.get_topics_for_safety_result(result)
    ids = {t["id"] for t in topics}
    assert "severe-allergic-reaction" in ids


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
