"""
Adaptive Follow-Up Question Engine
------------------------------------
Deterministic, reusable, no LLM required (works fully in DEMO_MODE).

Flow (see main.py /api/symptoms/start and /api/symptoms/follow-up):

    extracted_symptoms
        -> build_queue()            picks relevant topics + orders questions,
                                     capped so we never ask everything we
                                     curated -- just what's relevant
        -> next_batch()             called repeatedly as the user answers,
                                     returns 1-2 questions at a time
        -> extract_signals()        turns "Yes" answers on flagged questions
                                     into red-flag phrases the safety engine
                                     already knows how to recognize, so a
                                     follow-up answer can escalate risk just
                                     as reliably as the original free text

Each topic (headache, chest pain, fever, ...) is triggered by overlap with
the symptoms nlp_extraction.py already pulled out of the user's initial free
text -- no separate classification step needed. If nothing matches, the
generic fallback questions are used instead so the flow never dead-ends.
"""

import json
from pathlib import Path

BANK_PATH = Path(__file__).parent / "question_bank.json"

with open(BANK_PATH, "r", encoding="utf-8") as f:
    _BANK = json.load(f)

MAX_QUESTIONS = _BANK.get("max_questions_per_session", 6)
BATCH_SIZE = _BANK.get("questions_per_batch", 2)
GENERIC_INTRO = _BANK["generic_intro_questions"]
TOPICS = _BANK["topics"]
FALLBACK = _BANK["generic_fallback_questions"]


def _topic_matches(topic: dict, extracted_symptoms_lower: set) -> bool:
    return bool(set(s.lower() for s in topic["trigger_symptoms"]) & extracted_symptoms_lower)


def matched_topics(extracted_symptoms: list) -> list:
    lower = {s.lower() for s in extracted_symptoms}
    return [t for t in TOPICS if _topic_matches(t, lower)]


def build_queue(extracted_symptoms: list) -> list:
    """
    Returns an ordered list of question dicts (each tagged with its
    topic_id), already deduplicated and capped at MAX_QUESTIONS. Always
    starts with the two generic intro questions (onset + severity), since
    those are useful regardless of which symptom was described.
    """
    queue = []
    seen_ids = set()

    def _add(q, topic_id=None):
        if q["id"] in seen_ids:
            return
        seen_ids.add(q["id"])
        item = dict(q)
        item["topic_id"] = topic_id
        queue.append(item)

    for q in GENERIC_INTRO:
        _add(q, topic_id="generic")

    topics = matched_topics(extracted_symptoms)

    if not topics:
        for q in FALLBACK:
            if len(queue) >= MAX_QUESTIONS:
                break
            _add(q, topic_id="fallback")
        return queue

    # Round-robin across matched topics so one very long topic list can't
    # crowd out a second, less-common but still-relevant topic.
    topic_queues = [(t["topic_id"], [q for q in t["questions"] if q["id"] in t["priority_order"]]) for t in topics]
    # keep each topic's own priority order
    for topic_id, qs in topic_queues:
        order = next(t["priority_order"] for t in topics if t["topic_id"] == topic_id)
        qs.sort(key=lambda q: order.index(q["id"]))

    idx = 0
    while len(queue) < MAX_QUESTIONS and any(topic_queues[i][1] for i in range(len(topic_queues))):
        topic_id, qs = topic_queues[idx % len(topic_queues)]
        if qs:
            _add(qs.pop(0), topic_id=topic_id)
        idx += 1
        if len(queue) >= MAX_QUESTIONS:
            break

    return queue[:MAX_QUESTIONS]


def is_critical_hit(question: dict, answer: str) -> bool:
    """True if this answer to this question should end questioning early
    (a strong-enough signal that more back-and-forth just delays getting to
    safety validation / results)."""
    if not question.get("critical"):
        return False
    return str(answer).strip().lower() == str(question.get("critical_answer", "")).strip().lower()


def next_batch(queue: list, answered: dict, batch_size: int = None) -> dict:
    """
    answered: {question_id: answer_string}, accumulated so far.

    Returns {"questions": [...], "done": bool, "stop_reason": str|None}.
    `done=True` means proceed straight to analysis -- either every queued
    question has been answered, or a critical answer short-circuited the
    rest (see docstring above: we don't ask every possible question).
    """
    batch_size = batch_size or BATCH_SIZE

    for q in queue:
        if q["id"] in answered and is_critical_hit(q, answered[q["id"]]):
            return {"questions": [], "done": True, "stop_reason": "critical_answer"}

    remaining = [q for q in queue if q["id"] not in answered]
    if not remaining:
        return {"questions": [], "done": True, "stop_reason": "queue_exhausted"}

    return {"questions": remaining[:batch_size], "done": False, "stop_reason": None}


def extract_signals(queue: list, answered: dict) -> list:
    """
    Turns flagged answers into the exact red-flag phrase text the safety
    engine matches on (see if_yes_signal / if_answer_signal /
    if_yes_signal_on_no in question_bank.json), so results can be fed
    straight into safety.red_flag_engine.run_safety_check() alongside the
    user's original free text.
    """
    signals = []
    for q in queue:
        if q["id"] not in answered:
            continue
        answer = str(answered[q["id"]]).strip()
        answer_lower = answer.lower()

        if "if_yes_signal" in q and answer_lower == "yes":
            signals.append(q["if_yes_signal"])
        if "if_yes_signal_on_no" in q and answer_lower == "no":
            signals.append(q["if_yes_signal_on_no"])
        if "if_answer_signal" in q and answer in q["if_answer_signal"]:
            signals.append(q["if_answer_signal"][answer])

    return signals


def answers_summary(queue: list, answered: dict) -> list:
    """Human-readable {question, answer} pairs, in queue order, for the
    doctor summary and the 'What you told us' results section."""
    by_id = {q["id"]: q for q in queue}
    out = []
    for qid, answer in answered.items():
        q = by_id.get(qid)
        if not q:
            continue
        out.append({"question": q["prompt"], "answer": answer, "topic": q.get("topic_id")})
    return out
