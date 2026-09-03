# Recorded Benchmark Results

## Status

These are real API measurements on 16 declared synthetic support tickets. They are evidence for this prototype configuration only.

- Engine: OpenAI API
- Model: `gpt-4o-mini`
- Temperature: `0`
- Token source: API-reported input usage
- Masker: deterministic structured-field baseline
- OPF status: not used in these runs
- Corpus SHA-256: `21790fd5fd7c2b6da8b0f1c8e8181bdd34877d2281b2124c76125afde0b9f8d1`
- Prompt SHA-256: `ce132f54914817b82aba24197101ed9cf1b35c8b629c9c7edb68169abacda3a2`

## Iteration 1: rejected minimum contract

Recorded at `2026-09-03T14:03:36.595837+00:00`.

The candidate minimum payload contained `issue_description` and `product_area`.

| Variant | Correct | Changes vs full | Input tokens | Token reduction | Field reduction | Raw structured PII sent |
|---|---:|---:|---:|---:|---:|---:|
| Full context | 15/16 | 0 | 2,383 | 0.0% | 0.0% | 96 |
| Masking only | 15/16 | 0 | 2,272 | 4.7% | 0.0% | 0 |
| Candidate minimum | 14/16 | 1 | 1,232 | 48.3% | 77.8% | 0 |
| Candidate minimum + masking | 14/16 | 1 | 1,232 | 48.3% | 77.8% | 0 |

The changed case was `T007`: the full-context run returned `technical_support`, while the candidate minimum-context run returned `general_inquiry`. The certificate therefore marked the candidate for review instead of approving it.

## Iteration 2: accepted prototype contract

Recorded at `2026-09-03T14:05:25.236758+00:00`.

The revised minimum payload retained the three task fields: `issue_description`, `product_area`, and `urgency`.

| Variant | Correct | Accuracy | Changes vs full | Input tokens | Token reduction | Field reduction | Raw structured PII sent | Raw PII reduction |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Full context | 15/16 | 93.8% | 0 | 2,383 | 0.0% | 0.0% | 96 | 0.0% |
| Masking only | 15/16 | 93.8% | 0 | 2,272 | 4.7% | 0.0% | 0 | 100.0% |
| Minimum context | 15/16 | 93.8% | 0 | 1,312 | 44.9% | 66.7% | 0 | 100.0% |
| Minimum + masking | 15/16 | 93.8% | 0 | 1,312 | 44.9% | 66.7% | 0 | 100.0% |

On this run, the revised minimum context preserved all 15 correct decisions and produced zero decision changes compared with full context. It reduced API-reported input tokens by 44.9%, reduced field instances by 66.7%, and withheld all 96 raw structured PII values present in the full-context payloads.

The matching values for `minimum context` and `minimum + masking` are expected in this synthetic corpus: after structured PII fields are removed, the remaining task text contains no declared PII for the structured baseline to mask.

## What this result demonstrates

1. The certificate can reject an over-aggressive minimum contract instead of automatically approving every reduction.
2. Purpose-specific minimization produced substantially more token reduction than masking alone in the accepted run: 44.9% versus 4.7%.
3. Masking and minimization remain separate layers. These measurements do not evaluate OPF detection quality.

## Limitations

- The corpus is small and synthetic.
- The same engineering corpus was used to revise and evaluate the allowlist. It is not a held-out validation set.
- A single model execution per condition does not measure run-to-run variability.
- The full-context reference itself scored 15/16, so the benchmark demonstrates preservation relative to that reference, not perfect task performance.
- The causal role of `urgency` is not established by the second run alone. The complete revised condition passed; repeated ablations would be needed to isolate causality under model nondeterminism.
- The result is specific to the recorded corpus, prompt, model, and run. It is not a universal or legal proof.

## Reproduce

```bash
pip install -r poc/requirements.txt
export OPENAI_API_KEY="your-key"
python poc/benchmark.py --engine openai --model gpt-4o-mini --masker structured
```

The generated JSON contains each exact payload, prompt, prediction, expected label, and token count. Generated reports remain ignored by Git to avoid accidentally committing future evaluation records.

