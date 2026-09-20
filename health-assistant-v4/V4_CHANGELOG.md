# V4 Changelog

## V3 features preserved
- Full 5-stage pipeline logic: `nlp_extraction.py`, `symptom_analysis.py`,
  `risk_assessment.py`, `recommendation_engine.py` — all kept, all still used
  by the legacy endpoint.
- `POST /symptoms/check` and `GET /symptoms/history` — work exactly as before.
- `auth.py` / `models.py` — JWT + bcrypt + SQLAlchemy, untouched.
- `knowledge_base.json`'s 29 conditions, schema, and `_meta` documentation.
- `GET /conditions`, `GET /conditions/{id}/differential`, `GET /privacy-notice`.
- Docker/deployment shape (FastAPI backend + static frontend + Postgres).
- The "recall-biased, explainable, no fake confidence" design philosophy.

## New V4 features
- **Adaptive follow-up questions** (`backend/questions/`) — rule-based engine,
  curated question bank per symptom topic, deduplication, a cap on total
  questions asked, and early-stop when an answer is already conclusive.
- **Independent safety/red-flag engine** (`backend/safety/`) — ~50 phrases +
  5 combination rules, word-order-tolerant and negation-aware matching, runs
  twice (initial pass + final validation) and always wins over AI output.
- **Emergency Help** page + configurable `backend/emergency_contacts.json`
  (India/Tamil Nadu demo config: 112/108, plus a Tele MANAS 14416 mental-health
  crisis number surfaced specifically for mental-health-category red flags).
- **First-aid library** (`backend/first_aid/`) — 7 curated topics (severe
  bleeding, burns, choking, fainting, seizure, suspected stroke, severe
  allergic reaction), structured as DO NOW / AVOID / GET HELP IF / SOURCE.
  Never AI-generated.
- **Evidence/sources** (`backend/evidence/`) — traces every match back to
  which symptoms actually overlapped, and explicitly discloses that the
  knowledge base is an unverified educational scaffold rather than
  fabricating a specific citation.
- **Four-category triage** (`backend/triage.py`) — EMERGENCY / URGENT MEDICAL
  EVALUATION / ROUTINE MEDICAL CONSULTATION / SELF-CARE MONITORING, fully
  deterministic, with the safety-engine result as a hard override.
- **Doctor-ready summary** (`backend/doctor_summary.py`) — template-based,
  copyable/printable, explicitly never called a medical record.
- **AI fallback / DEMO_MODE** (`backend/ai_provider.py`) — works with zero API
  keys; the AI layer, when configured, only ever writes the explanation
  paragraph, never risk/triage/first-aid content.
- **First test suite for this project** (`backend/tests/`) — 61 tests
  actually executed during development, plus a FastAPI integration suite.
- **Redesigned frontend** — landing page, symptom-check app flow (adaptive
  Q&A → results dashboard), first-aid library page, emergency help page,
  shared design system, all vanilla HTML/CSS/JS (no framework, no build step).

## Two real bugs found and fixed during development
Both were caught by actually running tests against the code, not just by
inspection — worth calling out explicitly per the brief's "don't fake it"
instruction:

1. **Negation was silently broken for contractions.** V3's `normalize()`
   stripped apostrophes before `NEGATION_WORDS` was ever checked, so
   `"isn't"`/`"don't"` were split into two tokens and never matched anything.
   `"I don't have a fever"` incorrectly extracted `"fever"` as a present
   symptom. Fixed by preserving apostrophes in `normalize()` and expanding
   `NEGATION_WORDS` to cover common contractions. Also found and fixed a
   related self-negation bug where the phrase `"can't breathe"` — which
   legitimately contains the word `"can't"`, itself a negation cue — was
   canceling itself out and never matching at all.
2. **Triage reasoning could name the wrong condition with the wrong
   severity.** The triage engine used `matches[0]` (the highest-*confidence*
   match) to decide and explain the "urgent evaluation vs. routine" split,
   but `risk_assessment.py` can escalate risk based on a *different*,
   lower-confidence match (e.g. a vague "cough + runny nose" can score higher
   confidence for Common Cold while Influenza, a weaker match, is what
   actually drives the risk level to "moderate"). This produced reasoning
   text like `"'Common Cold' matched with moderate severity"` — Common Cold's
   real severity is "mild"; the sentence just had the wrong condition and a
   hardcoded wrong severity word. Fixed by having `risk_assessment.assess_risk()`
   return `driving_match_id` and having `triage.py` reason about that
   specific match instead of assuming it's always the top-confidence one.

See `backend/tests/test_nlp_negation.py` and
`backend/tests/test_triage.py::test_reasoning_names_the_condition_that_actually_drove_the_risk_level`
for the regression tests that would catch these again.

## Files changed
- `backend/nlp_extraction.py` — negation/contraction fix (see above)
- `backend/risk_assessment.py` — now backed by the shared safety engine;
  returns `driving_match_id`
- `backend/main.py` — full rewrite, adds the V4 pipeline endpoints alongside
  every preserved V3 endpoint
- `backend/schemas.py` — added ~20 new Pydantic models for the V4 pipeline
- `docker-compose.yml` — added `CORS_ORIGINS` / `ANTHROPIC_API_KEY` env vars
- `README.md` — rewritten for V4
- `frontend/index.html` — replaced (was a single utilitarian form; V3's
  original is documented in `docs/V3_AUDIT.md` rather than shipped alongside)

## Files added
```
backend/safety/{__init__.py,red_flag_engine.py}
backend/questions/{__init__.py,question_engine.py,question_bank.json}
backend/first_aid/{__init__.py,first_aid_service.py,first_aid_data.json}
backend/evidence/{__init__.py,evidence_service.py}
backend/emergency_contacts.json
backend/emergency_contacts_service.py
backend/triage.py
backend/doctor_summary.py
backend/ai_provider.py
backend/tests/{__init__.py,test_safety_engine.py,test_question_engine.py,
  test_triage.py,test_first_aid.py,test_emergency_contacts.py,test_evidence.py,
  test_doctor_summary.py,test_ai_fallback.py,test_nlp_negation.py,
  test_risk_assessment.py,test_api.py}
frontend/app.html, frontend/first-aid.html, frontend/emergency.html
frontend/css/styles.css
frontend/js/{config.js,api.js,app.js}
docs/V3_AUDIT.md, docs/SAFETY_ENGINE.md
.env.example, .gitignore
V4_CHANGELOG.md
```

## API changes
Additive only — nothing removed. New: `POST /api/symptoms/start`,
`POST /api/symptoms/follow-up`, `POST /api/symptoms/analyze`,
`POST /api/doctor-summary`, `GET /api/first-aid`, `GET /api/first-aid/{id}`,
`GET /api/emergency-contacts`, `GET /api/emergency-contacts/regions`,
`GET /api/sources`. See README's API table for the full list including
preserved V3 endpoints.

## How to run
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```
Open `frontend/index.html` in a browser. No API key required. Full details,
including Docker, in `README.md`.

## How to test
```bash
cd backend
pip install -r requirements.txt pytest httpx
pytest tests/
```
See README's "Running the tests" section for the honesty note about which
tests were actually executed during development (61, everything except the
FastAPI-dependent `test_api.py`) versus written-but-unexecuted due to this
sandbox having no network access to install FastAPI/httpx/pydantic/SQLAlchemy.

## Demo scenarios
See README's "Demo scenarios" section — Scenario A (normal headache, full
adaptive-question flow to a non-emergency result) and Scenario B (chest pain,
immediate emergency short-circuit with region-configured call buttons).

## Deployment steps
See README's "Deployment" section. Summary: deploy `backend/` via the
existing `Dockerfile` to any container platform, set `DATABASE_URL` to a
managed database, and add a `<meta name="sympguard-api-base" content="...">`
tag to the frontend HTML files before hosting them statically — no localhost
URL is hardcoded anywhere in the shipped frontend.

## Known limitations
See README's "Known Limitations" section for the full list: the safety
engine's keyword-matching ceiling, the knowledge base's unverified-scaffold
status, in-memory-only sessions, the un-executed FastAPI test file, and the
heuristic (not clinically validated) urgent/routine confidence threshold in
`triage.py`. This list is meant to be read, not skipped — it's here so
whoever demos this can honestly answer "what doesn't this do" if asked.
