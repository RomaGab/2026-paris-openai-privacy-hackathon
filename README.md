# Necessity Certificate

## One-line pitch

**AI needs context, not identity. We turn a raw customer record into the smallest purpose-specific facts an AI task needs, with evidence for every omission or transformation.**

## Problem

**How do we ensure privacy by design in AI systems, rather than bolt it on after the fact?**

Privacy by design means minimizing data use before processing, not filtering it afterwards. In practice, most AI systems fail this test: they are commonly given whole records, such as a support ticket, application, or customer profile, that can contain direct identifiers and sensitive context irrelevant to the requested decision.

Most privacy tooling answers an important but different question: **what looks personal?** It detects, masks, pseudonymises, or redacts personal data after collection, once it has already reached the system boundary. This is privacy by reaction, not privacy by design.

The question we need to answer instead, upfront and by construction, is: **what is the smallest context this specific AI task needs?**

## Solution

For a declared purpose, such as taking the next support action, the system produces a purpose-specific minimum context:

1. Declare the request type and the expected outcome.
2. Run the task with the complete record.
3. Remove, generalise, or derive one input at a time and rerun the identical task.
4. Measure whether an expected decision changes on a declared test set.
5. Review the resulting allowlist of facts, then enforce it before the model call.
6. Generate an auditable evidence card for every retained, transformed, or blocked input.

The result is a Necessity Certificate: a system that does not merely say, "we removed an account ID," but records why the task received `plan = Pro` instead.

## Evidence card

```text
Source field: account_id
Declared purpose: prioritise a billing request
Privacy cost: direct identifier
Minimal context sent: subscription_plan = Pro
Counterfactual test: raw ID replaced in [N] declared synthetic cases
Observed effect: [K] expected decisions changed
Operational action: derive the plan locally; block the raw ID before the model call
```

## How it differs from PII filtering

| PII filtering | Necessity Certificate |
|---|---|
| What data is personal? | What minimal context is necessary for this declared task? |
| Detect or mask data | Test, generalise, derive, or block data before the model call |
| A detection result | A reproducible minimization certificate |

These approaches are complementary. A PII detector can identify a field's privacy cost, especially in free text. This project determines whether a raw field should cross the AI boundary at all, or whether a less identifying fact is sufficient.

## What we can prove

1. **Enforcement proof**: only approved fields are present in the outgoing model payload.
2. **Empirical necessity evidence**: on the declared test set, model, prompt, and task, omitting a field did or did not change the expected decision.
3. **Clear limits**: this is not a universal legal or mathematical proof. A different task, prompt, model version, or field interaction can change the result. The tool produces evidence for a DPIA or engineering review, not a legal verdict.

## Minimum viable demo

- **Purpose**: choose the next action for a synthetic B2B SaaS support request.
- **Request types**: billing dispute, delayed delivery, account-access issue.
- **Minimum context**: a billing request can receive `subscription_plan` and `invoice_status`; delivery can receive `delivery_status` and a country or region; account access can receive `failed_login_count` and `last_login_age`.
- **Raw inputs held back**: name, email, phone, date of birth, street address, and account ID. The raw ID may be used locally to derive an approved fact, but is never sent to the model.
- **Baseline**: run each complete record with one fixed prompt and model configuration.
- **Ablation and transformation**: remove or replace one input at a time and repeat the same run.
- **Measures**: exact match against the expected action, raw personal fields withheld, and input tokens sent.
- **Output**: a before/after payload and Necessity Certificates showing inputs retained, transformed, or blocked.

All displayed measurements are real and reproducible. The demonstration data is synthetic.

## Proof of concept

The `poc/` folder currently implements the first measurement harness, using synthetic ticket routing:

- `poc/data/synthetic_tickets.json`: 16 synthetic support tickets with the declared fields and an expected queue.
- `poc/classifier.py`: the routing task. Uses the OpenAI API when `OPENAI_API_KEY` is set, otherwise falls back to a deterministic offline classifier so the demo runs with no key.
- `poc/minimize.py`: runs the baseline, ablates each field one at a time, measures exact-match accuracy and tokens sent, and prints/saves an evidence card per field.

The next iteration replaces the simple raw-field removal scenario with the contextual use case above: purpose-specific facts are derived locally, reviewed, and enforced as the model payload.

Run it:

```bash
pip install -r poc/requirements.txt   # optional if you only use the offline fallback
python poc/minimize.py
```

This prints one evidence card per field and writes the full report, including a before/after payload, to `poc/report.json`.

### Step A -- differential-privacy-aware SQL minimization

`poc/sql_minimize.py` takes the necessity evidence from `minimize.py` and a real SQL table definition (`poc/data/tickets_schema.sql`) and emits:

- an AI-facing `CREATE VIEW` containing only the columns proven necessary for the declared task (any column never covered by the necessity test is blocked by default, fail-closed);
- a base-table DDL where every PII column kept only for a secondary, declared operational purpose (e.g. agent lookup) is stored encrypted at rest via pgcrypto, or generalized (date of birth to age band), never in plaintext or raw form.

Retained-but-sensitive columns additionally go through a DP-style check before they can reach the AI view: direct identifiers must be pseudonymized, quasi-identifiers generalized, sensitive numerics get calibrated Laplace noise. Non-personal task fields pass through unchanged.

```bash
python poc/sql_minimize.py
```

### Step B -- supplier data-leakage simulation

`poc/leakage_simulation.py` runs a Monte Carlo simulation, over `poc/data/suppliers.json`, of what happens when suppliers who receive the Step A output actually leak data: 10,000 events, thousands of repetitions, two threat models (independent per-event leaks vs. one correlated breach exposing a whole batch), each compared with and without Step A minimization. Output is a probability of at least one real PII exposure, the expected number of exposed events, and a pass/fail verdict against a configurable risk threshold.

```bash
python poc/leakage_simulation.py --events 10000 --threshold 0.01
```

## Market landscape

The project builds on established detection, governance, policy, and evaluation techniques. Its differentiated contribution is connecting a declared purpose, counterfactual task measurement, an enforced minimal payload, and a reproducible evidence certificate. See [MARKET_STUDY.md](MARKET_STUDY.md).

## Product plan and principles

[PRODUCT_PLAN.md](PRODUCT_PLAN.md) defines the two user journeys, Privacy Preflight principles, wizard screens, structured skill contract, benchmark requirements, report contents, and the scope gate for the minimum viable submission.

## Critical review

[REVIEW_FEEDBACK.md](REVIEW_FEEDBACK.md) records the P0 correctness gaps, claim boundaries, validation criteria, and final scope gate.

## Pitch

> Existing tools find sensitive data. We turn task evidence into an enforced minimal AI context.

> Build AI that needs less, and show the evidence for every field it leaves behind.
