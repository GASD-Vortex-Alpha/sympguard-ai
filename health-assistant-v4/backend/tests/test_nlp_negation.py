"""
Regression tests for backend/nlp_extraction.py.

Covers a real bug found and fixed during V4 development: normalize() used
to strip apostrophes BEFORE negation words were checked, so "isn't",
"don't", etc. were silently split into two tokens and NEVER matched
NEGATION_WORDS -- "I don't have a fever" incorrectly extracted "fever" as
a present symptom.

Run: pytest tests/test_nlp_negation.py   OR   python3 tests/test_nlp_negation.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import nlp_extraction as nlp


def test_normalize_preserves_apostrophes():
    assert "don't" in nlp.normalize("I don't have a fever")


def test_negation_with_contraction_dont():
    assert nlp.extract_symptoms("I don't have a fever") == []


def test_negation_with_contraction_isnt():
    assert "chest pain" not in nlp.extract_symptoms("this isn't chest pain, just heartburn")


def test_negation_with_full_word_not_still_works():
    result = nlp.extract_symptoms("I do not have chest pain but I do have a runny nose")
    assert "chest pain" not in result
    assert "runny nose" in result


def test_positive_mentions_still_extracted_normally():
    result = nlp.extract_symptoms("I have a runny nose, sore throat, and mild fever since yesterday")
    assert "runny nose" in result
    assert "fever" in result


def test_typo_tolerance_still_works_after_the_fix():
    result = nlp.extract_symptoms("hedache and feve")
    assert "headache" in result
    assert "fever" in result


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
