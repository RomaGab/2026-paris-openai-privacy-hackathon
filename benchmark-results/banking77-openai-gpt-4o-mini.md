# Necessity Certificate Benchmark Report

> **REAL MODEL RUN:** Metrics below were recorded from the declared API execution.

> The masking condition is a structured-field baseline. It is not an OpenAI Privacy Filter evaluation.

## Run metadata

- Generated: `2026-09-03T14:29:10.588874+00:00`
- Engine: `openai:gpt-4o-mini`
- Model: `gpt-4o-mini`
- Masker: `structured_field_masking`
- Evaluation cases: `50`
- Corpus: Fixed 50-case subset of the public BANKING77 test split
- Public source: https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/master/banking_data/test.csv
- Dataset license: `CC BY 4.0`
- Data provenance: Public queries and original labels with a synthetic structured identity overlay
- Corpus SHA-256: `8cb8af569addd647e01dc4fcddcfe4c6a09c1772a525a9f4b8dbd30feb7cf91e`
- Prompt SHA-256: `303a55251f47010a958836662b20b4c9a68929a6c653a0e29c753fe545905445`

## Results

| Variant | Correct | Accuracy | Changes vs full | Improvements | Regressions | Input tokens | Token reduction | Field reduction | Raw structured PII sent | Raw PII reduction | Accepted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| Full context | 44/50 | 88.0% | 0 | 0 | 0 | 9921 | 0.0% | 0.0% | 300 | 0.0% | yes |
| Masking only | 45/50 | 90.0% | 1 | 1 | 0 | 9371 | 5.5% | 0.0% | 0 | 100.0% | review |
| Minimum context | 45/50 | 90.0% | 1 | 1 | 0 | 5764 | 41.9% | 88.9% | 0 | 100.0% | review |
| Minimum + masking | 45/50 | 90.0% | 1 | 1 | 0 | 5764 | 41.9% | 88.9% | 0 | 100.0% | review |

## Interpretation

- `minimum_context` versus `full_context` measures the contribution of purpose-specific minimization.
- `minimum_plus_masking` versus `masking_only` measures the additional reduction from minimization when a masking layer is already present.
- A minimized condition is accepted without review only when it causes zero individual decision changes and does not reduce ground-truth correctness.
- Improvements and regressions distinguish beneficial decision changes from harmful ones; the strict no-change rule still routes every change to review.

## Limitations

- This is a fixed 50-case, 10-intent BANKING77-derived subset evaluation, not a full BANKING77 benchmark result.
- The support queries and intent labels come from BANKING77; all structured identity fields are synthetic overlays.
- The minimum-context allowlist was designed before this public holdout evaluation.
- BANKING77 is public, so possible model pretraining exposure is unknown; this run measures relative context effects, not uncontaminated generalization.
- Results are bounded to this corpus, prompt, model configuration, and run.
- No result is a legal conclusion or a universal proof that a field never matters.
- The masking condition uses declared structured fields and is not an OpenAI Privacy Filter evaluation.
