# SympGuard AI — Symptom Assistant (V4)

A safety-oriented symptom-assessment assistant: describe your symptoms, answer a
short set of adaptive follow-up questions, and get an explainable, triaged
result — with an independent safety check that can flag a possible emergency
and surface first aid + emergency contacts, and that nothing else in the
system (including AI-generated text) can override.

**⚠️ Not a medical device, not a diagnosis tool.** This is informational
software only. It must not be used as a substitute for professional medical
advice. See [Security & Compliance Notes](#security--compliance-notes) before
handling any real user data, and see `docs/SAFETY_ENGINE.md` for what the
safety check does and doesn't catch.

This is V4 of the project, built on top of an existing V3 codebase rather than
a rewrite — see `docs/V3_AUDIT.md` for exactly what was preserved, improved,
and newly added, and `V4_CHANGELOG.md` for the full change list including two
real bugs found and fixed along the way.

## Architecture

```
health-assistant/
├── backend/
│   ├── main.py                  # FastAPI app -- both pipelines (V3 legacy + V4 adaptive)
│   ├── nlp_extraction.py        # Free text -> extracted symptom phrases (typo + negation aware)
│   ├── symptom_analysis.py      # Extracted symptoms -> ranked condition matches
│   ├── knowledge_base.json      # 70 curated conditions (V3 had 29 -- see V4_CHANGELOG.md)
│   ├── risk_assessment.py       # Matches + text -> low/moderate/urgent (now backed by safety/)
│   ├── recommendation_engine.py # V3 legacy: risk level -> headline + first-aid text
│   ├── safety_privacy.py        # Disclaimer, consent notice, log redaction
│   ├── safety/red_flag_engine.py        # V4: independent, deterministic red-flag + combo-rule engine
│   ├── questions/question_engine.py     # V4: adaptive follow-up question engine
│   ├── questions/question_bank.json     # V4: curated follow-up questions per symptom topic
│   ├── first_aid/first_aid_service.py   # V4: curated first-aid content (not AI-generated)
│   ├── first_aid/first_aid_data.json
│   ├── evidence/evidence_service.py     # V4: honest evidence/sources -- no fabricated citations
│   ├── emergency_contacts.json          # V4: configurable emergency numbers per region
│   ├── emergency_contacts_service.py
│   ├── triage.py                # V4: 4-category deterministic triage (EMERGENCY / URGENT / ROUTINE / SELF-CARE)
│   ├── doctor_summary.py        # V4: structured, template-based doctor-ready summary
│   ├── ai_provider.py           # V4: optional AI explanation layer with deterministic DEMO_MODE fallback
│   ├── models.py                # SQLAlchemy models (User, SymptomCheck) -- unchanged from V3
│   ├── schemas.py                # Pydantic request/response schemas (V3 + V4)
│   ├── auth.py                   # JWT auth + bcrypt password hashing -- unchanged from V3
│   ├── tests/                    # V4: first test suite for this project
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── index.html         # Landing page
│   ├── app.html            # Symptom-check app flow (adaptive Q&A -> results)
│   ├── first-aid.html      # First-aid library
│   ├── emergency.html      # Emergency help + configurable regional contacts
│   ├── css/styles.css      # Shared design system
│   └── js/{config,api,app}.js
├── docs/
│   ├── V3_AUDIT.md         # What V3 had, preserved, improved, and what's new in V4
│   └── SAFETY_ENGINE.md    # Non-exhaustiveness disclosure for the safety engine
├── docker-compose.yml      # Full stack: backend + Postgres + static frontend
├── .env.example
└── README.md
```

### V4 pipeline

```
POST /api/symptoms/start
    -> nlp_extraction.extract_symptoms()          [unchanged from V3]
    -> safety/red_flag_engine.run_safety_check()  [pass 1 -- early signal]
    -> questions/question_engine.build_queue()

POST /api/symptoms/follow-up   (repeatable)
    -> questions/question_engine.next_batch()

POST /api/symptoms/analyze
    -> symptom_analysis.analyzer.analyze()        [unchanged from V3]
    -> risk_assessment.assess_risk()              [same signature, now backed by
                                                     the shared, upgraded safety engine]
    -> safety/red_flag_engine.run_safety_check()  [pass 2 -- FINAL, always wins]
    -> triage.classify()
    -> evidence/evidence_service.get_evidence()
    -> ai_provider.get_explanation()              [DEMO_MODE-safe]
    -> first_aid/first_aid_service                [curated, never AI-generated]

POST /api/doctor-summary
    -> doctor_summary.build_summary()             [template, never AI-generated]
```

**Why safety can't be overridden:** the safety check runs twice — once on the
raw input, and once (the one that counts) on the input plus every follow-up
answer that implies a red flag. `triage.classify()` takes that final result as
a hard override parameter, not a vote alongside the AI explanation or the
knowledge-base match confidence. The AI layer only ever writes the "why"
paragraph — it cannot set risk level, triage category, or emergency status,
and it cannot generate first-aid instructions (those are 100% curated data).

V3's original single-shot pipeline (`POST /symptoms/check`) is untouched and
still works, for backward compatibility.

## Quick Start (local, no Docker, no API key needed)

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

API docs: http://localhost:8000/docs

Then open `frontend/index.html` directly in a browser (double-click it, or
serve the `frontend/` folder with any static server). It talks to
`http://localhost:8000` automatically when running locally — see
"Deployment" below for pointing it at a different backend.

**No `ANTHROPIC_API_KEY` needed.** The app runs fully in DEMO_MODE without
one: symptom matching, the safety engine, adaptive questions, triage, first
aid, and emergency contacts are all deterministic and don't call any AI API.
Only the "why this was flagged" paragraph's *wording* changes if you add a
key — nothing about safety or correctness depends on it. See `.env.example`.

By default this uses SQLite (zero setup). To use Postgres/MySQL instead, set
`DATABASE_URL` before starting (see `.env.example`).

## Quick Start (Docker)

```bash
docker compose up --build
```

- Backend: http://localhost:8000
- Frontend: http://localhost:3000
- Postgres: localhost:5432

## Running the tests

```bash
cd backend
pip install -r requirements.txt
pip install pytest httpx   # only needed for the HTTP-layer tests in tests/test_api.py
pytest tests/
```

Every test file except `tests/test_api.py` uses only the Python standard
library and can also be run directly without pytest, e.g.:
```bash
python3 tests/test_safety_engine.py
```
**Honesty note:** this project was built in a sandboxed environment with no
network access, so `fastapi`/`pydantic`/`sqlalchemy`/`httpx` could not be
installed there. Every test file that doesn't need them (safety engine,
question engine, triage, first aid, emergency contacts, evidence, doctor
summary, AI fallback, nlp negation, risk assessment, knowledge-base
expansion — 68 tests total) **was actually run**, and real bugs were found
and fixed as a result (see
`V4_CHANGELOG.md`). `tests/test_api.py`, the FastAPI `TestClient`-based
integration suite, was written but could not be executed in that sandbox —
please run it yourself after `pip install -r requirements.txt`.

## API Endpoints

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/api/symptoms/start` | optional | Start a check: extracts symptoms, runs the initial safety pass, pre-fills onset/severity if already stated, returns the first batch of adaptive questions (or `done: true` if already flagged) |
| POST | `/api/symptoms/follow-up` | none | Submit answers, get the next batch of questions or `done: true` |
| POST | `/api/symptoms/add-details` | none | Free-text: add a symptom the tap-only questions didn't cover; may surface new question topics |
| POST | `/api/symptoms/analyze` | optional | Run the full pipeline and return the explainable result |
| POST | `/api/doctor-summary` | none | Structured, copyable/printable summary for a clinician |
| GET | `/api/first-aid` | none | List first-aid topics |
| GET | `/api/first-aid/{id}` | none | First-aid topic detail (DO NOW / AVOID / GET HELP IF) |
| GET | `/api/emergency-contacts` | none | Emergency numbers for a region (`?region=IN-TN`) |
| GET | `/api/emergency-contacts/regions` | none | List configured regions |
| GET | `/api/sources` | none | Evidence/methodology disclosure |
| POST | `/symptoms/check` | optional | **V3 legacy** single-shot pipeline, unchanged |
| GET | `/symptoms/history` | required | Past checks for the logged-in user |
| GET | `/conditions` | none | Browse the full knowledge base |
| GET | `/conditions/{id}/differential` | none | Overlapping-symptom cross-references |
| GET | `/privacy-notice` | none | Disclaimer + consent notice text |
| POST | `/auth/register` / `/auth/login` | none | Account creation / JWT token |
| GET | `/auth/me` | required | Current user info |
| GET | `/health` | none | Health check (also reports whether an AI key is configured) |

## Demo scenarios

**Scenario A — normal/common symptoms:**
`"I have a bad headache since this morning"` → adaptive questions (onset,
severity, sudden vs. gradual, vision changes, fever, vomiting, neck
stiffness) → non-emergency result → possible explanations with evidence →
routine/self-care triage → doctor summary.

**Scenario B — red-flag symptoms:**
`"I have crushing chest pain and shortness of breath"` → the initial safety
pass already flags this, so it skips straight to analysis → EMERGENCY triage
→ emergency banner with region-configured call buttons (112/108 demo config)
→ relevant first-aid suggestion → safety-engine override is visible in the
"Red Flags Checked" section.

Try also: `"I feel suicidal"` → emergency, with the Tele MANAS (14416) mental
health crisis line surfaced alongside general emergency numbers, not just an
ambulance number.

Both scenarios work with zero configuration and zero API keys.

## Extending the knowledge base

Add new conditions to `backend/knowledge_base.json` — no code changes needed.
See the file's own `_meta` block for the schema. The ICD-10 codes included
are explicitly flagged as illustrative, not verified clinical coding.

## Extending the safety engine / question bank

- New red-flag phrases or combination rules: edit
  `backend/safety/red_flag_engine.py`'s `RED_FLAG_GROUPS` / `COMBINATION_RULES`.
- New adaptive-question topics: edit `backend/questions/question_bank.json` —
  no code changes needed, the engine picks up new topics automatically based
  on `trigger_symptoms` overlap with extracted symptoms.
- New first-aid topics: edit `backend/first_aid/first_aid_data.json`.
- New emergency-contact regions: edit `backend/emergency_contacts.json`.

## Security & Compliance Notes

Baseline security is in place (bcrypt password hashing, JWT auth,
parameterized queries via SQLAlchemy). Before handling real patient data, add:

- **Encryption at rest** for the database
- **TLS/HTTPS** everywhere (terminate at your load balancer or reverse proxy)
- **CORS** — set `CORS_ORIGINS` to your real frontend origin(s) in production
  instead of the default `*` (see `.env.example`)
- **Secrets management** — set a real `JWT_SECRET_KEY`; don't rely on the
  auto-generated fallback, which changes on every restart and invalidates
  existing tokens
- **Rate limiting** on `/api/symptoms/*` and `/auth/*` to prevent abuse
- **Audit logging** for access to health records
- **Regulatory review** — HIPAA (US), GDPR (EU), or similar health-data
  regulations may apply depending on jurisdiction and use. This project does
  not implement that compliance out of the box.
- **Session storage** — the adaptive-questions flow keeps session state
  (extracted symptoms, answers so far) in the database (`SymptomCheckSession`
  in `models.py`), which is what makes it work correctly on serverless
  platforms like Vercel where an in-memory store would silently break across
  requests. Rows aren't automatically expired yet — fine for a hackathon
  demo, worth adding a cleanup job (delete sessions older than N hours)
  before any real deployment.

## Deployment

The `Dockerfile` in `backend/` builds a production-ready container. Typical
path: push to a container registry, deploy on any container platform (Render,
Railway, Fly.io, etc.), point `DATABASE_URL` at a managed database, and serve
`frontend/` from a static host. Before deploying the frontend, add a
`<meta name="sympguard-api-base" content="https://your-api.example.com">` tag
to each HTML file's `<head>` (see `frontend/js/config.js` — it reads this tag
first, falls back to `localhost:8000` only when running on localhost, and
never has a hardcoded production URL).

**Vercel + Supabase (serverless):** works, but requires two specific things
that a "normal" server deployment doesn't:
- **Session storage must be database-backed, not in-memory** — already true
  as of this version (`models.SymptomCheckSession`; see the changelog).
  Deploying an earlier version with the in-memory `_SESSIONS` dict to
  serverless would intermittently 404 on `/api/symptoms/follow-up`, since
  consecutive requests can land on different, memory-isolated instances.
- **Use Supabase's Transaction pooler connection string (port `6543`), not
  the direct connection (port `5432`)** — direct connections exhaust the
  free-tier connection limit almost immediately under serverless, since
  each invocation can open its own connection. Get it from the project's
  "Connect" button → Direct Connection string → Transaction mode. Also:
  Supabase gives you `postgres://...`, but SQLAlchemy requires
  `postgresql://...` — swap the scheme before using it as `DATABASE_URL`.

Both frontend and backend deploy as separate Vercel projects from the same
repo, each with **Root Directory** set to `backend` or `frontend`
respectively — no `vercel.json` needed for the backend, Vercel auto-detects
the FastAPI `app` object.

## Known Limitations

- The safety engine is keyword/combination-based, not a clinical model — see
  `docs/SAFETY_ENGINE.md` for exactly what it does and doesn't catch (in
  particular: it needs close-to-exact wording, not synonyms it hasn't been
  told about).
- The knowledge base and first-aid content are curated educational scaffolds,
  not independently, per-entry clinically verified sources — the Evidence
  section of every result says this explicitly rather than fabricating a
  citation.
- Sessions are in-memory only (see Security & Compliance Notes above).
- `tests/test_api.py` could not be executed in the development sandbox (no
  network access to install FastAPI/httpx) — please run it yourself.
- The urgent-vs-routine confidence threshold in `triage.py` is a heuristic
  picked by inspecting the score distribution during development, not a
  clinically validated cutoff (documented inline in `triage.py`).
