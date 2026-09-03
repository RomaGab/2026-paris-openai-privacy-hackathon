# Product Plan: Minimum Viable Data + Necessity Certificate

## Product promise

**AI needs context, not identity.**

Minimum Viable Data helps a team design the minimum-data architecture for an AI feature. Necessity Certificate then measures whether the AI task still works with the proposed minimum context and records the resulting evidence.

```text
Privacy Preflight
→ minimum-data design
→ measured minimum-context evaluation
→ reviewed context contract
→ enforced payload
→ Necessity Certificate report
```

## Who the product serves

| User | Starting point | Outcome |
|---|---|---|
| Startup builder | A new product or AI feature | A privacy-by-design architecture before the first production data flow exists. |
| Team migrating an existing AI feature | A current prompt, data schema, and expected task outcome | A measured migration from an over-broad payload to a minimal, purpose-specific context. |

The product never requires production customer data for its demonstration. The workflow uses a declared schema and synthetic, labelled test cases unless an organisation has separately approved another evaluation dataset.

## Privacy Preflight principles

The first screen follows the Minimum Viable Data principles:

1. **No data without a feature.** Every input must name the feature or task it enables.
2. **No retention without a reason.** Data kept outside the AI call needs a separate, declared operational purpose.
3. **No permission beyond the task.** The AI receives only the minimum context approved for its current task.

These principles make privacy by design concrete before the model is called.

## One workflow, two entry modes

### Mode 1: Build a new AI feature

1. Describe the product, intended user, and AI task.
2. Define the decision or output to evaluate.
3. Map the candidate fields and their purpose.
4. Propose the minimum context contract before implementation.
5. Create synthetic, labelled cases and measure the proposed context.

### Mode 2: Migrate an existing AI feature

1. State the current task, prompt version, model, and expected output.
2. List the fields currently sent to the model. A schema is sufficient. Do not paste production personal data into the wizard.
3. Identify each field as `retain`, `block`, `generalise`, or `derive_locally`.
4. Compare the current full payload with the minimum-context payload on the declared test set.
5. Review and adopt the resulting contract before changing the production integration.

## Wizard screens

| Screen | User action | Output |
|---|---|---|
| 1. Privacy Preflight | Describe a new feature or current workflow. | Declared purpose and entry mode. |
| 2. Data Map | List fields, source, sensitivity, feature purpose, and current destination. | Structured data map. |
| 3. Minimum Context | Review proposed actions: retain, block, generalise, derive locally. | Draft context contract. |
| 4. Benchmark | Run the full and minimal payloads against the same declared corpus. | Measured comparison. |
| 5. Certificate | Review the contract, evidence, limits, and implementation action. | Exportable Necessity Certificate. |

## Structured skill contract

The skill is a recommender and report generator. It does not autonomously authorise a data flow. A person reviews and accepts the final context contract.

```json
{
  "mode": "new_or_migrate",
  "declared_purpose": "prioritise a billing request",
  "expected_action": "billing_priority",
  "fields": [
    {
      "source": "account_id",
      "privacy_cost": "direct_identifier",
      "feature_purpose": "look up account context",
      "action": "derive_locally",
      "minimal_fact": "subscription_plan",
      "reason": "the model needs plan context, not a raw identifier"
    }
  ]
}
```

The benchmark service enriches this contract with observed results. The report generator must keep design recommendations separate from measured evidence.

## Benchmark integrity

The central proof is a real comparison of two executions of the same task:

| Measure | Required evidence |
|---|---|
| Task quality | Exact match against declared labels, plus agreement between full and minimum-context outputs. |
| Context reduction | Raw fields withheld, transformed, and retained. |
| Token reduction | Actual input-token count for the exact model and payload used. |
| Reproducibility | Corpus version, prompt, model, run time, and configuration. |

A field may be recommended for blocking only when its removal or transformation causes **zero decision changes** on the declared corpus, unless the report explicitly records a review exception. Aggregate accuracy alone is insufficient because predictions can change while the aggregate score stays flat.

All displayed benchmark numbers must come from an executed run. Synthetic data is acceptable when it is labelled as synthetic. If a run used a deterministic offline fallback, it is a technical dry run, not evidence about an LLM's data needs.

## Report contents

The Necessity Certificate contains:

1. Declared purpose and expected outcome.
2. Data map with a purpose for every retained field.
3. Proposed actions: retain, block, generalise, or derive locally.
4. Full-context versus minimum-context benchmark results.
5. Model, prompt, corpus, and run metadata.
6. Enforced payload schema and implementation next step.
7. Limits: corpus-specific, prompt-specific, model-specific, and not a legal conclusion.

## Existing POC and scope

| Component | Role in the product | Claim allowed in the demo |
|---|---|---|
| `poc/minimize.py` | Core full-payload versus ablated-payload benchmark. | Measured quality and token results only from a real model run. |
| `poc/sql_minimize.py` | Generates a proposed SQL view and storage-design artifact from the context contract. | A generated design artifact, not proof of a deployed database control until executed against a real database. |
| `poc/leakage_simulation.py` | Explores assumed supplier-leak scenarios. | Do not show its simulated risk values as measured evidence or as a claim that the project would have prevented a breach. |

The minimum viable submission is the wizard, one real benchmark run, and one Necessity Certificate. SQL generation and any risk scenario remain enhancers after that proof works.

## Team interfaces and stop criteria

| Workstream | Delivers | Stop criterion |
|---|---|---|
| Founder interview | One anonymous qualitative finding about adoption friction, with consent if attributable. | A single verified sentence for the pitch. It does not change the product scope. |
| Minimum Viable Data frontend | The five-screen wizard and a structured contract export. | A user can reach the Certificate screen with synthetic input. |
| Skill and report | Contract recommendation, reasons, limits, and report rendering. | Output is structured and does not invent measurements. |
| Benchmark engine | Full versus minimum-context run and saved run metadata. | One repeatable real-model result is available. |

## Scope gate

Do not add new subsystems after the first working benchmark. Finish the report, capture the first working demo, and rehearse the story:

> Existing tools find sensitive data. Minimum Viable Data designs the minimum context. Necessity Certificate proves that the AI still works with it.
