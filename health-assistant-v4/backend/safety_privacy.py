"""
Safety & Privacy Module
--------------------------
Cross-cutting concerns referenced by every stage in the architecture diagram:
data protection, consent, secure processing, and the mandatory medical
disclaimer. This module doesn't sit in the request pipeline sequence --
instead its helpers are called from wherever data enters, leaves, or gets
logged/stored (see main.py and models.py).

This is a starting scaffold, not a compliance implementation. See the
"Security & Compliance Notes" section of README.md for what a production
deployment handling real health data needs beyond this (encryption at rest,
audit logging infrastructure, a real PII-redaction library, legal review for
HIPAA/GDPR, etc.).
"""

MEDICAL_DISCLAIMER = (
    "This tool provides general information only and is not a medical "
    "diagnosis. Always consult a qualified healthcare provider for medical "
    "advice, and call emergency services for urgent symptoms."
)

CONSENT_NOTICE = (
    "By submitting symptoms, you consent to this text being processed to "
    "generate informational guidance. Authenticated users' checks are saved "
    "to their history; anonymous checks are stored without a user link."
)


def get_disclaimer() -> str:
    return MEDICAL_DISCLAIMER


def get_consent_notice() -> str:
    return CONSENT_NOTICE


def redact_for_logging(text: str, max_len: int = 80) -> str:
    """
    Truncates free text before it goes into application logs (server logs,
    error trackers) -- as opposed to the database, which stores the full
    input by design so a user can review their own history. Swap in a real
    PII-detection library (e.g. Microsoft Presidio) before production use;
    this truncation alone is not a substitute for proper de-identification.
    """
    text = text.strip()
    return text if len(text) <= max_len else text[:max_len] + "..."
