from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from safety_privacy import get_disclaimer


# --- Auth ---

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class UserOut(BaseModel):
    id: str
    email: EmailStr
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# --- Symptom checking pipeline ---

class SymptomCheckRequest(BaseModel):
    text: str = Field(..., min_length=3, description="Free-text description of symptoms")


class ConditionMatchOut(BaseModel):
    condition_id: str
    name: str
    confidence: float
    matched_symptoms: list[str]
    severity: str
    description: str
    advice: str
    category: str = ""
    icd10: str = ""
    first_aid: Optional[str] = None
    related_conditions: list[str] = Field(default_factory=list)


class SymptomCheckResponse(BaseModel):
    id: Optional[str] = None
    extracted_symptoms: list[str]
    risk_level: str = Field(description="'low' | 'moderate' | 'urgent' -- from the Risk Assessment stage")
    red_flags: list[str] = Field(default_factory=list)
    is_emergency: bool
    matches: list[ConditionMatchOut]
    recommendation: str = Field(description="Headline guidance from the Recommendation Engine")
    first_aid_steps: list[str] = Field(
        default_factory=list,
        description="Immediate lay-person first-aid instructions, populated for moderate/urgent matches that have them",
    )
    disclaimer: str = Field(default_factory=get_disclaimer)


# --- V4: adaptive follow-up question flow ---

class StartCheckRequest(BaseModel):
    text: str = Field(..., min_length=3, description="Free-text description of symptoms")
    region: Optional[str] = Field(None, description="Emergency-contacts region code, e.g. 'IN-TN', 'US'")


class QuestionOut(BaseModel):
    id: str
    prompt: str
    type: str = Field(description="'yes_no' | 'choice' | 'scale'")
    options: Optional[list[str]] = None
    topic_id: Optional[str] = None


class SafetyCheckOut(BaseModel):
    is_emergency: bool
    matched_phrases: list[str] = Field(default_factory=list)
    matched_combinations: list[dict] = Field(default_factory=list)


class StartCheckResponse(BaseModel):
    session_id: str
    extracted_symptoms: list[str]
    initial_safety_check: SafetyCheckOut
    questions: list[QuestionOut]
    done: bool = Field(description="True if there's nothing more to ask -- proceed straight to /api/symptoms/analyze")


class AnswerIn(BaseModel):
    question_id: str
    answer: str


class FollowUpRequest(BaseModel):
    session_id: str
    answers: list[AnswerIn]


class FollowUpResponse(BaseModel):
    questions: list[QuestionOut]
    done: bool


class AnalyzeRequest(BaseModel):
    session_id: str


class WhatYouToldUsOut(BaseModel):
    original_description: str
    extracted_symptoms: list[str]
    answers: list[dict]


class EvidenceItemOut(BaseModel):
    condition_id: str
    condition_name: str
    matched_on: list[str]
    source_type: str
    source_disclosure: str
    general_reference_suggestions: list[str]
    category: str = ""


class TriageOut(BaseModel):
    category: str
    label: str
    reasoning: str


class ExplanationOut(BaseModel):
    text: str
    source: str = Field(description="'ai' | 'deterministic_fallback'")
    note: Optional[str] = None


class FirstAidTopicOut(BaseModel):
    id: str
    topic: str
    summary: str


class FirstAidDetailOut(FirstAidTopicOut):
    immediate_steps: list[str]
    avoid: list[str]
    when_to_call_emergency: list[str]
    source: str
    last_reviewed: str


class EmergencyContactOut(BaseModel):
    name: str
    number: str


class EmergencyContactsOut(BaseModel):
    region_code: str
    label: str
    general: list[EmergencyContactOut]
    mental_health_crisis: list[EmergencyContactOut] = Field(default_factory=list)
    fallback_message: Optional[str] = None


class AnalyzeResponse(BaseModel):
    """
    The Explainable Results screen, section by section (see brief section 9):
    ASSESSMENT / URGENCY / WHY THIS WAS FLAGGED / POSSIBLE EXPLANATIONS /
    WHAT YOU TOLD US / RED FLAGS CHECKED / EVIDENCE / WHAT TO DO NEXT /
    WHEN TO SEEK PROFESSIONAL CARE / UNCERTAINTY-LIMITATIONS. Doctor-ready
    summary is a separate endpoint (POST /api/doctor-summary) since it's
    only generated on request, not on every analysis.
    """
    session_id: str
    is_emergency: bool
    triage: TriageOut
    why_flagged: str
    possible_explanations: list[ConditionMatchOut]
    explanation: ExplanationOut
    what_you_told_us: WhatYouToldUsOut
    red_flags_checked: SafetyCheckOut
    evidence: list[EvidenceItemOut]
    first_aid_suggestions: list[FirstAidTopicOut]
    emergency_contacts: Optional[EmergencyContactsOut] = None
    what_to_do_next: str
    when_to_seek_care: str
    uncertainty_limitations: str
    disclaimer: str = Field(default_factory=get_disclaimer)


class DoctorSummaryRequest(BaseModel):
    session_id: str


class DoctorSummaryResponse(BaseModel):
    generated_at_utc: str
    main_symptoms: list[str]
    onset: str
    severity: str
    duration: str
    associated_symptoms_and_answers: list[dict]
    red_flags_noted: list[str]
    triage_category: str
    triage_label: str
    possible_explanations_considered: list[dict]
    questions_to_discuss_with_clinician: list[str]
    original_description: str
    not_a_medical_record_notice: str
    plain_text: str
