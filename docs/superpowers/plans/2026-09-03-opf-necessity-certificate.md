# OPF Necessity Certificate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an isolated skill that combines generic field ablation with actual OpenAI Privacy Filter masking and emits a problem-specific, four-condition evidence report.

**Architecture:** A single Python orchestration module owns validation, ablation, four-branch evaluation, metrics, and artifact rendering. The OPF adapter is dependency-injected for tests but the CLI always constructs the actual `openai/privacy-filter` adapter and fails closed if it cannot load. HTML, Markdown, CSV, SQL, SVG, and JSON are derived from one report object.

**Tech Stack:** Python 3.11 standard library, OpenAI Python client already used by the repository, Hugging Face Transformers, PyTorch, unittest.

## Global Constraints

- Keep all runtime changes inside `skills/opf-necessity-certificate/`.
- Do not alter existing skills, PoC behavior, MCP server behavior, or recorded benchmark results.
- Never label the output as legal compliance or a universal proof.
- Never silently replace OPF with regex, structured-field masking, or a test fixture.
- Never write raw record values, prompts, or detected PII text into evidence artifacts.
- Public code and documentation use English and no em dash characters.

---

### Task 1: Define orchestration behavior with failing tests

**Files:**
- Create: `tests/test_opf_necessity_certificate_skill.py`
- Create: `skills/opf-necessity-certificate/scripts/opf_necessity_certificate.py`

**Interfaces:**
- Consumes: `run_certificate(config, records, schema_sql, predictor, masker)` with injected test doubles.
- Produces: a report containing `field_evidence`, `minimum_fields`, `benchmark.variants`, `opf`, `status`, `limitations`, and provenance hashes.

- [ ] **Step 1: Write failing tests**

Test that zero-change fields become `drop_candidate`, changed fields become `retained_pending_review`, all four variants exist, improvements and regressions are separate, technical fixtures cannot be auto-accepted, no raw email appears in serialized evidence, and OPF load failures raise instead of falling back.

- [ ] **Step 2: Run the focused tests to verify RED**

Run: `python -m unittest tests.test_opf_necessity_certificate_skill -v`

Expected: FAIL because `opf_necessity_certificate.py` has no implementation.

- [ ] **Step 3: Implement the minimum orchestration API**

Implement `CertificateConfig`, `Decision`, `MaskingResult`, `evaluate_records`, `build_field_evidence`, `calculate_variant_metrics`, `OpenAIPrivacyFilterMasker`, and `run_certificate`. Keep the CLI boundary separate from injected test fixtures.

- [ ] **Step 4: Run the focused tests to verify GREEN**

Run: `python -m unittest tests.test_opf_necessity_certificate_skill -v`

Expected: all focused tests pass.

### Task 2: Render the evidence package

**Files:**
- Modify: `tests/test_opf_necessity_certificate_skill.py`
- Modify: `skills/opf-necessity-certificate/scripts/opf_necessity_certificate.py`
- Create: `skills/opf-necessity-certificate/assets/report.html`
- Create: `skills/opf-necessity-certificate/references/report-schema.md`

**Interfaces:**
- Consumes: the report returned by `run_certificate`.
- Produces: `render_markdown(report)`, `render_html(report)`, `render_csv(report)`, `render_sql(report)`, `render_svg(report)`, and `write_artifacts(report, out_dir)`.

- [ ] **Step 1: Add failing artifact tests**

Assert that HTML contains the declared purpose, four variant labels, percentages, OPF model and revision, hashes, review status, limitations, and embedded source JSON. Assert that all six artifact files are written and raw input values are absent.

- [ ] **Step 2: Run the focused tests to verify RED**

Run: `python -m unittest tests.test_opf_necessity_certificate_skill -v`

Expected: FAIL because renderers and artifacts do not exist.

- [ ] **Step 3: Implement escaped, deterministic renderers**

Use `html.escape`, `json.dumps`, `csv.DictWriter`, and inline SVG/CSS. Render field-flow examples using field names and counts only. Generate every artifact from the same immutable report dictionary.

- [ ] **Step 4: Run the focused tests to verify GREEN**

Run: `python -m unittest tests.test_opf_necessity_certificate_skill -v`

Expected: all focused tests pass.

### Task 3: Finish the reusable skill interface

**Files:**
- Modify: `skills/opf-necessity-certificate/SKILL.md`
- Modify: `skills/opf-necessity-certificate/agents/openai.yaml`
- Modify: `skills/opf-necessity-certificate/scripts/opf_necessity_certificate.py`
- Create: `skills/opf-necessity-certificate/references/requirements.txt`

**Interfaces:**
- Consumes: CLI arguments for purpose, schema, data, label field, labels, model, engine, revision, overrides, and output directory.
- Produces: a non-zero exit with a clear message on invalid inputs or missing OPF runtime; otherwise writes the six artifacts.

- [ ] **Step 1: Add failing CLI-validation tests**

Cover missing API key for `--engine openai`, empty data, absent label values, invalid privacy overrides, and a masker that does not identify itself as the actual OPF model.

- [ ] **Step 2: Run the focused tests to verify RED**

Run: `python -m unittest tests.test_opf_necessity_certificate_skill -v`

Expected: FAIL on the new validation assertions.

- [ ] **Step 3: Implement the CLI and skill instructions**

Document one executable workflow, its six outputs, the evidence boundary, and the exact OPF dependency. Keep `SKILL.md` concise and remove all scaffold placeholders.

- [ ] **Step 4: Run the focused tests to verify GREEN**

Run: `python -m unittest tests.test_opf_necessity_certificate_skill -v`

Expected: all focused tests pass.

### Task 4: Validate and commit

**Files:**
- Verify: `skills/opf-necessity-certificate/`
- Verify: `tests/test_opf_necessity_certificate_skill.py`

**Interfaces:**
- Consumes: the complete isolated skill.
- Produces: validation logs, a generated technical-dry-run evidence package, and a Wilfred Doré-authored git commit.

- [ ] **Step 1: Validate the skill structure**

Run: `python /Users/wdore/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/opf-necessity-certificate`

Expected: skill is valid.

- [ ] **Step 2: Run the complete Python test suite**

Run: `python -m unittest discover -s tests -v`

Expected: all tests pass with zero failures and zero errors.

- [ ] **Step 3: Generate and inspect a technical dry-run report**

Run the orchestrator through its library interface with deterministic fixtures, then verify the HTML contains the four benchmark conditions and no source PII values.

- [ ] **Step 4: Review the final diff and forbidden claims**

Run: `git diff --check` and search the new runtime files for legal-certification claims, scaffold placeholders, and em dash characters.

- [ ] **Step 5: Commit with the requested identity**

Run: `git -c user.name='Wilfred Doré' -c user.email='wilfred.dore@telecom-paristech.org' commit -m 'Add OPF necessity certificate skill'`

