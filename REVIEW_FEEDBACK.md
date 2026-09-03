# Critical Review Feedback

*Review snapshot: 3 September 2026. This document separates implemented behavior from claims that still require evidence.*

## Outcome

The strongest minimum viable submission is one complete and reproducible path:

```text
Minimum Viable Data wizard
→ declared purpose and data map
→ one real ablation or transformation benchmark
→ enforced minimal payload
→ Necessity Certificate
```

Do not add another privacy technique until this path is executable, measured, recorded, and easy to explain.

## Priority feedback

### P0: Use decision stability as the necessity rule

The current benchmark retains a field only when removing it lowers aggregate accuracy. Aggregate accuracy can remain unchanged even when individual predictions change.

A field may be recommended for blocking only when its removal or transformation causes **zero decision changes** on the declared corpus. Any exception must be explicit and reviewed.

**Done when:** the action shown on every evidence card is derived from `changed == 0`, with a test covering the case where predictions change but aggregate accuracy does not.

### P0: Produce one reproducible real-model run

The deterministic fallback is useful for checking the plumbing, but it is programmed to ignore the identifier fields. It cannot demonstrate what an LLM needs.

The benchmark report must save:

- model and model version where available;
- complete prompt or prompt hash;
- corpus version and synthetic-data disclosure;
- full-context and minimum-context predictions;
- exact input payloads and token counts;
- run timestamp and configuration.

**Done when:** another teammate can rerun the same command and inspect the saved evidence without relying on console output.

### P0: Connect the wizard to the benchmark

The product promise depends on one continuous user journey. The current repository contains the POC scripts but does not yet contain the Minimum Viable Data frontend or the skill.

The wizard should export one structured contract, invoke the benchmark, and render the resulting certificate. Avoid separate demos that require verbal explanation to connect them.

**Done when:** a user can start from the Privacy Preflight screen and reach a populated Necessity Certificate without manually editing an intermediate file.

### P0: Align the public promise with implemented transformations

The product plan proposes four actions: `retain`, `block`, `generalise`, and `derive_locally`. The current ablation POC only removes fields.

Implement one visible non-trivial transformation, for example:

```text
account_id → subscription_plan
```

The raw identifier remains local. Only the less identifying, task-relevant fact enters the model payload.

**Done when:** the before and after payloads visibly show one derived fact and the benchmark measures the resulting task outcome.

### P0: Generate the actual report artifact

The jury-facing artifact should be an HTML or Markdown report, not only terminal output or JSON.

It must contain:

1. declared purpose;
2. data map and field actions;
3. full versus minimum-context results;
4. raw personal fields withheld;
5. token reduction;
6. prompt, model, corpus, and run metadata;
7. explicit limitations;
8. the enforced minimal payload schema.

**Done when:** the report opens directly from the final wizard screen and every displayed number can be traced to the saved run.

## Claims to remove from the main demo

### Supplier leakage simulation

`poc/leakage_simulation.py` uses assumed leak, breach, key-compromise, and residual-risk probabilities. Its output is scenario analysis, not a measured result.

Do not display its probabilities as evidence, and do not imply that the product would have prevented a real breach. It can remain a clearly labelled future-risk modelling experiment.

### Differential privacy

`poc/sql_minimize.py` currently generates SQL and describes potential transforms. It does not yet execute or validate a differential-privacy mechanism.

Describe this output as a proposed SQL minimization and storage design. Do not claim differential privacy unless noise calibration, privacy accounting, and the resulting utility impact are implemented and measured.

### Universal or legal proof

The certificate provides purpose-specific empirical evidence and a deterministic payload-enforcement check. It does not prove that a field will never matter, and it is not a legal compliance verdict.

## Scope gate

The minimum viable submission is complete only when all five P0 items above are demonstrated. After that point, spend remaining time on:

1. recording the first working run;
2. inserting one consented or anonymous founder interview finding;
3. simplifying the pitch;
4. rehearsing the live flow and fallback video.

Do not spend the remaining build window on new cryptography, formal verification, leakage probability models, broad market research, or additional use cases.

## Final pitch test

Someone from another breakout room should be able to repeat this sentence after seeing the demo once:

> Minimum Viable Data designs the smallest context. Necessity Certificate measures that the AI still works and proves which payload was actually sent.
