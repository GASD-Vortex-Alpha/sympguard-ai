# Safety Engine — what it does and doesn't catch

This document is linked from the app's Safety page and from
`backend/safety/red_flag_engine.py`. It exists because the brief requires
this rule set to be documented as **not medically exhaustive**, and we mean
that literally, not as boilerplate.

## What the safety engine is

A small, deterministic, keyword-and-combination-rule system that runs
**independently** of symptom matching and independently of any AI call. It
runs twice per symptom check:

1. **Pass 1**, on the raw text the user first types in — before any
   follow-up questions are even generated.
2. **Pass 2 (final validation)**, on the original text plus every red-flag
   signal implied by the user's follow-up answers — right before the result
   screen is built.

Whatever pass 2 decides **always wins**. Nothing computed after it (the AI
explanation, the knowledge-base match confidence) can downgrade an
emergency result — see `triage.py`'s `classify()`, which takes the safety
result as a hard override, not a vote.

## How it decides

- **Standalone phrases** (`RED_FLAG_GROUPS`): a fixed list of ~50 phrases
  organized into categories (airway/breathing, cardiac, neurological,
  bleeding/trauma, allergic, mental health, obstetric, pediatric) purely for
  readability — the categories aren't used for scoring.
- **Combination rules** (`COMBINATION_RULES`): a handful of rules that only
  fire when symptoms from two (or three) different groups are present
  together — e.g. a sudden, severe headache is only escalated when paired
  with vision changes, vomiting, or neck stiffness; on its own it is common
  and not automatically flagged.
- **Word-order tolerance**: matching checks whether all the words of a
  phrase appear near each other, in any order, rather than requiring an
  exact substring — so "my throat is closing" still matches the phrase
  "throat closing".
- **Negation awareness**: a phrase immediately preceded by "no", "not",
  "don't", "isn't", etc. is not counted, so "I don't have chest pain" isn't
  flagged. (This fixed a real, pre-existing bug in V3's negation handling
  for contractions — see `V4_CHANGELOG.md`.)

## What it does NOT do, on purpose

- It does not understand synonyms or paraphrase it hasn't been told about.
  "A lot of trouble breathing" will not match "difficulty breathing" unless
  the exact words are present (word-order tolerance helps with reordering,
  not with different vocabulary). This is the single biggest limitation of
  a keyword system versus a clinician or a large language model, and it is
  not solved here.
- It does not weigh severity, duration, or the person's overall context —
  only whether specific wording is present.
- It has not been validated against real clinical cases, a real triage
  dataset, or reviewed by a licensed medical professional. The phrase list
  and combination rules were written by inference from commonly known
  emergency-recognition patterns (e.g. FAST for stroke, anaphylaxis signs),
  not derived from a clinical guideline document.
- It can both **over-flag** (a phrase used in an unrelated context — e.g.
  "my grandmother had a stroke" would not itself match since "stroke" alone
  isn't a listed phrase, but a hypothetical broader phrase list could) and
  **under-flag** (a real emergency described in unfamiliar words). Given the
  choice, this project's V3 code already stated a "recall-biased" design
  philosophy (better to over-flag than under-flag for a triage tool), and
  V4 keeps that stance.

## What this means in practice

Treat every result from this app — emergency or not — the way you would
treat a first pass, not a verdict. If something feels seriously wrong and
this tool says otherwise, **trust yourself and your symptoms, not the
tool**, and seek care or call emergency services anyway.

If you are extending this project: a broader phrase vocabulary, a small
classifier trained on labeled symptom-severity data, or a second opinion
from an LLM prompted specifically to look for missed red flags (with its
output still unable to downgrade a rule-based match) would all be
reasonable next steps that don't require abandoning the deterministic core.
