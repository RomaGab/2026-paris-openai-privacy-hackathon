# Necessity Certificate

## One-line pitch

**AI needs context, not identity. We turn a raw customer record into the smallest purpose-specific facts an AI task needs, with evidence for every omission or transformation.**

## Problem

**How do we ensure privacy by design in AI systems, rather than bolt it on after the fact?**

Privacy by design means minimizing data use before processing, not filtering it afterwards. In practice, most AI systems fail this test: they are commonly given whole records, such as a support ticket, application, or customer profile, that can contain direct identifiers and sensitive context irrelevant to the requested decision.

PII tooling answers an important but different question: **what looks personal?** It can detect and mask personal data before an external model call. Detection is a useful component, but it does not establish whether a task needs the data, whether a less identifying fact would suffice, or whether the reduced payload preserves task quality.

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

## Why this is more than OpenAI Privacy Filter

[OpenAI Privacy Filter](https://huggingface.co/openai/privacy-filter) is a local PII detection and masking model. It identifies sensitive spans such as names, email addresses, phone numbers, addresses, account numbers, dates, URLs, and secrets. It does not know the declared business purpose of an AI call or test which context preserves the task outcome.

| Question | OpenAI Privacy Filter | Minimum Viable Data + Necessity Certificate |
|---|---|---|
| What is the input? | Text to inspect for PII spans. | A declared AI purpose, data schema, expected outcome, and test corpus. |
| What decision is made? | Which spans match the privacy-label taxonomy. | Which inputs to retain, block, generalise, or replace with locally derived facts. |
| Is task utility measured? | No. | Yes: full context and minimum context run against the same expected outcomes. |
| Is the result enforced? | Detected spans can be masked. | A reviewed context contract controls the complete payload sent to the model. |
| What artifact is produced? | Detected or masked spans. | A reproducible certificate containing purpose, field actions, benchmark evidence, payload, and limitations. |

Concrete example:

```text
Raw system record:
  account_id = ACC-123
  email = alice@example.com
  subscription_plan = Pro
  invoice_status = overdue

OpenAI Privacy Filter:
  detects or masks account_id and email

Minimum Viable Data + Necessity Certificate:
  declared purpose = prioritise a billing request
  derives locally = subscription_plan, invoice_status
  sends to model = subscription_plan, invoice_status, issue description
  blocks from model = account_id, email, name, address
  measures = whether the expected billing decision stays unchanged
  records = the benchmark and exact minimal payload
```

OPF can remain an optional first-layer detector for PII embedded in free text. Our differentiated layer starts after detection: **purpose-specific context design, measured utility preservation, payload enforcement, and evidence generation.**

If the demo only highlights masking an email address, it will look like a PII-filter demo. The distinctive moment is showing a raw identifier replaced by a useful fact, the task outcome remaining stable, and the resulting context contract being enforced.

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

The `poc/` folder implements two complementary measurement paths using synthetic ticket routing:

- `poc/data/synthetic_tickets.json`: 16 synthetic support tickets with the declared fields and an expected queue.
- `poc/classifier.py`: the routing task. Uses the OpenAI API when `OPENAI_API_KEY` is set, otherwise falls back to a deterministic offline classifier so the demo runs with no key.
- `poc/minimize.py`: runs per-field counterfactual ablations. A field is recommended for blocking only when its removal causes zero individual decision changes.
- `poc/benchmark.py`: compares full context, masking alone, minimum context, and minimum context plus masking. It exports exact observations, utility scores, data-reduction measures, and limitations to JSON and Markdown.

Run the dependency-free technical dry run:

```bash
python poc/benchmark.py --engine offline --masker structured
```

Run the real-model benchmark after setting `OPENAI_API_KEY` outside the repository:

```bash
pip install -r poc/requirements.txt
python poc/benchmark.py --engine openai --model gpt-4o-mini --masker structured
```

The default structured masker is a comparison baseline, not OpenAI Privacy Filter. An optional adapter runs the actual Privacy Filter model:

```bash
pip install -r poc/requirements-opf.txt
python poc/benchmark.py --engine openai --model gpt-4o-mini --masker opf
```

The first OPF execution may download model weights, so cache them before a live demo. See [BENCHMARK.md](BENCHMARK.md) for the experimental design, formulas, acceptance rule, report schema, and claim boundaries. See [BENCHMARK_RESULTS.md](BENCHMARK_RESULTS.md) for the first recorded real-model iterations, including one rejected candidate contract and one accepted prototype contract.

The per-field ablation remains available:

```bash
python poc/minimize.py
```

### Optional architecture artifact: SQL minimization design

`poc/sql_minimize.py` takes the necessity evidence from `minimize.py` and a real SQL table definition (`poc/data/tickets_schema.sql`) and emits:

- an AI-facing `CREATE VIEW` containing only the columns proven necessary for the declared task (any column never covered by the necessity test is blocked by default, fail-closed);
- a base-table DDL where every PII column kept only for a secondary, declared operational purpose (e.g. agent lookup) is stored encrypted at rest via pgcrypto, or generalized (date of birth to age band), never in plaintext or raw form.

The generated SQL is a proposed architecture artifact. It is not evidence of a deployed database control, differential privacy mechanism, or privacy accounting implementation.

```bash
python poc/sql_minimize.py
```

### Optional scenario artifact: supplier data-leakage simulation

`poc/leakage_simulation.py` runs a Monte Carlo simulation, over `poc/data/suppliers.json`, of what happens when suppliers who receive the Step A output actually leak data: 10,000 events, thousands of repetitions, two threat models (independent per-event leaks vs. one correlated breach exposing a whole batch), each compared with and without Step A minimization. Output is a probability of at least one real PII exposure, the expected number of exposed events, and a pass/fail verdict against a configurable risk threshold.

These probabilities come from declared assumptions, not observed incidents. They must not be presented as measured product impact.

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
