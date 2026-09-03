# Necessity Certificate Benchmark Report

> **REAL MODEL RUN:** Metrics below were recorded from the declared API execution.

> The masking condition is a structured-field baseline. It is not an OpenAI Privacy Filter evaluation.

## Run metadata

- Generated: `2026-09-03T14:05:25.236758+00:00`
- Engine: `openai:gpt-4o-mini`
- Model: `gpt-4o-mini`
- Masker: `structured_field_masking`
- Synthetic cases: `16`
- Corpus SHA-256: `21790fd5fd7c2b6da8b0f1c8e8181bdd34877d2281b2124c76125afde0b9f8d1`
- Prompt SHA-256: `ce132f54914817b82aba24197101ed9cf1b35c8b629c9c7edb68169abacda3a2`

## Results

| Variant | Correct | Accuracy | Changes vs full | Input tokens | Token reduction | Field reduction | Raw structured PII sent | Raw PII reduction | Accepted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| Full context | 15/16 | 93.8% | 0 | 2383 | 0.0% | 0.0% | 96 | 0.0% | yes |
| Masking only | 15/16 | 93.8% | 0 | 2272 | 4.7% | 0.0% | 0 | 100.0% | yes |
| Minimum context | 15/16 | 93.8% | 0 | 1312 | 44.9% | 66.7% | 0 | 100.0% | yes |
| Minimum + masking | 15/16 | 93.8% | 0 | 1312 | 44.9% | 66.7% | 0 | 100.0% | yes |

## Interpretation

- `minimum_context` versus `full_context` measures the contribution of purpose-specific minimization.
- `minimum_plus_masking` versus `masking_only` measures the additional reduction from minimization when a masking layer is already present.
- A minimized condition is accepted without review only when it causes zero individual decision changes and does not reduce ground-truth correctness.

## Limitations

- The corpus is small, synthetic, and specific to support-ticket routing.
- Results are bounded to this corpus, prompt, model configuration, and run.
- No result is a legal conclusion or a universal proof that a field never matters.
- The masking condition uses declared structured fields and is not an OpenAI Privacy Filter evaluation.
