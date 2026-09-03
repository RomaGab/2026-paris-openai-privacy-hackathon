# Purpose-specific minimization: 41.9% fewer tokens, zero identity values sent, accuracy preserved

Necessity Certificate benchmark on public data: fixed BANKING77-derived subset, 50 support queries (10 intents x 5), synthetic identity overlay, gpt-4o-mini, temperature 0, API-reported input tokens. Run 2026-09-03.

**41.9%** fewer input tokens (9,921 to 5,764) · **300 to 0** raw identity values sent to the model · **88.9%** fewer fields sent (450 to 50) · **88% to 90%** accuracy (1 error corrected, 0 regressions)

| Payload sent to the model | Accuracy | Input tokens | Token reduction | Fields sent | Identity values sent | Certificate |
|---|---:|---:|---:|---:|---:|---|
| Full record | 44/50 (88.0%) | 9,921 | 0.0% | 450 | 300 | reference |
| Masking only | 45/50 (90.0%) | 9,371 | 5.5% | 450 | 0 | review (1 change) |
| **Minimum context** | **45/50 (90.0%)** | **5,764** | **41.9%** | **50** | **0** | **review (1 change)** |
| Minimum + masking | 45/50 (90.0%) | 5,764 | 41.9% | 50 | 0 | review (1 change) |

**Masking alone cuts 5.5% of tokens; deciding what never leaves the application cuts 41.9% (7.6x).** The strict rule routes any changed decision, even an improvement, to human review. Synthetic support corpus (16 tickets): 44.9% fewer tokens, 96 PII values withheld, zero decision changes, accepted; the first candidate contract was rejected after one changed decision.

*Limits: 50 cases over 10 of 77 intents, one run per condition, structured-field masker (not OpenAI Privacy Filter), public dataset with unknown pretraining exposure. Empirical evidence for an engineering review or a DPIA, not a legal proof. Source: BENCHMARK_RESULTS.md, benchmark-results/summary.csv (BANKING77, CC BY 4.0).*

Speaker note: the only changed decision is B77-0015, "Can I freeze my card right now?". Full context answered verify_my_identity; every reduced condition answered the expected compromised_card.
