# V4 Changelog

## Post-delivery fixes and additions (from real deployment feedback)

After the initial V4 delivery, testing against a live Vercel+Supabase
deployment and real usage surfaced four more things worth documenting
explicitly:

1. **Session storage moved from an in-memory dict to the database**
   (`models.SymptomCheckSession`). The original in-memory `_SESSIONS` dict
   only works on a single long-running process -- it silently breaks on
   serverless platforms (Vercel, etc.) where consecutive requests for the
   same session can land on different, memory-isolated instances. Session
   state (raw text, region, extracted symptoms, answers so far) now lives
   in the same database as everything else. The question queue itself is
   deliberately NOT stored -- it's a pure function of extracted_symptoms,
   so it's recomputed on each request instead of risking two copies
   drifting apart. `/api/doctor-summary` similarly recomputes the full
   pipeline from stored inputs rather than caching a previous result,
   since the pipeline is fully deterministic -- simpler than serializing
   `ConditionMatch` objects into the database.
2. **A real ranking-fairness bug in `risk_assessment.py`.** Reported
   directly from live use: symptoms consistent with a common cold kept
   being explained as "Influenza" in the reasoning text. Root cause: a
   higher-severity match only needs to clear a low absolute confidence
   floor to become the "driving match" narrated in the reasoning text --
   and since a *mild*-severity match can never itself trigger escalation
   (severity only escalates the risk level when it strictly *increases*,
   and mild never increases past the "low" starting point), a
   moderate-severity condition could dominate the narrative merely by
   trailing not too far behind, even while a much stronger, milder match
   sat at the top of "Possible Explanations." Fixed with a
   `COMPETITIVE_MARGIN`: a higher-severity match now only drives escalation
   if its confidence is genuinely close to the top match's, not just above
   an absolute floor. A real tie still escalates (correctly cautious); a
   weak trailing match no longer hijacks the explanation.
3. **Onset/severity pre-detection** (`onset_detection.py`). If someone's
   initial description already says "severe headache since this morning,"
   the adaptive questions no longer re-ask "when did this start?" / "how
   severe is it?" -- a small regex-based detector recognizes common timing
   and severity phrasing (including numeric forms like "for 3 days," "5
   days ago," "for about 10 days") and pre-fills those two questions so
   `next_batch()` skips them automatically.
4. **Free-text mid-flow additions** (`POST /api/symptoms/add-details`).
   The adaptive questions are tap-only by design, but sometimes a symptom
   just doesn't fit any of them -- so there's now a "something else going
   on? type it here" option available throughout the follow-up flow.
   Whatever's typed is: (a) run through the same symptom extraction as the
   original description, potentially surfacing new question topics that
   weren't relevant before, (b) appended to the stored raw text so it's
   included in the final safety validation pass at analyze time, and (c)
   checked immediately for its own red flags, short-circuiting straight to
   results if what was just typed is itself an emergency signal (mirroring
   `/api/symptoms/start`'s behavior). Building and testing this surfaced
   another real gap: the rash/skin question topic's trigger list didn't
   include "itching" even though it's a real, extractable knowledge-base
   phrase -- fixed by broadening `question_bank.json`'s `rash_skin` topic
   triggers.

All four were caught and fixed the same way as everything else in this
project: by actually running the code against realistic input, not just
writing it. See `backend/tests/test_risk_assessment.py`,
`backend/tests/test_onset_detection.py`, and
`backend/tests/test_question_engine.py::test_add_details_can_surface_a_new_topic_not_in_the_original_text`
for the regression tests. Full test count: 74 (up from 68), all passing at
time of writing, same honesty caveat as before -- everything except
`test_api.py` was actually executed in this sandbox.

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

## Knowledge base expansion
V3 shipped with 29 conditions. That's thin for a symptom checker, so V4 adds
**41 more conditions (70 total)**, spread across more categories (plus two
new ones: `ent_eye` and `dermatological`) — see `backend/knowledge_base.json`.
Deliberately includes some conditions that are close differentials for
existing emergency ones (e.g. Bell's Palsy vs. stroke — both share the
"face drooping" symptom, and the system is designed to escalate to EMERGENCY
for either, since only a clinician can reliably tell them apart).

## Three real bugs found and fixed during development
All three were caught by actually running tests against the code, not just
by inspection — worth calling out explicitly per the brief's "don't fake it"
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
3. **Symptom extraction missed natural phrasing, including for a newly
   added emergency condition.** `nlp_extraction.py` required a symptom
   phrase to appear as a near-exact substring (or a same-length typo). Found
   while testing the new Deep Vein Thrombosis entry: `"my leg is swollen red
   and warm on one side with tenderness in my calf"` — a clear, plausible
   DVT description — extracted **zero** symptoms, because the KB's phrases
   ("leg swelling one side", "tenderness in calf") didn't appear as
   contiguous substrings once the sentence was worded naturally. Fixed by
   porting the same order-independent proximity matching already used in the
   safety engine into `nlp_extraction.py`. That fix alone didn't catch a
   second case found in the same session — `"my face is drooping"` still
   extracted nothing relevant for Bell's Palsy/stroke, because the KB only
   had `"facial drooping"` and the user said `"face"`, a different word
   entirely, not a reordering or a typo. Fixed by adding `"face drooping"` as
   an explicit synonym to both conditions (matching what the safety engine's
   phrase list already had).

See `backend/tests/test_nlp_negation.py`,
`backend/tests/test_triage.py::test_reasoning_names_the_condition_that_actually_drove_the_risk_level`,
and `backend/tests/test_kb_expansion.py` for the regression tests that would
catch these again.

## Files changed
- `backend/knowledge_base.json` — expanded from 29 to 70 conditions (see above)
- `backend/nlp_extraction.py` — negation/contraction fix + proximity-matching fix (see above)
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
