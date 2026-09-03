# Necessity Certificate

## One-line pitch

**We do not just remove data before an AI call. We make every removed field carry its own evidence of why the declared task did not need it.**

## Problem

**How do we ensure privacy by design in AI systems, rather than bolt it on after the fact?**

Privacy by design means minimizing data use before processing, not filtering it afterwards. In practice, most AI systems fail this test: they are commonly given whole records — a support ticket, application, or customer profile — that can contain direct identifiers and sensitive context irrelevant to the requested decision.

Most privacy tooling answers an important but different question: **what looks personal?** It detects, masks, pseudonymises, or redacts personal data after collection, once it has already reached the system boundary. This is privacy by reaction, not privacy by design.

The question we need to answer instead, upfront and by construction, is: **does this specific AI task need this field at all?**

## Solution

For a declared purpose, such as routing a support ticket, the system tests every input field counterfactually:

1. Run the task with the complete record.
2. Remove one field and run the identical task again.
3. Measure whether the expected decision changes on a declared test set.
4. Block fields whose removal does not degrade the measured task outcome.
5. Generate an auditable evidence card for every retained or removed field.

The result is a Necessity Certificate: a system that does not merely say, "we removed email," but attaches the observed evidence for doing so.

## Evidence card

```text
Field: email
Declared purpose: route a support ticket
Privacy cost: direct identifier
Counterfactual test: removed in [N] declared synthetic cases
Observed effect: [K] routing decisions changed
Operational action: block before the model call
```

## How it differs from PII filtering

| PII filtering | Necessity Certificate |
|---|---|
| What data is personal? | Is this data necessary for the declared task? |
| Detect or mask data | Test necessity and block unnecessary data before the model call |
| A detection result | A reproducible minimization certificate |

These approaches are complementary. A PII detector can help identify a field's privacy cost. This project determines whether that field should cross the AI boundary at all.

## What we can prove

1. **Enforcement proof**: only approved fields are present in the outgoing model payload.
2. **Empirical necessity evidence**: on the declared test set, model, prompt, and task, omitting a field did or did not change the expected decision.
3. **Clear limits**: this is not a universal legal or mathematical proof. A different task, prompt, model version, or field interaction can change the result. The tool produces evidence for a DPIA or engineering review, not a legal verdict.

## Minimum viable demo

- **Purpose**: route a synthetic support ticket to an appropriate queue.
- **Fields**: issue description, product area, urgency, name, email, phone, date of birth, address, account ID.
- **Baseline**: run each complete record with one fixed prompt and model configuration.
- **Ablation**: remove one field at a time and repeat the same run.
- **Measures**: exact match against the expected queue and input tokens sent.
- **Output**: a before/after payload and evidence cards showing fields blocked or retained.

All displayed measurements are real and reproducible. The demonstration data is synthetic.

## Proof of concept

The `poc/` folder implements the minimum viable demo above end to end:

- `poc/data/synthetic_tickets.json` — 16 synthetic support tickets with the declared fields and an expected queue.
- `poc/classifier.py` — the routing task. Uses the OpenAI API when `OPENAI_API_KEY` is set, otherwise falls back to a deterministic offline classifier so the demo runs with no key.
- `poc/minimize.py` — runs the baseline, ablates each field one at a time, measures exact-match accuracy and tokens sent, and prints/saves an evidence card per field.

Run it:

```bash
pip install -r poc/requirements.txt   # optional if you only use the offline fallback
python poc/minimize.py
```

This prints one evidence card per field and writes the full report, including a before/after payload, to `poc/report.json`.

## Market landscape

The project builds on established detection, governance, policy, and evaluation techniques. Its differentiated contribution is connecting a declared purpose, counterfactual task measurement, an enforced minimal payload, and a reproducible evidence certificate. See [MARKET_STUDY.md](MARKET_STUDY.md).

## Pitch

> Existing tools find sensitive data. We turn task evidence into an enforced minimal AI payload.

> Build AI that needs less, and show the evidence for every field it leaves behind.
