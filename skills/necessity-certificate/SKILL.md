---
name: necessity-certificate
description: Turn a declared AI use case + a database schema into a minimized, purpose-specific database (an AI-facing view, a securely-transformed base table) with a per-field justification (Necessity Certificate). Use when a user asks to minimize a database for an AI/LLM use case, wants to know which columns an AI task really needs, or asks for a data-minimization / privacy-by-design pass over a schema.
---

# Necessity Certificate

## Overview

Given (1) a declared purpose ("what will the AI decide?") and (2) a real database schema + a labeled dataset, this
skill produces:

- a **per-column justification** ("evidence card"): why a field is kept, transformed, or dropped, backed by a
  measured counterfactual test, not a guess;
- a **minimized AI-facing SQL view**: only columns *proven* necessary for the task, and already safe to expose,
  are selected — anything untested is blocked by default (fail-closed);
- a **secure base-table DDL**: columns kept only for a secondary, declared, non-AI purpose (e.g. human agent
  lookup) are stored transformed (encrypted / generalized / DP-noised), never in plaintext.

This generalizes the proof of concept in `poc/minimize.py` + `poc/sql_minimize.py` (see `README.md` at the repo
root for the underlying "Necessity Certificate" methodology) to **any** use case and schema, not just the
ticket-routing demo.

Core idea: privacy by design means testing what a task needs *before* the model call, not filtering the output
after the fact. A field is only allowed to cross the AI boundary if removing it was empirically shown to change
the task's outcome, on a declared test set.

## When to use this skill

- The user gives you a use case (e.g. "route a support ticket", "decide loan pre-approval", "summarize a patient
  visit for a scheduling assistant") plus a database/table (schema, or schema + sample/labeled rows), and wants a
  minimized version of that database for the AI system.
- The user asks "which columns does this AI feature actually need?" or "give me a justification for every field
  we send to the model."

## Required inputs

Before running the workflow, make sure you have (ask the user if missing):

1. **Declared purpose**: one sentence describing the task and its expected output (e.g. "decide which support
   queue a ticket belongs to").
2. **Schema**: a single `CREATE TABLE` DDL for the table in question.
3. **A labeled dataset**: a JSON array of records for that table, each including the column holding the
   expected/ground-truth decision (the label field). Without ground truth, the ablation test has nothing to
   measure against — if the user has no labeled data, either help them label a small representative sample first,
   or clearly flag the resulting certificate as unverified/dry-run only.
4. Optional: the finite set of possible decision values (`--label-values`), if the task is a classification.
5. Optional: known privacy-cost overrides per column (e.g. a column named `ext_ref` is actually a direct
   identifier, or a column named `region` is actually not personal) and any secondary (non-AI) purpose that
   justifies keeping a blocked column in storage.

## Workflow

1. **Inspect the schema and a few sample rows.** Note the primary key column (assumed to be the first declared
   column, matching this repo's convention) and every other column.
2. **Classify each column's privacy cost.** The script applies a name-based heuristic (`direct identifier`,
   `quasi-identifier`, `sensitive numeric`, or `task-relevant, not personal`). Review its guesses against the
   actual column semantics and supply a `--privacy-cost-overrides` JSON file for anything it got wrong — this is
   the human-review step the methodology requires, do not skip it.
3. **Run the counterfactual test** with `scripts/necessity_certificate.py` (see Usage below): it runs the
   declared task on the full record for every labeled row (baseline), then removes each column one at a time and
   reruns the identical task, measuring whether the expected decision changes.
   - If `OPENAI_API_KEY` is set, the task is executed by an actual LLM call built from the declared purpose and
     the row's remaining fields — this produces genuine evidence.
   - Without a key, the script falls back to an offline majority-class baseline. This is only a smoke test of the
     pipeline; say so explicitly if you have to use it, and prefer asking the user for a key or running with one
     if real evidence is needed.
4. **Review the resulting field disposition** with the user:
   - *Blocked*: removing the field never changed the decision — never send it to the model.
   - *Retained, no transform needed*: field is necessary and not personal — safe to expose as-is.
   - *Retained, transform pending*: field is necessary but personal (quasi-identifier / direct identifier /
     sensitive numeric) — must be pseudonymized, generalized, or DP-noised before it may reach the AI view; the
     script flags this rather than silently exposing it.
   - *Blocked but operationally retained*: not needed by the AI task, but kept in storage (encrypted/generalized)
     for a separately declared purpose (e.g. human agent lookup) — supply this via `--secondary-retention`.
5. **Deliver the artifacts**: the minimized SQL (view + secure base table), the JSON evidence report, and the
   rendered Necessity Certificate markdown (per-field justification + limits section). Point out any column the
   test never covered — those are fail-closed (blocked) by construction, and should be flagged to the user rather
   than silently dropped without mention.

## Usage

```bash
python skills/necessity-certificate/scripts/necessity_certificate.py \
    --purpose "route a support ticket to the right queue" \
    --schema path/to/schema.sql \
    --data path/to/labeled_records.json \
    --label-field expected_queue \
    --label-values billing,account_security,shipping_logistics,technical_support,general_inquiry \
    --privacy-cost-overrides path/to/privacy_overrides.json \
    --secondary-retention path/to/secondary_retention.json \
    --model gpt-4o-mini \
    --out-dir out/
```

Set `OPENAI_API_KEY` in the environment to get a real counterfactual test; omit it only for a dry-run smoke test
of the pipeline.

Outputs, written to `--out-dir`:

- `evidence_cards.json` — full machine-readable report (baseline accuracy, per-field evidence, retained/blocked
  lists, an example before/after payload).
- `minimized_schema.sql` — the AI-facing view (`<table>_ai_view`) and the secure base table
  (`<table>_secure`).
- `necessity_certificate.md` — human-readable evidence cards + column disposition table + limits section, ready
  to hand to a reviewer or attach to a DPIA.

### Try it on the existing demo data

The repo already ships a labeled dataset you can run this against immediately:

```bash
python skills/necessity-certificate/scripts/necessity_certificate.py \
    --purpose "route a support ticket to the right queue" \
    --schema poc/data/tickets_schema.sql \
    --data poc/data/synthetic_tickets.json \
    --label-field expected_queue \
    --label-values billing,account_security,shipping_logistics,technical_support,general_inquiry \
    --out-dir out/tickets_demo/
```

## Notes / limits

- This produces **empirical evidence for the declared purpose, model, prompt, and test set used** — not a
  universal legal or mathematical proof. A different task, prompt, model version, or field interaction can change
  the result. Present it as input to a DPIA or engineering review, never as a legal verdict.
- The column privacy-cost heuristic is name-based and imperfect (e.g. a column literally named `id` won't match
  `account_id`-style patterns). Always let a human review and override it before trusting the output.
- A column present in the schema but absent from every record in `--data`, or never meaningfully varied across
  the test set, cannot produce a reliable ablation signal — call this out rather than presenting it as settled.
- Fail-closed by design: any column not proven necessary is blocked, and any personal column proven necessary is
  blocked from the AI view until its required transform (pseudonymize/generalize/dp_noise) is actually
  implemented — the script marks this rather than silently exposing raw personal data.

## Resources

- `scripts/necessity_certificate.py`: the generalized counterfactual-minimization + SQL-generation pipeline
  described above.
- `poc/minimize.py`, `poc/sql_minimize.py`, `poc/classifier.py`: the original fixed-schema demo this skill
  generalizes; useful as a reference for the exact methodology and evidence-card format.
- Root `README.md` / `MARKET_STUDY.md`: the "Necessity Certificate" product framing and evidence-card template
  this skill's output follows.
