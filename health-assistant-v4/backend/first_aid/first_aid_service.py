"""
First-Aid module -- curated, structured, and deliberately NOT LLM-generated.

The brief is explicit: "Do not let the LLM freely invent first-aid
instructions. Use curated structured knowledge." This module is the only
source of first-aid text in the app; ai_provider.py never generates or
rewrites first-aid steps, it only ever displays what's here verbatim.
"""

import json
from pathlib import Path

DATA_PATH = Path(__file__).parent / "first_aid_data.json"

with open(DATA_PATH, "r", encoding="utf-8") as f:
    _DATA = json.load(f)

TOPICS = _DATA["topics"]
_BY_ID = {t["id"]: t for t in TOPICS}


def list_topics() -> list:
    """Preview cards -- id, topic, summary only (no full instructions)."""
    return [{"id": t["id"], "topic": t["topic"], "summary": t["summary"]} for t in TOPICS]


def get_topic(topic_id: str) -> dict:
    return _BY_ID.get(topic_id)


def get_topics_for_condition_ids(condition_ids: list) -> list:
    """
    Best-effort bridge from a matched knowledge_base.json condition id to a
    relevant first-aid topic, so the results screen can surface "View First
    Aid" only when it's actually relevant to what matched. Conservative by
    design: an explicit mapping table, not fuzzy text matching, so it never
    surfaces the wrong instructions.
    """
    mapping = {
        "choking": ["choking"],
        "severe_bleeding": ["severe-bleeding"],
        "burns": ["burns"],
        "anaphylaxis": ["severe-allergic-reaction"],
        "stroke": ["suspected-stroke"],
        "epilepsy": ["seizure"],
        "myocardial_infarction": [],  # deliberately no invasive first-aid entry -- guidance is "call emergency now"
        "heat_stroke": [],
    }
    topic_ids = []
    for cid in condition_ids:
        for tid in mapping.get(cid, []):
            if tid not in topic_ids:
                topic_ids.append(tid)
    return [_BY_ID[tid] for tid in topic_ids if tid in _BY_ID]


# Phrase/rule -> first-aid topic, used when an EMERGENCY was raised by the
# safety engine directly (raw text), which may have no strong knowledge-base
# condition match to hang a suggestion off of at all -- e.g. "I can't
# breathe and my throat feels like it's closing" might not score high
# against any single KB condition, but clearly calls for the anaphylaxis
# first-aid card regardless.
_PHRASE_TO_TOPIC = {
    "choking": "choking",
    "severe bleeding": "severe-bleeding",
    "uncontrolled bleeding": "severe-bleeding",
    "bleeding heavily": "severe-bleeding",
    "deep wound": "severe-bleeding",
    "throat closing": "severe-allergic-reaction",
    "swelling of the throat": "severe-allergic-reaction",
    "swelling of face and throat": "severe-allergic-reaction",
    "anaphylaxis": "severe-allergic-reaction",
    "seizure": "seizure",
    "seizure in infant": "seizure",
    "facial drooping": "suspected-stroke",
    "face drooping": "suspected-stroke",
    "slurred speech": "suspected-stroke",
    "sudden numbness": "suspected-stroke",
    "sudden weakness one side": "suspected-stroke",
}
_RULE_TO_TOPIC = {
    "stroke_fast": "suspected-stroke",
    "allergic_airway": "severe-allergic-reaction",
}


def get_topics_for_safety_result(safety_result) -> list:
    """safety_result: a safety.red_flag_engine.SafetyResult."""
    topic_ids = []
    for phrase in safety_result.matched_phrases:
        tid = _PHRASE_TO_TOPIC.get(phrase)
        if tid and tid not in topic_ids:
            topic_ids.append(tid)
    for combo in safety_result.matched_combinations:
        tid = _RULE_TO_TOPIC.get(combo["rule_id"])
        if tid and tid not in topic_ids:
            topic_ids.append(tid)
    return [_BY_ID[tid] for tid in topic_ids if tid in _BY_ID]
