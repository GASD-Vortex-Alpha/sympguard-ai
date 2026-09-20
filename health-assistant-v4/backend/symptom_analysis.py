"""
AI Symptom Analysis Module
---------------------------
Corresponds to the "AI SYMPTOM ANALYSIS" stage: takes extracted symptoms and
performs pattern analysis against the Medical Knowledge Base to surface
possible causes (conditions), each with an explainable confidence score.

Rule-based and explainable by design -- every match traces back to exactly
which symptoms triggered it. Swap `SymptomAnalyzer.analyze()` for a call into
a real embedding/LLM model later; nothing downstream needs to change since it
only depends on the ConditionMatch shape returned here.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

KB_PATH = Path(__file__).parent / "knowledge_base.json"


@dataclass
class ConditionMatch:
    condition_id: str
    name: str
    confidence: float
    severity: str
    description: str
    advice: str
    matched_symptoms: list = field(default_factory=list)
    category: str = ""
    icd10: str = ""
    first_aid: str = None
    related_conditions: list = field(default_factory=list)


class SymptomAnalyzer:
    def __init__(self, kb_path: Path = KB_PATH):
        with open(kb_path, "r", encoding="utf-8") as f:
            self.kb = json.load(f)["conditions"]

    def analyze(self, extracted_symptoms: list, top_k: int = 5) -> list:
        """Pattern-match extracted symptoms against every condition profile."""
        extracted = {s.lower() for s in extracted_symptoms}
        if not extracted:
            return []

        results = []
        for condition in self.kb:
            cond_symptoms = {s.lower() for s in condition["symptoms"]}
            overlap = extracted & cond_symptoms
            if not overlap:
                continue

            # Recall-biased weighting: better for triage to over- than under-flag
            coverage = len(overlap) / len(cond_symptoms)
            precision = len(overlap) / len(extracted)
            confidence = round(0.7 * coverage + 0.3 * precision, 3)

            results.append(
                ConditionMatch(
                    condition_id=condition["id"],
                    name=condition["name"],
                    confidence=confidence,
                    severity=condition["severity"],
                    description=condition["description"],
                    advice=condition["advice"],
                    matched_symptoms=sorted(overlap),
                    category=condition.get("category", ""),
                    icd10=condition.get("icd10", ""),
                    first_aid=condition.get("first_aid"),
                    related_conditions=condition.get("related_conditions", []),
                )
            )

        results.sort(key=lambda r: -r.confidence)
        return results[:top_k]


analyzer = SymptomAnalyzer()
