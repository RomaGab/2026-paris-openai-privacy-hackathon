# Results Summary (slide-ready)

Snapshot written 3 September 2026, 17:15 local time. Every number below comes from an executed run recorded in [BENCHMARK_RESULTS.md](BENCHMARK_RESULTS.md) and [benchmark-results/summary.csv](benchmark-results/summary.csv). Model `gpt-4o-mini`, temperature 0, input tokens as reported by the OpenAI API. The masking condition is a deterministic structured-field baseline, not an OpenAI Privacy Filter evaluation.

## 1. Public data: fixed BANKING77-derived subset (run 2026-09-03 14:29 UTC)

50 public banking-support queries (10 intents, 5 each) from the BANKING77 test split (CC BY 4.0), original labels preserved, six synthetic structured identity fields overlaid on each record.

| Payload | Correct | Accuracy | Changes vs full | Input tokens | Token reduction | Fields sent | Field reduction | Raw identity values sent |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Full record | 44/50 | 88.0% | 0 | 9,921 | 0.0% | 450 | 0.0% | 300 |
| Masking only | 45/50 | 90.0% | 1 | 9,371 | 5.5% | 450 | 0.0% | 0 |
| Minimum context | 45/50 | 90.0% | 1 | 5,764 | 41.9% | 50 | 88.9% | 0 |
| Minimum + masking | 45/50 | 90.0% | 1 | 5,764 | 41.9% | 50 | 88.9% | 0 |

Headline: 41.9% fewer input tokens, 88.9% fewer fields, all 300 raw identity values withheld, exact-match accuracy from 88.0% to 90.0% (one full-context error corrected, zero regressions).

The single changed decision is `B77-0015` ("Can I freeze my card right now?"): full context answered `verify_my_identity`, every reduced condition answered the expected `compromised_card`. The strict certificate still routed the minimized payload to review: any changed decision, even an improvement, requires a human look.

## 2. Synthetic support corpus, accepted contract (run 2026-09-03 14:05 UTC)

16 declared synthetic support tickets, routing to one of five queues. Minimum payload: `issue_description`, `product_area`, `urgency`.

| Payload | Correct | Accuracy | Changes vs full | Input tokens | Token reduction | Fields sent | Field reduction | Raw PII values sent |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Full record | 15/16 | 93.8% | 0 | 2,383 | 0.0% | 144 | 0.0% | 96 |
| Masking only | 15/16 | 93.8% | 0 | 2,272 | 4.7% | 144 | 0.0% | 0 |
| Minimum context | 15/16 | 93.8% | 0 | 1,312 | 44.9% | 48 | 66.7% | 0 |
| Minimum + masking | 15/16 | 93.8% | 0 | 1,312 | 44.9% | 48 | 66.7% | 0 |

Headline: 44.9% fewer input tokens, 66.7% fewer fields, all 96 raw PII values withheld, zero decision changes. Accepted without review.

## 3. The certificate can say no (rejected contract, run 2026-09-03 14:03 UTC)

First candidate minimum (`issue_description` + `product_area` only): 14/16 correct, one decision changed (ticket `T007`: `technical_support` became `general_inquiry`). Rejected by the zero-change rule. Adding `urgency` restored 15/16 with zero changes and was accepted.

## 4. Minimization versus masking

| Corpus | Masking only, token reduction | Minimum context, token reduction | Ratio |
|---|---:|---:|---:|
| Synthetic (16) | 4.7% | 44.9% | 9.6x |
| BANKING77 subset (50) | 5.5% | 41.9% | 7.6x |

Masking hides personal values after collection; purpose-specific minimization decides what never leaves the application. The layers are complementary: minimize first, then mask the remaining text.

## 5. Limitations (state them first)

- Small corpora: 16 synthetic tickets and 50 public queries covering 10 of BANKING77's 77 intents.
- One model execution per condition: run-to-run variability is not measured yet.
- The synthetic corpus was used both to design and to evaluate the allowlist; the public subset was the holdout and its allowlist was fixed beforehand.
- BANKING77 is public, so pretraining exposure is unknown; the run supports a relative comparison of payload policies, not a claim about uncontaminated generalization.
- The masking baseline is a structured-field masker. The `openai/privacy-filter` adapter and the `opf-necessity-certificate` skill exist but have not produced a recorded real-model run; no Privacy Filter number is claimed.
- Task-specific empirical evidence for an engineering review or a DPIA, not a legal conclusion.

## 6. Pitch sentence

We reduced the context sent to the model by 41.9% on public data, withheld 100% of raw structured identity values, and preserved 45 of 50 expected decisions. Masking protects the remaining text; Necessity Certificate shows why the rest never needed to leave the application.

## Reproduce

```bash
pip install -r poc/requirements.txt
export OPENAI_API_KEY="your-key"
python poc/benchmark.py --engine openai --model gpt-4o-mini --masker structured
python poc/benchmark.py --corpus banking77 --engine openai --model gpt-4o-mini --masker structured
```
