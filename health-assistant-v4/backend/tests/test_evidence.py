"""
Tests for backend/evidence/evidence_service.py.

Run: pytest tests/test_evidence.py   OR   python3 tests/test_evidence.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import nlp_extraction as nlp
from symptom_analysis import analyzer
from evidence import evidence_service as es


def test_evidence_traces_back_to_actual_matched_symptoms():
    text = "I have a runny nose, sore throat, and mild fever since yesterday"
    extracted = nlp.extract_symptoms(text)
    matches = analyzer.analyze(extracted)
    evidence = es.get_evidence(matches)
    assert len(evidence) == len(matches)
    for item, match in zip(evidence, matches):
        assert item["matched_on"] == match.matched_symptoms
        assert item["condition_id"] == match.condition_id


def test_no_fabricated_per_condition_citation():
    """Brief requirement: never fabricate citations, and state clearly when
    there is no verified source. Every evidence item must carry the honest
    disclosure rather than a made-up specific citation."""
    text = "I have a headache"
    extracted = nlp.extract_symptoms(text)
    matches = analyzer.analyze(extracted)
    evidence = es.get_evidence(matches)
    for item in evidence:
        assert "NOT" in item["source_disclosure"] or "not" in item["source_disclosure"]
        assert item["source_type"] == "curated_knowledge_base"


def test_empty_matches_returns_empty_evidence():
    assert es.get_evidence([]) == []


def test_methodology_summary_is_honest_about_the_confidence_score():
    summary = es.methodology_summary()
    assert "not a calibrated medical probability" in summary["what_the_confidence_number_is_not"]
    assert "safety_engine_note" in summary


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
