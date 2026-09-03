# Market Study: Task-Specific Data Minimization for AI

*Research snapshot: 3 September 2026. This is a product landscape, not a patent, freedom-to-operate, or legal opinion.*

## Executive takeaway

The component technologies already exist. The defensible contribution of **Necessity Certificate** is their connection at the AI input boundary:

```text
declared purpose
→ counterfactual task measurement
→ reviewed context contract
→ enforced minimal payload of facts
→ reproducible evidence certificate
```

We should not claim to have invented data minimization, PII detection, policy engines, feature ablation, or formal proof. We can claim a concrete and testable way to turn task evidence into an enforced minimum payload of purpose-specific facts for an AI call.

## Existing solutions

| Segment | Representative solutions | What they do | Gap addressed by this project |
|---|---|---|---|
| PII detection and redaction | [OpenAI Privacy Filter](https://huggingface.co/openai/privacy-filter), [Microsoft Presidio](https://microsoft.github.io/presidio/), [Google Sensitive Data Protection](https://docs.cloud.google.com/sensitive-data-protection/docs/deidentify-sensitive-data) | Identify PII and mask, replace, redact, encrypt, or otherwise de-identify it. | They do not measure whether a field is needed for one declared AI task. |
| Sensitive-data discovery and governance | [Amazon Macie](https://docs.aws.amazon.com/macie/latest/user/discovery-asdd-how-it-works.html), [BigID](https://bigid.com/discovery-classification/), [OneTrust](https://www.onetrust.com/products/) | Discover, classify, map, govern, retain, delete, and remediate data across enterprise systems. | Their main unit of work is the data estate and its governance workflow, not a measured field-level decision before one model call. |
| Policy as code | [Open Policy Agent](https://www.openpolicyagent.org/docs/policy-language) | Evaluate declarative policies on structured data and enforce allow or deny decisions. | A policy engine enforces a policy written by a person. It does not itself generate task-utility evidence for an allowlist. |
| Data science and model evaluation | Feature ablation, feature selection, counterfactual evaluation | Test how model outcomes change when features are removed or changed. | These methods usually optimise model performance. They do not turn the result into a privacy control and an auditable request-level certificate. |

## Where we are original

The original product proposition is not any individual box in the diagram. It is the closed loop:

1. A person declares a purpose and its expected output.
2. The system measures which fields affect that output on a declared corpus.
3. A reviewer accepts the resulting field allowlist.
4. A gateway ensures the model receives only that context contract, including derived or generalised facts where appropriate.
5. The product emits the evidence, configuration, and payload summary needed to reproduce the decision.

This produces a useful distinction:

> Existing tools find sensitive data. Necessity Certificate turns task evidence into an enforced minimal AI context.

The certificate is useful because it links a removal decision to a purpose, a test design, actual observed results, and the operational control that acted on the decision.

## What we must not claim

- Not the first system to minimise data.
- Not a replacement for PII detection, data-discovery platforms, DPIAs, or legal review.
- Not a universal proof that a field will never matter.
- Not a cryptographic proof or a zero-knowledge proof.
- Not an automatic authority to remove data: a responsible person approves the purpose and the final policy.

The terms "proof-carrying data" and "proof-carrying code" already have formal and cryptographic meanings. The public product name should therefore be **Necessity Certificate**, with the precise claim **measured, reproducible, purpose-specific evidence**.

## What the certificate proves

| Claim | Evidence | Strength |
|---|---|---|
| Only approved fields reached the model endpoint. | Logged payload schema checked against the allowlist. | Deterministic enforcement proof. |
| A removed field did not change measured task quality. | Baseline and ablation runs on the declared corpus, with model and prompt recorded. | Empirical evidence, bounded to the test conditions. |
| The removal advances minimisation. | Field classification and data-flow summary, reviewed against the stated purpose. | Decision-support evidence, not a legal conclusion. |

## Competitive messages

If a comparable product already detects PII:

> Detecting a field is personal does not answer whether the model needs it. We test that question for a declared task and block the field before the call.

If a comparable product already applies a policy:

> Policies are necessary. We add measured task evidence to support the choice of policy and a certificate showing that the policy was enforced.

If a comparable product already has a governance dashboard:

> Governance dashboards describe the estate. We show a compact, replayable decision at the point where data crosses into an AI model.

## Demonstration implication

The demo should show a single use case end to end. A synthetic B2B SaaS support-action task is sufficient:

1. Show the full record and the declared next-action purpose.
2. Run the baseline.
3. Remove, generalise, or derive fields one at a time, and measure the expected action.
4. Review the recommended context contract, including any locally derived fact.
5. Show the gateway forwarding only the approved minimal payload of facts.
6. Open the resulting Necessity Certificate.

Every displayed number must come from the run shown or an explicitly identified prior run. The synthetic nature of the dataset and the limits of the result must be stated clearly.

The benchmark should not attempt to outperform PII detectors on their own detection metric. Instead, it should compare four task conditions: full context, masking only, minimum context, and minimum context plus masking. The comparison between minimum context and full context measures our distinctive contribution. The comparison between minimum context plus masking and masking alone demonstrates a reusable layered architecture. See [BENCHMARK.md](BENCHMARK.md).
