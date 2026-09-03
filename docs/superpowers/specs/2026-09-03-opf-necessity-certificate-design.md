# OPF Necessity Certificate Design

## Objective

Create a separate orchestration skill that accepts a declared classification purpose, one SQL table schema, and a labeled JSON dataset. It combines field-level necessity testing with the actual `openai/privacy-filter` model and produces one problem-specific privacy-by-design evidence package.

The output is evidence for engineering review or a DPIA. It is not a legal compliance certificate and must not use language such as "legally compliant" or "proven necessary".

## Isolation

All runtime implementation lives under `skills/opf-necessity-certificate/`. Existing skills, the PoC, and MCP server remain unchanged. A dedicated test module may be added under `tests/`.

## Inputs

- A one-sentence declared purpose.
- A SQL file containing exactly one `CREATE TABLE` statement.
- A non-empty JSON array of labeled records.
- The label field, with label values inferred from the records unless explicitly supplied.
- Optional field privacy-cost overrides.
- The task model and engine. Real evidence requires the OpenAI engine and an API key; offline execution is marked as a technical dry run.
- An optional immutable Hugging Face revision for `openai/privacy-filter`.

## Processing

1. Parse the schema and exclude the primary key and label from model inputs.
2. Evaluate the full context once.
3. Remove each input field independently and evaluate the same task again.
4. Mark a field `drop_candidate` only when removal causes zero individual decision changes. Any changed decision yields `retained_pending_review`, including changes that improve accuracy.
5. Build the minimum context from all retained fields.
6. Load the actual `openai/privacy-filter` token-classification pipeline. Missing dependencies or model-loading failures stop the run; there is no substitute masker.
7. Evaluate four branches on the same records and task: full context, OPF only, minimum context, and minimum plus OPF.
8. Compare every branch with full context, separating improvements, regressions, and other decision changes.
9. Accept the minimum-plus-OPF branch without review only for a real-model run with zero individual decision changes and no accuracy loss. All technical dry runs remain `review_required`.

## Privacy and provenance

The evidence artifacts never store raw dataset values, prompts, or detected PII spans. They store field names, aggregate span categories, predictions, labels, token counts, and cryptographic hashes. OPF provenance includes model ID, requested revision, resolved revision when available, and runtime library versions.

Token totals use API-reported input tokens when available. Otherwise, the report names the tokenizer or estimate used. Cost and carbon claims are excluded because they require provider-specific prices and measured energy data.

## Outputs

The output directory contains:

- `opf_necessity_certificate.json`: source-of-truth evidence report.
- `opf_necessity_certificate.md`: reviewer-readable summary.
- `opf_necessity_certificate.html`: self-contained visual report generated from the same report object.
- `field_decisions.csv`: one row per field.
- `minimized_schema.sql`: fail-closed AI-facing view.
- `benchmark_chart.svg`: dependency-free chart of accuracy and token volume.

The HTML visibly includes the declared problem, run status, field decisions, four-condition benchmark, OPF provenance, hashes, limitations, and a no-raw-values field-flow example.

## Error handling

- Reject empty datasets, missing labels, unknown schema fields, invalid override categories, and malformed SQL.
- Require `OPENAI_API_KEY` for the OpenAI engine.
- Fail clearly if Transformers, PyTorch, or the OPF model cannot load.
- Escape every dynamic HTML value and neutralize closing script tags in embedded JSON.

## Verification

Unit tests inject a deterministic test masker and predictor. This validates orchestration and rendering without pretending the fixture is OPF evidence. A separate runtime probe attempts to load the actual model only when dependencies and model files are available.

