"""
AI Health Symptom Assistant - FastAPI backend.

V3's original single-shot pipeline is fully preserved (see _run_pipeline,
POST /symptoms/check, GET /symptoms/history) so nothing that worked before
stops working. V4 adds a second, richer pipeline alongside it:

    POST /api/symptoms/start
        -> nlp_extraction.extract_symptoms()      (unchanged from V3)
        -> safety/red_flag_engine.run_safety_check()   [pass 1, early signal]
        -> questions/question_engine.build_queue()
    POST /api/symptoms/follow-up (repeatable)
        -> questions/question_engine.next_batch()
    POST /api/symptoms/analyze
        -> symptom_analysis.analyzer.analyze()    (unchanged from V3)
        -> risk_assessment.assess_risk()          (unchanged signature, now
                                                     backed by the shared,
                                                     upgraded safety engine)
        -> safety/red_flag_engine.run_safety_check()   [pass 2, FINAL --
                                                          this result always
                                                          wins, see triage.py]
        -> triage.classify()
        -> evidence/evidence_service.get_evidence()
        -> ai_provider.get_explanation()          (DEMO_MODE-safe)
        -> first_aid/first_aid_service            (curated, not AI-generated)
    POST /api/doctor-summary
        -> doctor_summary.build_summary()         (template, not AI-generated)

Session state (extracted symptoms, the question queue, answers so far) is
kept in a small in-memory store -- see _SESSIONS below. This is a
deliberate hackathon-appropriate simplification (brief section 20: don't
overengineer): no session table, no Redis, just a capped dict. It resets on
server restart; that's an accepted, documented limitation (see README), not
an oversight -- see also safety_privacy.py's guidance on not storing more
health data than necessary.

Run locally:
    pip install -r requirements.txt
    uvicorn main:app --reload

Docs:
    http://localhost:8000/docs
"""

import json
import logging
import os
import uuid
from collections import OrderedDict
from datetime import datetime, timedelta

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

import auth
import doctor_summary
import nlp_extraction
import risk_assessment
import recommendation_engine
import safety_privacy
import triage
import ai_provider
import emergency_contacts_service
from evidence import evidence_service
from first_aid import first_aid_service
from questions import question_engine
from safety import red_flag_engine as safety_engine
from symptom_analysis import analyzer
from models import SymptomCheck, User, get_db, init_db
from schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    ConditionMatchOut,
    DoctorSummaryRequest,
    DoctorSummaryResponse,
    EmergencyContactOut,
    EmergencyContactsOut,
    EvidenceItemOut,
    ExplanationOut,
    FirstAidDetailOut,
    FirstAidTopicOut,
    FollowUpRequest,
    FollowUpResponse,
    QuestionOut,
    SafetyCheckOut,
    StartCheckRequest,
    StartCheckResponse,
    SymptomCheckRequest,
    SymptomCheckResponse,
    Token,
    TriageOut,
    UserCreate,
    UserOut,
    WhatYouToldUsOut,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("health-assistant")

app = FastAPI(
    title="SympGuard AI - Symptom Assistant API",
    description="Safety-oriented symptom assessment API. Informational use only -- not a "
                "substitute for professional medical advice, and not a diagnosis tool.",
    version="4.0.0",
)

# V4: CORS origins are now configurable (V3 hardcoded "*" with a TODO).
# CORS_ORIGINS="*" (default, same as V3) or a comma-separated list of real
# origins for production, e.g. CORS_ORIGINS="https://yourapp.com".
_cors_origins_env = os.getenv("CORS_ORIGINS", "*").strip()
_allow_origins = ["*"] if _cors_origins_env == "*" else [o.strip() for o in _cors_origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()
    logger.info("Database initialized.")
    logger.info("AI provider available: %s", ai_provider.is_ai_available())
    if not ai_provider.is_ai_available():
        logger.info("DEMO_MODE: no ANTHROPIC_API_KEY set -- using deterministic fallback explanations.")


@app.get("/health")
def health_check():
    return {"status": "ok", "ai_available": ai_provider.is_ai_available()}


# ---------------- Auth (unchanged from V3) ----------------

@app.post("/auth/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(email=payload.email, hashed_password=auth.hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post("/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth.create_access_token(
        data={"sub": user.id}, expires_delta=timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return Token(access_token=token)


@app.get("/auth/me", response_model=UserOut)
def read_me(current_user: User = Depends(auth.require_user)):
    return current_user


# ---------------- V3 legacy single-shot pipeline (preserved as-is) ----------------

def _run_pipeline(raw_text: str):
    """The original V3 pipeline, unchanged. Still used by /symptoms/check
    and /symptoms/history so existing integrations keep working."""
    normalized = nlp_extraction.normalize(raw_text)
    extracted = nlp_extraction.extract_symptoms(raw_text)
    matches = analyzer.analyze(extracted)
    risk = risk_assessment.assess_risk(matches, normalized)
    recommendation = recommendation_engine.build_recommendation(risk["risk_level"], matches)
    return extracted, matches, risk, recommendation


def _to_match_out(matches) -> list:
    return [
        ConditionMatchOut(
            condition_id=m.condition_id,
            name=m.name,
            confidence=m.confidence,
            matched_symptoms=m.matched_symptoms,
            severity=m.severity,
            description=m.description,
            advice=m.advice,
            category=m.category,
            icd10=m.icd10,
            first_aid=m.first_aid,
            related_conditions=m.related_conditions,
        )
        for m in matches
    ]


@app.post("/symptoms/check", response_model=SymptomCheckResponse)
def check_symptoms(
    payload: SymptomCheckRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth.get_current_user),  # optional (anonymous allowed)
):
    """V3's original single-shot endpoint -- no follow-up questions, kept
    working exactly as before for backward compatibility. New integrations
    should prefer /api/symptoms/start -> /follow-up -> /analyze."""
    extracted, matches, risk, recommendation = _run_pipeline(payload.text)

    logger.info("symptom check processed: %s", safety_privacy.redact_for_logging(payload.text))

    record = SymptomCheck(
        user_id=current_user.id if current_user else None,
        raw_input=payload.text,
        extracted_symptoms=json.dumps(extracted),
        top_match_id=matches[0].condition_id if matches else None,
        top_match_confidence=matches[0].confidence if matches else None,
        is_emergency_flag=str(risk["risk_level"] == "urgent").lower(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return SymptomCheckResponse(
        id=record.id,
        extracted_symptoms=extracted,
        risk_level=risk["risk_level"],
        red_flags=risk["red_flags"],
        is_emergency=(risk["risk_level"] == "urgent"),
        matches=_to_match_out(matches),
        recommendation=recommendation["headline"],
        first_aid_steps=recommendation["first_aid_steps"],
    )


@app.get("/symptoms/history", response_model=list[SymptomCheckResponse])
def get_history(db: Session = Depends(get_db), current_user: User = Depends(auth.require_user)):
    records = (
        db.query(SymptomCheck)
        .filter(SymptomCheck.user_id == current_user.id)
        .order_by(SymptomCheck.created_at.desc())
        .limit(50)
        .all()
    )
    results = []
    for r in records:
        extracted = json.loads(r.extracted_symptoms) if r.extracted_symptoms else []
        matches = analyzer.analyze(extracted)
        risk = risk_assessment.assess_risk(matches, nlp_extraction.normalize(r.raw_input))
        recommendation = recommendation_engine.build_recommendation(risk["risk_level"], matches)

        results.append(
            SymptomCheckResponse(
                id=r.id,
                extracted_symptoms=extracted,
                risk_level=risk["risk_level"],
                red_flags=risk["red_flags"],
                is_emergency=(risk["risk_level"] == "urgent"),
                matches=_to_match_out(matches),
                recommendation=recommendation["headline"],
                first_aid_steps=recommendation["first_aid_steps"],
            )
        )
    return results


@app.get("/conditions")
def list_conditions():
    """Browse the full curated knowledge base."""
    return analyzer.kb


@app.get("/conditions/{condition_id}/differential")
def get_differential(condition_id: str):
    condition = next((c for c in analyzer.kb if c["id"] == condition_id), None)
    if not condition:
        raise HTTPException(status_code=404, detail="Condition not found")

    curated_ids = set(condition.get("related_conditions", []))
    own_symptoms = set(s.lower() for s in condition["symptoms"])

    overlapping = []
    for c in analyzer.kb:
        if c["id"] == condition_id:
            continue
        shared = own_symptoms & set(s.lower() for s in c["symptoms"])
        if shared or c["id"] in curated_ids:
            overlapping.append({
                "id": c["id"],
                "name": c["name"],
                "curated_related": c["id"] in curated_ids,
                "shared_symptoms": sorted(shared),
            })

    return {"condition_id": condition_id, "condition_name": condition["name"], "differential": overlapping}


@app.get("/privacy-notice")
def privacy_notice():
    return {
        "disclaimer": safety_privacy.get_disclaimer(),
        "consent_notice": safety_privacy.get_consent_notice(),
    }


# ---------------- V4: adaptive follow-up question pipeline ----------------

# In-memory session store. Deliberately simple (brief section 20: don't
# overengineer) -- see module docstring. Capped so a long-running demo
# instance can't grow this unboundedly; oldest sessions are evicted first.
_SESSIONS: "OrderedDict[str, dict]" = OrderedDict()
_MAX_SESSIONS = 500


def _evict_old_sessions():
    while len(_SESSIONS) > _MAX_SESSIONS:
        _SESSIONS.popitem(last=False)


def _get_session(session_id: str) -> dict:
    session = _SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found or expired. This can happen if the server restarted, or "
                   "if the session is older than this demo's in-memory session limit -- start a "
                   "new symptom check.",
        )
    return session


def _question_out(q: dict) -> QuestionOut:
    return QuestionOut(id=q["id"], prompt=q["prompt"], type=q["type"], options=q.get("options"), topic_id=q.get("topic_id"))


@app.post("/api/symptoms/start", response_model=StartCheckResponse)
def start_symptom_check(payload: StartCheckRequest):
    normalized = nlp_extraction.normalize(payload.text)
    extracted = nlp_extraction.extract_symptoms(payload.text)
    initial_safety = safety_engine.run_safety_check(normalized)
    queue = question_engine.build_queue(extracted)

    session_id = str(uuid.uuid4())
    _SESSIONS[session_id] = {
        "raw_text": payload.text,
        "region": payload.region,
        "extracted_symptoms": extracted,
        "queue": queue,
        "answered": {},
        "created_at": datetime.utcnow(),
        "last_result": None,
    }
    _evict_old_sessions()

    logger.info("symptom check started: %s", safety_privacy.redact_for_logging(payload.text))

    if initial_safety.is_emergency:
        # Emergency language in the very first message -- don't spend time
        # on follow-up questions. `done=True` tells the frontend to call
        # /api/symptoms/analyze immediately (which re-confirms this via the
        # same, authoritative safety check as its final validation pass).
        return StartCheckResponse(
            session_id=session_id,
            extracted_symptoms=extracted,
            initial_safety_check=SafetyCheckOut(**initial_safety.to_dict()),
            questions=[],
            done=True,
        )

    batch = question_engine.next_batch(queue, {})
    return StartCheckResponse(
        session_id=session_id,
        extracted_symptoms=extracted,
        initial_safety_check=SafetyCheckOut(**initial_safety.to_dict()),
        questions=[_question_out(q) for q in batch["questions"]],
        done=batch["done"],
    )


@app.post("/api/symptoms/follow-up", response_model=FollowUpResponse)
def follow_up(payload: FollowUpRequest):
    session = _get_session(payload.session_id)
    for a in payload.answers:
        session["answered"][a.question_id] = a.answer
    batch = question_engine.next_batch(session["queue"], session["answered"])
    return FollowUpResponse(questions=[_question_out(q) for q in batch["questions"]], done=batch["done"])


def _why_flagged(safety_result, matches: list) -> str:
    if safety_result.is_emergency:
        reasons = []
        if safety_result.matched_phrases:
            reasons.append(
                "specific wording matched known emergency warning signs ("
                + ", ".join(safety_result.matched_phrases) + ")"
            )
        if safety_result.matched_combinations:
            reasons.append(
                "a combination of symptoms matched a known emergency pattern ("
                + "; ".join(c["label"] for c in safety_result.matched_combinations) + ")"
            )
        base = " and ".join(reasons) if reasons else "an emergency indicator was detected"
        return (
            f"This was flagged as an emergency because {base}. This determination comes from an "
            f"independent, deterministic safety check that runs separately from the rest of the "
            f"analysis and cannot be downgraded by it."
        )
    if matches:
        return (
            f"'{matches[0].name}' and the other possibilities below were considered because your "
            f"description and answers overlapped with symptoms associated with them. See "
            f"'Possible Explanations' and 'Evidence' for exactly which symptoms matched."
        )
    return "No confident match was found against the knowledge base, and no emergency indicators were detected."


_WHAT_NEXT = {
    triage.EMERGENCY: "Contact emergency services now using the numbers provided, and follow "
                       "any first-aid guidance shown below while help is on the way.",
    triage.URGENT_MEDICAL_EVALUATION: "Arrange to be seen by a doctor or urgent care today or "
                                       "tomorrow rather than waiting to see if it resolves on its own.",
    triage.ROUTINE_MEDICAL_CONSULTATION: "Schedule a routine appointment with a healthcare "
                                          "provider to discuss these symptoms, especially if they persist or change.",
    triage.SELF_CARE_MONITORING: "Rest and manage symptoms at home, and monitor for any changes.",
}
_WHEN_TO_SEEK_CARE = {
    triage.EMERGENCY: "Now -- this is time-sensitive.",
    triage.URGENT_MEDICAL_EVALUATION: "Within the next 24 hours, sooner if symptoms worsen.",
    triage.ROUTINE_MEDICAL_CONSULTATION: "In the next few days to a couple of weeks, or sooner "
                                          "if symptoms worsen or new symptoms appear.",
    triage.SELF_CARE_MONITORING: "If symptoms persist beyond about a week, worsen, or new "
                                  "concerning symptoms appear.",
}
_UNCERTAINTY_NOTE = (
    "This assessment comes from keyword-level symptom matching against a curated, non-exhaustive "
    "knowledge base, plus a deterministic, non-exhaustive safety check (see the Safety page for "
    "what it does and doesn't catch). It can miss rare presentations or unfamiliar phrasing, and "
    "can also over-flag on limited symptom overlap by design. It is not a diagnosis and does not "
    "replace a clinician who can examine you directly."
)


@app.post("/api/symptoms/analyze", response_model=AnalyzeResponse)
def analyze_symptoms(
    payload: AnalyzeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth.get_current_user),
):
    session = _get_session(payload.session_id)
    raw_text = session["raw_text"]
    extracted = session["extracted_symptoms"]
    queue = session["queue"]
    answered = session["answered"]

    normalized_original = nlp_extraction.normalize(raw_text)
    signals = question_engine.extract_signals(queue, answered)
    # Final validation text = original description + every red-flag signal
    # implied by the follow-up answers (e.g. "worst headache of my life" if
    # they answered Yes to that question). This is what makes an answer
    # given DURING follow-up questions just as safety-relevant as something
    # said in the original free text.
    combined_text = " ".join([normalized_original] + signals)

    matches = analyzer.analyze(extracted)
    risk = risk_assessment.assess_risk(matches, combined_text)
    final_safety = safety_engine.run_safety_check(combined_text)  # <-- pass 2 / final validation
    result = triage.classify(
        risk["risk_level"], risk["red_flags"], matches,
        safety_is_emergency=final_safety.is_emergency,
        driving_match_id=risk.get("driving_match_id"),
    )

    answers_summary = question_engine.answers_summary(queue, answered)
    evidence = evidence_service.get_evidence(matches)
    explanation = ai_provider.get_explanation(extracted, answers_summary, matches, risk["red_flags"], result.label)

    first_aid_topics = first_aid_service.get_topics_for_condition_ids([m.condition_id for m in matches])
    if final_safety.is_emergency:
        for topic in first_aid_service.get_topics_for_safety_result(final_safety):
            if topic not in first_aid_topics:
                first_aid_topics.append(topic)

    emergency_contacts = None
    if final_safety.is_emergency:
        categories = safety_engine.matched_categories(final_safety)
        contacts = emergency_contacts_service.get_contacts(session.get("region"))
        emergency_contacts = EmergencyContactsOut(
            region_code=contacts["region_code"],
            label=contacts["label"],
            general=[EmergencyContactOut(**c) for c in contacts.get("general", [])],
            mental_health_crisis=(
                [EmergencyContactOut(**c) for c in contacts.get("mental_health_crisis", [])]
                if "mental_health" in categories else []
            ),
            fallback_message=contacts.get("fallback_message"),
        )

    logger.info("symptom check analyzed: %s", safety_privacy.redact_for_logging(raw_text))

    record = SymptomCheck(
        user_id=current_user.id if current_user else None,
        raw_input=raw_text,
        extracted_symptoms=json.dumps(extracted),
        top_match_id=matches[0].condition_id if matches else None,
        top_match_confidence=matches[0].confidence if matches else None,
        is_emergency_flag=str(final_safety.is_emergency).lower(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    # Cache for /api/doctor-summary so it doesn't need to recompute (and so
    # the summary always matches exactly what the results screen showed).
    session["last_result"] = {
        "matches": matches,
        "red_flags": risk["red_flags"],
        "triage_category": result.category,
        "triage_label": result.label,
        "answers_summary": answers_summary,
    }

    return AnalyzeResponse(
        session_id=payload.session_id,
        is_emergency=final_safety.is_emergency,
        triage=TriageOut(**result.to_dict()),
        why_flagged=_why_flagged(final_safety, matches),
        possible_explanations=_to_match_out(matches),
        explanation=ExplanationOut(**explanation),
        what_you_told_us=WhatYouToldUsOut(
            original_description=raw_text, extracted_symptoms=extracted, answers=answers_summary
        ),
        red_flags_checked=SafetyCheckOut(**final_safety.to_dict()),
        evidence=[EvidenceItemOut(**e) for e in evidence],
        first_aid_suggestions=[
            FirstAidTopicOut(id=t["id"], topic=t["topic"], summary=t["summary"]) for t in first_aid_topics
        ],
        emergency_contacts=emergency_contacts,
        what_to_do_next=_WHAT_NEXT[result.category],
        when_to_seek_care=_WHEN_TO_SEEK_CARE[result.category],
        uncertainty_limitations=_UNCERTAINTY_NOTE,
    )


@app.post("/api/doctor-summary", response_model=DoctorSummaryResponse)
def create_doctor_summary(payload: DoctorSummaryRequest):
    session = _get_session(payload.session_id)
    last = session.get("last_result")
    if not last:
        raise HTTPException(
            status_code=400,
            detail="No analysis found for this session yet -- call /api/symptoms/analyze first.",
        )
    summary = doctor_summary.build_summary(
        raw_text=session["raw_text"],
        extracted_symptoms=session["extracted_symptoms"],
        answers=last["answers_summary"],
        matches=last["matches"],
        red_flags=last["red_flags"],
        triage_category=last["triage_category"],
        triage_label=last["triage_label"],
    )
    return DoctorSummaryResponse(**summary)


# ---------------- V4: first aid / emergency contacts / evidence ----------------

@app.get("/api/first-aid", response_model=list[FirstAidTopicOut])
def list_first_aid_topics():
    return first_aid_service.list_topics()


@app.get("/api/first-aid/{topic_id}", response_model=FirstAidDetailOut)
def get_first_aid_topic(topic_id: str):
    topic = first_aid_service.get_topic(topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="First-aid topic not found")
    return topic


@app.get("/api/emergency-contacts", response_model=EmergencyContactsOut)
def get_emergency_contacts(region: str = None):
    contacts = emergency_contacts_service.get_contacts(region)
    return EmergencyContactsOut(
        region_code=contacts["region_code"],
        label=contacts["label"],
        general=[EmergencyContactOut(**c) for c in contacts.get("general", [])],
        mental_health_crisis=[EmergencyContactOut(**c) for c in contacts.get("mental_health_crisis", [])],
        fallback_message=contacts.get("fallback_message"),
    )


@app.get("/api/emergency-contacts/regions")
def get_emergency_contact_regions():
    return emergency_contacts_service.list_regions()


@app.get("/api/sources")
def get_sources_methodology():
    return evidence_service.methodology_summary()
