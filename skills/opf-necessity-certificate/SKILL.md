---
name: opf-necessity-certificate
description: Generate a problem-specific privacy-by-design evidence package by combining field-level necessity ablation with the actual openai/privacy-filter model. Use when assessing which fields an AI classification task needs, comparing full context, OPF only, minimum context, and minimum plus OPF, or producing auditable HTML, JSON, Markdown, CSV, SQL, and SVG evidence for an engineering review or DPIA.
---

# OPF Necessity Certificate

## Overview

Measure what a declared AI task needs and what OPF detects before data reaches the model. Produce one self-contained report for the supplied problem, not a generic marketing benchmark.

Treat every output as empirical engineering evidence. Never describe it as a legal compliance decision or a universal proof of necessity.

## Required inputs

- One declared classification purpose.
- One SQL file containing a single `CREATE TABLE` statement.
- A non-empty JSON array of records containing ground-truth labels.
- The label field. Label values may be supplied or inferred from the dataset.
- Optional privacy-cost overrides using the categories in `references/report-schema.md`.
- `OPENAI_API_KEY` for real task-model evidence.

Install the runtime in `references/requirements.txt` inside a clean virtual environment before the first OPF run. Avoid a shared Python environment with unrelated Torch or Torchvision packages: incompatible native wheels can crash during `transformers.pipeline` import.

```bash
python3 -m venv /tmp/opf-necessity-venv
/tmp/opf-necessity-venv/bin/python -m pip install -r \
  skills/opf-necessity-certificate/references/requirements.txt
```

If OPF cannot load, stop and report the error. Do not substitute a regex or structured-field masker.

## Run

```bash
python skills/opf-necessity-certificate/scripts/opf_necessity_certificate.py \
  --purpose "route a banking support request" \
  --schema path/to/schema.sql \
  --data path/to/labeled-records.json \
  --label-field expected_intent \
  --model gpt-4o-mini \
  --engine openai \
  --opf-revision COMMIT_SHA \
  --out-dir out/opf-certificate
```

Use `--engine offline` only to test plumbing. The resulting report is forced to `review_required` and must not be used as evidence about an LLM's data needs.

## Interpret the result

The script performs single-field ablations, then evaluates the complete policy under four conditions:

1. `full_context`: all declared fields, without OPF.
2. `opf_only`: all declared fields after OPF.
3. `minimum_context`: fields retained by ablation, without OPF.
4. `minimum_plus_opf`: retained fields after OPF.

A field with zero individual decision changes becomes `drop_candidate`. Any changed decision becomes `retained_pending_review`, including an accuracy improvement. This wording is intentional: ablation shows task influence, not universal necessity.

The final status can be `accepted_without_review` only when the task predictor is a real OpenAI model run, the masker identifies itself as the actual OPF model, the combined branch causes zero decision changes, and accuracy does not fall. Otherwise it is `review_required`.

## Deliverables

- `opf_necessity_certificate.html`: self-contained visual evidence report.
- `opf_necessity_certificate.json`: machine-readable source of truth.
- `opf_necessity_certificate.md`: reviewer-readable summary.
- `field_decisions.csv`: field-level decision register.
- `minimized_schema.sql`: fail-closed view that excludes personal retained fields until a transform is enforced.
- `benchmark_chart.svg`: accuracy and token-volume comparison.

Open the HTML after generation and include its absolute path in the handoff. Confirm that the declared purpose, four variants, hashes, OPF model and revision, field decisions, limitations, and review status are visible.

## Evidence boundary

The output intentionally omits raw record values, prompts, and detected PII text. It includes only field names, aggregate OPF categories, aggregate metrics, predictions, labels, and hashes. Do not add cost or carbon claims unless the run also supplies current provider pricing or measured energy data.

Read `references/report-schema.md` when consuming the JSON or integrating the report into another system.

## Files

- `scripts/opf_necessity_certificate.py`: orchestrator and CLI.
- `assets/report.html`: standalone report template.
- `references/report-schema.md`: evidence semantics and claim boundaries.
- `references/requirements.txt`: explicit OPF runtime dependencies.
