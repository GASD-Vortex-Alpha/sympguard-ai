"""
Tests for backend/safety/red_flag_engine.py.

Runnable two ways:
  pytest tests/test_safety_engine.py          (once pytest is installed)
  python3 tests/test_safety_engine.py         (plain-Python runner, no deps)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import nlp_extraction as nlp
from safety.red_flag_engine import run_safety_check, matched_categories


def _check(text):
    return run_safety_check(nlp.normalize(text))


def test_benign_text_is_not_flagged():
    assert _check("I have a runny nose and mild cough").is_emergency is False
    assert _check("I feel a bit tired today").is_emergency is False
    assert _check("I twisted my ankle a bit playing football").is_emergency is False


def test_standalone_red_flag_phrases():
    assert _check("I have crushing chest pain").is_emergency is True
    assert _check("I can't breathe properly").is_emergency is True
    assert _check("severe bleeding from the leg").is_emergency is True
    assert _check("I feel suicidal").is_emergency is True


def test_word_order_variants_still_match():
    # "face is drooping" should still match the "face drooping" phrase, and
    # "throat is closing" should match "throat closing" -- see the
    # proximity-matching rationale in red_flag_engine.py.
    r = _check("my face is drooping and my speech is slurred")
    assert r.is_emergency is True
    assert "face drooping" in r.matched_phrases
    assert "slurred speech" in r.matched_phrases

    r2 = _check("my throat is closing and I have hives")
    assert r2.is_emergency is True
    assert "throat closing" in r2.matched_phrases


def test_negation_prevents_false_positive():
    assert _check("I don't have chest pain, just some heartburn").is_emergency is False
    assert _check("I do not have any suicidal thoughts, just stress").is_emergency is False
    assert _check("no seizure, no fainting, just mild dizziness").is_emergency is False


def test_phrase_that_contains_a_negation_word_does_not_self_negate():
    # "can't breathe" contains "can't", which is ALSO a negation cue -- must
    # not cancel itself out.
    r = _check("I can't breathe properly")
    assert r.is_emergency is True
    assert "can't breathe" in r.matched_phrases

    assert _check("I can breathe fine, no issues").is_emergency is False


def test_combination_rule_cardiac():
    r = _check("crushing chest pain with shortness of breath and sweating")
    assert r.is_emergency is True
    assert any(c["rule_id"] == "cardiac_dyspnea" for c in r.matched_combinations)


def test_combination_rule_thunderclap_headache():
    # Neither half alone (in this exact wording) is a standalone red flag,
    # but together they are a recognized emergency pattern.
    benign = _check("I have a headache since this morning")
    assert benign.is_emergency is False

    r = _check("worst headache of my life with blurred vision")
    assert r.is_emergency is True
    assert any(c["rule_id"] == "thunderclap_headache_neuro" for c in r.matched_combinations)


def test_combination_rule_allergic_airway():
    r = _check("hives all over and my throat is closing")
    assert r.is_emergency is True
    assert any(c["rule_id"] == "allergic_airway" for c in r.matched_combinations)


def test_matched_categories_identifies_mental_health():
    r = _check("I feel suicidal and want to end my life")
    cats = matched_categories(r)
    assert "mental_health" in cats


def test_matched_categories_identifies_cardiac():
    r = _check("I have crushing chest pain")
    cats = matched_categories(r)
    assert "cardiac" in cats


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
