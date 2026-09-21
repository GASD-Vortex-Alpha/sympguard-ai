"""
Tests for backend/onset_detection.py -- detects onset timing / severity
already stated in the initial free-text description, so main.py can skip
re-asking the generic_intro_questions for them.

Run: pytest tests/test_onset_detection.py   OR   python3 tests/test_onset_detection.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import onset_detection as od

CASES = [
    ("I have a headache since this morning", "Today", None),
    ("I have had a fever for 3 days", "1-3 days ago", None),
    ("symptoms started 5 days ago", "More than 3 days ago", None),
    ("I have had this cough for 2 weeks", "More than 2 weeks ago", None),
    ("it just started a few minutes ago", "Within the last hour", None),
    ("yesterday I started feeling nauseous", "1-3 days ago", None),
    ("I have a headache", None, None),
    ("I have a severe headache since this morning", "Today", "Severe - hard to ignore or function"),
    ("mild sore throat for the past 2 days", "1-3 days ago", "Mild - barely noticeable"),
    ("moderate pain, started last week", "More than 3 days ago", "Moderate - noticeable, manageable"),
    ("this is unbearable, started an hour ago", "Within the last hour", "Severe - hard to ignore or function"),
    ("I have had a headache for a month", "More than 2 weeks ago", None),
    ("woke up with a headache this morning, not too bad", "Today", "Mild - barely noticeable"),
    ("no particular timing mentioned here, just symptoms", None, None),
    ("been feeling dizzy for about 10 days now", "More than 3 days ago", None),
    ("started 2 weeks ago and getting worse", "More than 2 weeks ago", None),
]


def test_onset_and_severity_detection_matches_expected():
    for text, expected_onset, expected_severity in CASES:
        onset = od.detect_onset(text)
        severity = od.detect_severity(text)
        assert onset == expected_onset, f"onset mismatch for {text!r}: got {onset!r}, expected {expected_onset!r}"
        assert severity == expected_severity, f"severity mismatch for {text!r}: got {severity!r}, expected {expected_severity!r}"


def test_detect_intro_answers_only_includes_detected_fields():
    answers = od.detect_intro_answers("I have a headache")
    assert answers == {}

    answers2 = od.detect_intro_answers("severe headache since this morning")
    assert answers2 == {
        "onset_timing": "Today",
        "overall_severity": "Severe - hard to ignore or function",
    }

    answers3 = od.detect_intro_answers("I have had a fever for 3 days")
    assert answers3 == {"onset_timing": "1-3 days ago"}


def test_never_raises_on_empty_or_weird_input():
    for text in ["", "   ", "!!!???", "a" * 500, "12345"]:
        od.detect_onset(text)
        od.detect_severity(text)
        od.detect_intro_answers(text)


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
