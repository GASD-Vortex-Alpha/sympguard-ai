# V3 Audit — read before touching V4 code

This is a read-through of the uploaded V3 zip, done before any V4 changes. Goal: know what
already works so V4 preserves it, instead of rebuilding it.

## 1. Existing structure

```
health-assistant/
├── backend/
│   ├── main.py                  # FastAPI app, wires everything together
│   ├── nlp_extraction.py        # free text -> extracted symptom phrases
│   ├── symptom_analysis.py      # extracted symptoms -> ranked condition matches
│   ├── knowledge_base.json      # 29 curated conditions
│   ├── risk_assessment.py       # matches + red-flag text -> low/moderate/urgent
│   ├── recommendation_engine.py # risk level -> headline + first-aid text
│   ├── safety_privacy.py        # disclaimer, consent notice, log redaction
│   ├── models.py                # SQLAlchemy: User, SymptomCheck
│   ├── schemas.py                # Pydantic request/response models
│   ├── auth.py                   # JWT + bcrypt
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   └── index.html                # single-file vanilla HTML/CSS/JS client
├── docker-compose.yml             # backend + Postgres + nginx frontend
└── README.md
```

No `tests/` directory exists in V3 — there is nothing to run yet, so "run the existing tests
first" (step 17 of the brief) has nothing to execute. V4 adds the first test suite.

## 2. Existing pipeline (already matches the "diagram" in the code comments)

```
raw text
  -> nlp_extraction.normalize() + extract_symptoms()   [substring + fuzzy typo-tolerant match,
                                                          with negation detection: "no fever"]
  -> symptom_analysis.analyzer.analyze()                [overlap scoring vs. knowledge_base.json,
                                                          0.7*coverage + 0.3*precision, top 5]
  -> risk_assessment.assess_risk()                       [severity of matches + independent
                                                          red-flag phrase scan -> low/moderate/urgent]
  -> recommendation_engine.build_recommendation()         [risk level -> headline + first-aid text
                                                          pulled from matched conditions]
  -> SymptomCheckResponse                                 [returned to frontend, persisted to DB]
```

This is a genuinely reasonable design: rule-based and explainable (every match traces back to
literal matched words), and red-flag detection is already architecturally independent from the
condition-matching confidence score, so a single red-flag phrase escalates risk regardless of
what else matched. V4 keeps this pipeline as the analysis core and builds the new features
around it rather than replacing it.

## 3. Existing API endpoints

| Method | Path | Auth | What it does |
|---|---|---|---|
| GET | `/health` | none | liveness check |
| POST | `/auth/register` | none | create account |
| POST | `/auth/login` | none | JWT token |
| GET | `/auth/me` | required | current user |
| POST | `/symptoms/check` | optional | full pipeline, single-shot (no follow-up questions) |
| GET | `/symptoms/history` | required | past checks, re-run through the pipeline live |
| GET | `/conditions` | none | dump the whole knowledge base |
| GET | `/conditions/{id}/differential` | none | overlapping-symptom cross references |
| GET | `/privacy-notice` | none | disclaimer + consent text |

## 4. Existing modules — what each one actually does

- **`nlp_extraction.py`** — loads every symptom phrase out of the knowledge base as a vocabulary,
  sorts longest-phrase-first (so "chest pain" wins over bare "pain"), and does substring +
  `difflib.SequenceMatcher` fuzzy matching (typo tolerance, gated by both similarity ratio and
  length so short unrelated words can't falsely match). Negation window of 3 preceding words
  ("no", "denies", "without", etc.) filters out symptoms the user explicitly denied having.
- **`symptom_analysis.py`** — `SymptomAnalyzer` loads `knowledge_base.json` once at import time
  and scores every condition by symptom-set overlap with the extracted symptoms. Deliberately
  recall-biased (better to over- than under-flag for a triage tool). Returns a list of
  `ConditionMatch` dataclasses, already sorted, capped at top 5.
- **`risk_assessment.py`** — a small, separate, hardcoded `RED_FLAGS` set (11 phrases: chest
  pain, can't breathe, facial drooping, slurred speech, severe bleeding, unconscious, suicidal,
  seizure, etc.). Combines "highest-severity match above a confidence floor" with "any red flag
  present" — red flags bypass the confidence floor entirely, by design, so they can't be
  out-voted by a weak match.
- **`recommendation_engine.py`** — pure lookup table from risk level to a headline string, plus
  pulls `first_aid` text out of every matched condition that has one.
- **`safety_privacy.py`** — static disclaimer/consent strings + a log-truncation helper. Explicit
  docstring already says this is "a starting scaffold, not a compliance implementation."
- **`models.py` / `auth.py`** — real, working JWT + bcrypt auth against SQLAlchemy (SQLite by
  default, Postgres/MySQL via `DATABASE_URL`). Symptom checks are anonymous-allowed but linked to
  a user when authenticated.
- **`knowledge_base.json`** — 29 conditions across 10 categories, including a dedicated
  `emergency_trauma` category (anaphylaxis, choking, severe bleeding, burns, heat stroke) that
  already carries `first_aid` text. Each entry has `id`, `name`, `icd10` (explicitly flagged in
  `_meta` as "illustrative, not verified clinical coding"), `category`, `symptoms`, `severity`
  (`mild`/`moderate`/`emergency`), `description`, `advice`, optional `first_aid`, and
  `related_conditions`. This is a well-organized scaffold — V4 extends it rather than replacing
  it (adds first-aid *topics* as a separate curated module per the brief, since first aid needs
  to exist independently of which condition matched).
- **Frontend (`index.html`)** — single-shot form: textarea → one API call → render risk banner +
  matched conditions + first-aid box + disclaimer. No follow-up questions, no landing page, no
  emergency page, no first-aid library, no doctor summary, no evidence/sources display, no triage
  categories (only the 3 raw risk levels), no offline/demo-mode fallback (the app already works
  without an AI API key today, because there is no AI call anywhere in V3 — the "AI Symptom
  Analysis" stage is rule-based matching, not an LLM call).
- **Deployment** — working Dockerfile for the backend, docker-compose wiring backend + Postgres +
  an nginx static frontend container. CORS is wide open (`allow_origins=["*"]`), flagged with a
  `TODO` in the code itself.

## 5. What V4 preserves as-is

- The 5-stage pipeline architecture and every existing module's core logic (`nlp_extraction`,
  `symptom_analysis`, `risk_assessment`, `recommendation_engine`).
- `auth.py`, `models.py` (JWT + bcrypt + SQLAlchemy) — untouched.
- `knowledge_base.json`'s 29 existing conditions, schema, and `_meta` documentation — extended,
  not replaced.
- All existing endpoints — kept working exactly as before (`/symptoms/check` still works as a
  single-shot legacy endpoint).
- Docker/deployment shape (FastAPI backend + static frontend), SQLite-by-default / Postgres-ready
  `DATABASE_URL` pattern.
- The existing "recall-biased, explainable, no fake confidence" design philosophy.

## 6. What V4 improves

- `risk_assessment.py`'s red-flag list is narrow (11 phrases, no symptom *combinations*). V4 adds
  a dedicated, more thorough, independently-tested safety engine (`backend/safety/`) that layers
  combination rules on top, and adds a **final validation pass** after AI explanation generation
  so a red flag can never be "explained away."
- The knowledge base has `first_aid` text embedded per-condition (used only when that specific
  condition matches). V4 adds a separate, standalone first-aid library (`backend/first_aid/`) so
  first-aid content is reachable directly (landing page, dedicated page) and not just as a
  side-effect of a symptom match.
- The result screen shows matches + a headline, with no explicit "why," no evidence sourcing
  beyond the description text, and no uncertainty framing. V4 restructures this into the
  explainable-results sections the brief specifies.
- The frontend is a single utilitarian form. V4 redesigns it into a full landing page + multi-step
  app flow while keeping the vanilla HTML/CSS/JS approach (no build step, no new frontend
  framework, consistent with "don't replace working code just because something is newer").
- CORS is `["*"]` with a TODO. V4 makes it configurable via an environment variable with a safer
  default, and adds `.env.example`.

## 7. What V4 adds (net new, no prior V3 equivalent)

- Adaptive follow-up question engine (`backend/questions/`) — rule-based, reusable, no LLM
  required.
- Independent safety/red-flag engine with combination rules and documented non-exhaustiveness
  (`backend/safety/`).
- Emergency Help page + configurable `backend/emergency_contacts.json`.
- First-aid library module with structured entries (`backend/first_aid/`).
- Evidence/sources endpoint that is explicit about what is and isn't a verified citation
  (`backend/evidence/`) — no fabricated references.
- Four-category triage engine (`backend/triage.py`), deterministic, AI cannot downgrade it.
- Doctor-ready summary generator (`backend/doctor_summary.py`).
- AI-fallback/demo-mode provider (`backend/ai_provider.py`) — app works fully with zero API keys.
- First test suite for the project (`backend/tests/`).
- Redesigned frontend: landing page, symptom-check app flow, first-aid library page, emergency
  help page, shared design system.
