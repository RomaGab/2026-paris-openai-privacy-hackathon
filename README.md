# Proof-Carrying Data Minimization

## One-line pitch

**We do not just remove data before an AI call. We make every removed field carry its own evidence of why the declared task did not need it.**

## Problem

AI systems are commonly given whole records: a support ticket, application, or customer profile. These records can contain direct identifiers and sensitive context that are irrelevant to the requested decision.

Most privacy tooling answers an important question: **what looks personal?** It detects, masks, pseudonymises, or redacts personal data after collection.

The missing question is: **does this specific AI task need this field at all?**

## Solution

For a declared purpose, such as routing a support ticket, the system tests every input field counterfactually:

1. Run the task with the complete record.
2. Remove one field and run the identical task again.
3. Measure whether the expected decision changes on a declared test set.
4. Block fields whose removal does not degrade the measured task outcome.
5. Generate an auditable evidence card for every retained or removed field.

The result is proof-carrying data minimization: a system that does not merely say, "we removed email," but attaches the observed evidence for doing so.

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

| PII filtering | Proof-Carrying Data Minimization |
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

## Pitch

> Privacy tools can tell you what is personal. We prove what your AI does not need.

> Build AI that needs less, and show the evidence for every field it leaves behind.
