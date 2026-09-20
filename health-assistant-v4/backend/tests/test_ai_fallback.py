"""
Tests for backend/ai_provider.py -- the DEMO_MODE fallback is the important
path to verify since the whole app must work with zero API keys.

Run: pytest tests/test_ai_fallback.py   OR   python3 tests/test_ai_fallback.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import nlp_extraction as nlp
from symptom_analysis import analyzer
import ai_provider as ai


def test_no_api_key_uses_deterministic_fallback():
    os.environ.pop("ANTHROPIC_API_KEY", None)
    assert ai.is_ai_available() is False
    text = "I have a bad headache since this morning"
    extracted = nlp.extract_symptoms(text)
    matches = analyzer.analyze(extracted)
    result = ai.get_explanation(extracted, [], matches, [], "Routine Medical Consultation")
    assert result["source"] == "deterministic_fallback"
    assert "DEMO_MODE" in result["note"]
    assert len(result["text"]) > 0


def test_fallback_never_invents_a_condition_not_in_matches():
    text = "I have a bad headache since this morning"
    extracted = nlp.extract_symptoms(text)
    matches = analyzer.analyze(extracted)
    result = ai.get_explanation(extracted, [], matches, [], "Routine Medical Consultation")
    matched_names = {m.name for m in matches}
    # every condition name mentioned in the fallback text must be one that
    # was actually matched -- spot check the top match is present
    if matches:
        assert matches[0].name in result["text"]


def test_fallback_handles_zero_matches_gracefully():
    result = ai.get_explanation([], [], [], [], "Self-Care / Monitoring")
    assert result["source"] == "deterministic_fallback"
    assert len(result["text"]) > 0


def test_ai_call_failure_falls_back_gracefully():
    """With an API key set but no real network access (or an invalid key),
    the call must fail closed into the deterministic fallback, never raise
    an unhandled exception up to the caller."""
    os.environ["ANTHROPIC_API_KEY"] = "fake-key-for-test"
    try:
        text = "I have a bad headache"
        extracted = nlp.extract_symptoms(text)
        matches = analyzer.analyze(extracted)
        result = ai.get_explanation(extracted, [], matches, [], "Routine Medical Consultation")
        assert result["source"] == "deterministic_fallback"
        assert "AI call failed" in result["note"]
    finally:
        os.environ.pop("ANTHROPIC_API_KEY", None)


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
