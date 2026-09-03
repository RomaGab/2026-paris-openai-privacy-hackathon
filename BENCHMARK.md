# Benchmark: Less Data, Preserved Task Utility

## Benchmark question

The benchmark does not ask whether we can detect PII better than a PII detector. It asks a different, task-specific question:

> How much context can we withhold from an AI call while preserving the expected task outcome?

The core comparison is `minimum_context` versus `full_context`. A second comparison, `minimum_plus_masking` versus `masking_only`, shows the additional value of purpose-specific minimization when a masking layer already exists.

This framing makes the relationship with [OpenAI Privacy Filter](https://huggingface.co/openai/privacy-filter) complementary. Privacy Filter detects and masks PII spans in text. Necessity Certificate tests whether the AI task needs a field or fact at all, enforces the reviewed minimum payload, and records the evidence.

## Four conditions

Every condition uses the same labelled corpus, task instruction, model configuration, and output labels.

| Condition | Payload | Question answered |
|---|---|---|
| `full_context` | Every declared record field, including raw identifiers. | What is the reference task result? |
| `masking_only` | The complete record after applying the selected masking layer. | What does masking remove while retaining the original record shape? |
| `minimum_context` | Only the purpose-specific allowlisted fields. | What is the measured contribution of contextual minimization? |
| `minimum_plus_masking` | The minimum context with masking applied to any remaining text. | What does minimization add when masking is already present? |

The default `structured` masker is a deterministic comparison baseline for fields already classified as PII. It is not OpenAI Privacy Filter and cannot detect PII hidden in free text. The optional `opf` adapter runs the actual `openai/privacy-filter` model through Hugging Face Transformers.

## Task and ground truth

The minimum viable benchmark routes a synthetic support ticket to exactly one declared queue:

- `billing`
- `account_security`
- `shipping_logistics`
- `technical_support`
- `general_inquiry`

Each case has an expected queue. This permits exact-match accuracy instead of an uncalibrated LLM-as-judge relevance score.

The current corpus contains 16 synthetic cases. Results should therefore always include the numerator and denominator, such as `15/16`, and must not be presented as evidence of general performance beyond this declared test set.

The current corpus is an engineering corpus used both to design and evaluate the allowlist. It is not an independent holdout set. A production evaluation should freeze the contract and validate it on separate representative cases, with repeated model runs where nondeterminism matters.

### Public holdout validation

The repository also contains a fixed 50-case subset from the official BANKING77 test split. BANKING77 contains 13,083 labelled banking-support queries across 77 intents. This evaluation selects 5 examples from each of 10 declared intents by stable SHA-256 ranking with a published seed.

The public query and original intent label are preserved. Six unmistakably synthetic identity fields are added to each record so no real personal data is introduced merely to test privacy controls. The minimum payload contains only `issue_description` because the original BANKING77 intent task depends on the query, not on the synthetic identity overlay.

This must be described as a **fixed BANKING77-derived subset evaluation**, not a full BANKING77 benchmark result.

Sources and reproducibility:

- Dataset: [BANKING77 on Hugging Face](https://huggingface.co/datasets/PolyAI/banking77)
- Original data repository: [PolyAI task-specific datasets](https://github.com/PolyAI-LDN/task-specific-datasets/tree/master/banking_data)
- Paper: [Efficient Intent Detection with Dual Sentence Encoders](https://aclanthology.org/2020.nlp4convai-1.5/)
- License: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
- Committed subset: `poc/data/banking77_test_subset.json`
- Source hash and selection manifest: `poc/data/banking77_test_subset.meta.json`

To reproduce the committed subset from the official test CSV:

```bash
curl -fsSL \
  https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/master/banking_data/test.csv \
  -o /tmp/banking77-test.csv
python poc/banking77_corpus.py /tmp/banking77-test.csv
```

## Metrics

### Task utility

```text
accuracy = correct predictions / total cases

decision stability = 1 - decisions changed versus full context / total cases

improvements = full-context errors corrected by the variant

regressions = full-context correct decisions made incorrect by the variant
```

Accuracy is evaluated against the declared ground truth. Decision stability detects behavioral changes that aggregate accuracy alone can hide. Improvements and regressions distinguish helpful changes from harmful ones, while the strict certificate rule still sends every changed decision to review.

### Data reduction

```text
token reduction = 1 - variant input tokens / full-context input tokens

field reduction = 1 - variant field instances / full-context field instances

raw structured PII reduction =
    1 - variant raw structured PII values / full-context raw structured PII values
```

Token reduction measures the context transmitted to the model. Field reduction makes the architectural change understandable. Raw structured PII reduction counts original values from fields classified as structured PII that remain unchanged in the outgoing payload.

For OpenAI API runs, the harness records the input-token count returned by the API. If API usage is unavailable, it explicitly records `tiktoken` or `whitespace_estimate` as the token source.

## Acceptance rule

A minimized variant is accepted without review only when both conditions hold:

1. It causes zero individual decision changes versus full context on the declared corpus.
2. It does not reduce exact-match correctness against the ground truth.

An aggregate accuracy tie is insufficient. Predictions can change while the number of correct results remains the same.

This is empirical, bounded evidence. It is not a universal proof that a field can never matter under a different task, prompt, model, or data distribution.

## Run the benchmark

### 1. Dependency-free technical dry run

```bash
python poc/benchmark.py --engine offline --masker structured
```

This checks the end-to-end measurement and report pipeline. Its report is prominently labelled `TECHNICAL DRY RUN` and is not evidence about an LLM's data needs.

### 2. Real-model benchmark

Install the small runtime dependencies, set the API key outside the repository, and pin the model explicitly:

```bash
pip install -r poc/requirements.txt
export OPENAI_API_KEY="your-key"
python poc/benchmark.py --engine openai --model gpt-4o-mini --masker structured
```

The benchmark performs the same four passes and records each exact payload, prompt, prediction, expected label, input-token count, and token source.

### 3. Combined run with OpenAI Privacy Filter

Install and cache the optional model dependencies before the timed demo if possible:

```bash
pip install -r poc/requirements-opf.txt
python poc/benchmark.py --engine openai --model gpt-4o-mini --masker opf
```

The first execution may download the Privacy Filter model. Do not rely on that download during the live showcase.

### 4. Public BANKING77-derived validation

Run the report plumbing without making a model claim:

```bash
python poc/benchmark.py --corpus banking77 --engine offline --masker structured
```

The offline fallback does not implement BANKING77 intents. Its accuracy is deliberately excluded from model evidence.

Run the real public-data evaluation:

```bash
python poc/benchmark.py \
  --corpus banking77 \
  --engine openai \
  --model gpt-4o-mini \
  --masker structured
```

This writes separate ignored artifacts:

- `poc/banking77-benchmark-report.json`
- `poc/banking77-benchmark-report.md`

## Generated evidence

Every run writes two ignored local artifacts:

- `poc/benchmark-report.json`: complete machine-readable observations and run metadata.
- `poc/benchmark-report.md`: jury-readable Necessity Certificate benchmark table and limitations.

The JSON report includes:

- timestamp and evidence level;
- model, engine, masker, and token-count sources;
- corpus and prompt hashes;
- all four exact outgoing payloads for every case;
- predictions, expected labels, and correctness evidence;
- accuracy, decision changes, token reduction, field reduction, and raw structured-PII reduction;
- explicit limitations.

## Presentation table

Only populate this table from the generated report:

| Variant | Correct | Accuracy | Changes vs full | Input tokens | Token reduction | Raw structured PII sent |
|---|---:|---:|---:|---:|---:|---:|
| Full context | `K/N` | measured | measured | measured | `0%` | measured |
| Masking only | `K/N` | measured | measured | measured | measured | measured |
| Minimum context | `K/N` | measured | measured | measured | measured | measured |
| Minimum + masking | `K/N` | measured | measured | measured | measured | measured |

The most useful visual is a scatter plot with token reduction on the horizontal axis and accuracy on the vertical axis. The preferred condition preserves accuracy while moving furthest to the right.

The first recorded real-model result and the rejected candidate that preceded it are documented in [BENCHMARK_RESULTS.md](BENCHMARK_RESULTS.md).

## Claim boundaries

- Do not call the default structured masker an OPF run.
- Do not benchmark OPF detection precision or recall unless a separately labelled PII ground-truth corpus is added.
- Do not use the offline classifier as LLM evidence.
- Do not present supplier-leak probabilities as measurements.
- Do not claim differential privacy without an implemented privacy mechanism, privacy accounting, and a measured utility result.
- Always show the exact corpus provenance and that the findings are task-specific.
- For the public profile, state that the queries and labels are public BANKING77 data while the structured identity overlay is synthetic.
- Do not describe the 50-case, 10-intent subset as a full BANKING77 benchmark result.

## Pitch sentence

> We reduced the context sent to the model by X%, withheld Y% of raw structured personal values, and preserved K/N expected decisions. Masking protects the remaining text; Necessity Certificate shows why the rest never needed to leave the application.
