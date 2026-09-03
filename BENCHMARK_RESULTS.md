# Recorded Benchmark Results

## Status

These are real API measurements across the declared synthetic and BANKING77-derived evaluations below. They are evidence for these prototype configurations only.

- Engine: OpenAI API
- Model: `gpt-4o-mini`
- Temperature: `0`
- Token source: API-reported input usage
- Masker: deterministic structured-field baseline in the first three runs; actual `openai/privacy-filter` in the final pilot
- OPF status: actual-model pilot recorded below
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

## Public holdout validation: BANKING77-derived subset

Recorded at `2026-09-03T14:29:10.588874+00:00`.

This run used a fixed subset of 50 examples from the public BANKING77 test split: 5 examples from each of 10 original intent labels. Selection uses stable SHA-256 ranking with the published seed `necessity-certificate-2026-09-03`. The public query and original label are preserved; every structured identity field is a synthetic overlay.

- Dataset license: CC BY 4.0
- Official source CSV SHA-256: `d12d6e3bc4c3103966ae786dc435913c0c563dfa328f5a3646d0e62cfeeb474d`
- Committed subset SHA-256: `8cb8af569addd647e01dc4fcddcfe4c6a09c1772a525a9f4b8dbd30feb7cf91e`
- Prompt SHA-256: `303a55251f47010a958836662b20b4c9a68929a6c653a0e29c753fe545905445`
- Token source: API-reported input usage

| Variant | Correct | Accuracy | Changes vs full | Improvements | Regressions | Input tokens | Token reduction | Field reduction | Raw structured PII sent |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Full context | 44/50 | 88.0% | 0 | 0 | 0 | 9,921 | 0.0% | 0.0% | 300 |
| Masking only | 45/50 | 90.0% | 1 | 1 | 0 | 9,371 | 5.5% | 0.0% | 0 |
| Minimum context | 45/50 | 90.0% | 1 | 1 | 0 | 5,764 | 41.9% | 88.9% | 0 |
| Minimum + masking | 45/50 | 90.0% | 1 | 1 | 0 | 5,764 | 41.9% | 88.9% | 0 |

The only changed decision was `B77-0015`, whose public query is `Can I freeze my card right now?`. Full context returned `verify_my_identity`; every reduced or masked condition returned the expected label `compromised_card`. The change therefore corrected one error rather than introducing a regression. The strict certificate still marks the minimized condition for review because it permits no silent decision changes.

This run provides independent public-task evidence that contextual minimization withheld all 300 raw structured identity values and reduced API-reported input tokens by 41.9%, while exact-match accuracy increased from 88.0% to 90.0%. It is a fixed BANKING77-derived subset evaluation, not a full BANKING77 benchmark result.

## Actual OPF orchestration pilot: BANKING77-derived subset

Recorded at `2026-09-03T15:41:48.541909+00:00`.

This real-model pilot selected one case from each of the 10 intent groups in the committed 50-case BANKING77-derived subset: indices `0, 5, 10, ..., 45`. The public support queries and labels are preserved, while the structured identity fields are synthetic overlays.

- Task engine: `openai:gpt-4o-mini`
- Token source: API-reported input usage
- OPF model: `openai/privacy-filter`
- OPF revision: `7ffa9a043d54d1be65afb281eddf0ffbe629385b`
- OPF runtime: Transformers `5.16.1`, PyTorch `2.14.0`
- Selected-records canonical SHA-256: `07d5ffbbc7bf5869f83e65ef651eb6b20f643e436029e198be16516596edc7e5`
- Schema SHA-256: `c1a1e715a6708de57bac90784b45c298cc071e7d4968314903c1460335434dfb`
- Prompt-contract SHA-256: `d7583a7abed6bd19e1aff0ff3b141ab674683bc076fb637bf50cc29b81f9c3d4`

| Variant | Correct | Accuracy | Changes vs full | Input tokens | Token reduction | Field reduction | Residual known personal fields | OPF spans |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Full context | 9/10 | 90.0% | 0 | 2,039 | 0.0% | 0.0% | 60 | 0 |
| OPF only | 9/10 | 90.0% | 0 | 2,423 | -18.8% | 0.0% | 4 | 119 |
| Minimum context | 9/10 | 90.0% | 0 | 1,208 | 40.8% | 90.0% | 0 | 0 |
| Minimum + OPF | 9/10 | 90.0% | 0 | 1,208 | 40.8% | 90.0% | 0 | 0 |

The ablation selected only `issue_description`. Removing it changed all 10 decisions and reduced accuracy from 90.0% to 0.0%. Every other field caused zero decision changes when removed independently, so it was marked as a drop candidate.

OPF-only preserved the full-context decisions and masked 56 of the 60 known structured personal-field instances. Four synthetic `address` instances remained unchanged. OPF emitted 119 spans because a single value may produce multiple token-classification spans. Its replacement markers also increased API input usage by 18.8% in this pilot.

The minimum-context policy removed the structured identity fields before OPF. It preserved all full-context decisions, reduced fields by 90.0%, reduced API input tokens by 40.8%, and left no known structured personal fields. OPF then found no spans in the remaining `issue_description` values in this selected sample.

This is a 10-case orchestration pilot, not an OPF recall benchmark and not a full BANKING77 result. The self-contained HTML, JSON, Markdown, field register, SQL view, and SVG chart are in `benchmark-results/opf-banking77-pilot-10/`. The evidence artifacts omit raw record values and detected PII text.

## What this result demonstrates

1. The certificate can reject an over-aggressive minimum contract instead of automatically approving every reduction.
2. Purpose-specific minimization produced substantially more token reduction than masking alone in the accepted run: 44.9% versus 4.7%.
3. Masking and minimization remain separate layers. The earlier structured-masker runs do not evaluate OPF detection quality.
4. In the actual-OPF pilot, minimization removed known unnecessary identity fields that OPF alone did not fully transform.
5. OPF replacement text can increase token volume, while purpose-specific minimization reduced it before the model call.

## Limitations

- The corpus is small and synthetic.
- The same engineering corpus was used to revise and evaluate the allowlist. It is not a held-out validation set.
- A single model execution per condition does not measure run-to-run variability.
- The full-context reference itself scored 15/16, so the benchmark demonstrates preservation relative to that reference, not perfect task performance.
- The causal role of `urgency` is not established by the second run alone. The complete revised condition passed; repeated ablations would be needed to isolate causality under model nondeterminism.
- The result is specific to the recorded corpus, prompt, model, and run. It is not a universal or legal proof.
- The public validation covers 50 examples and 10 of BANKING77's 77 intents. The synthetic identity overlay tests irrelevant structured context, not naturally occurring PII in BANKING77 queries.
- BANKING77 is public and possible model pretraining exposure is unknown. This run supports a relative comparison of payload policies, not a claim of uncontaminated model generalization.
- The actual-OPF pilot contains only one example per selected intent. It establishes that the integration runs end to end, not a statistically stable OPF quality estimate.
- The OPF span total is not an entity-level precision or recall score. No labeled free-text PII ground truth was used.

## Reproduce

```bash
pip install -r poc/requirements.txt
export OPENAI_API_KEY="your-key"
python poc/benchmark.py --engine openai --model gpt-4o-mini --masker structured
python poc/benchmark.py --corpus banking77 --engine openai --model gpt-4o-mini --masker structured

# Full OPF orchestration run. Use a clean virtual environment.
HF_HUB_DISABLE_XET=1 HF_HOME=/tmp/opf-hf-cache \
  python skills/opf-necessity-certificate/scripts/opf_necessity_certificate.py \
  --purpose "classify a banking support request into the correct intent" \
  --schema poc/data/tickets_schema.sql \
  --data poc/data/banking77_test_subset.json \
  --label-field expected_queue \
  --engine openai \
  --model gpt-4o-mini \
  --opf-revision 7ffa9a043d54d1be65afb281eddf0ffbe629385b \
  --out-dir out/opf-banking77
```

The generated JSON contains each exact payload, prompt, prediction, expected label, and token count. Generated reports remain ignored by Git to avoid accidentally committing future evaluation records.
