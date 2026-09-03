# Four-Condition Privacy Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible benchmark that compares full context, masking alone, minimum context, and minimum context plus masking while measuring task utility and data reduction.

**Architecture:** A pure payload layer creates the four variants. A classifier adapter runs the same fixed task for every payload and returns both the decision and the input-token count. A report layer calculates ground-truth accuracy, decision stability, token reduction, field reduction, and raw structured-PII reduction, then exports traceable JSON and Markdown artifacts.

**Tech Stack:** Python 3.10+, standard-library `unittest`, existing OpenAI Python SDK and `tiktoken`, optional Hugging Face `transformers` adapter for `openai/privacy-filter`.

## Global Constraints

- Every reported number must come from an executed run.
- Offline fallback results must be labelled as a technical dry run, not LLM evidence.
- The benchmark must not claim to measure OpenAI Privacy Filter unless the real model adapter is selected.
- The same corpus, prompt, model configuration, and output labels must be used across all four conditions.
- A removal recommendation requires zero individual decision changes on the declared corpus.
- Public code and documentation are in English and contain no employer references.

---

### Task 1: Strict decision-stability rule

**Files:**
- Modify: `poc/minimize.py`
- Test: `tests/test_minimize.py`

**Interfaces:**
- Consumes: baseline and ablated prediction lists.
- Produces: `recommend_field_action(changed_decisions: int) -> str`.

- [ ] **Step 1: Write the failing test**

```python
def test_changed_decision_requires_retention_even_when_accuracy_is_flat():
    assert recommend_field_action(2).startswith("retain")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m unittest tests.test_minimize -v`

Expected: FAIL because `recommend_field_action` does not exist.

- [ ] **Step 3: Implement the minimal rule**

```python
def recommend_field_action(changed_decisions: int) -> str:
    return "block before the model call" if changed_decisions == 0 else "retain: changes measured decisions"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m unittest tests.test_minimize -v`

Expected: PASS.

### Task 2: Four payload conditions and metrics

**Files:**
- Create: `poc/benchmark.py`
- Test: `tests/test_benchmark.py`

**Interfaces:**
- Consumes: synthetic ticket records and a masker implementing `mask_record(record) -> dict`.
- Produces: `build_variant_payloads`, `calculate_variant_metrics`, and `run_benchmark`.

- [ ] **Step 1: Write failing tests for the four named variants**

```python
def test_variants_separate_masking_from_minimization():
    variants = build_variant_payloads(TICKET, StructuredFieldMasker())
    assert list(variants) == ["full_context", "masking_only", "minimum_context", "minimum_plus_masking"]
    assert "email" in variants["masking_only"]
    assert "email" not in variants["minimum_context"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_benchmark -v`

Expected: FAIL because `poc/benchmark.py` does not exist.

- [ ] **Step 3: Implement the four payload builders and metrics**

Implement fixed variant ordering, structured masking, minimum-field allowlisting, exact-match accuracy, decision changes against full context, and reductions against full context.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_benchmark -v`

Expected: PASS.

### Task 3: Traceable report and optional OPF adapter

**Files:**
- Modify: `poc/benchmark.py`
- Create: `poc/requirements-opf.txt`
- Test: `tests/test_benchmark.py`

**Interfaces:**
- Consumes: benchmark observations.
- Produces: JSON report, Markdown report, `StructuredFieldMasker`, and `OpenAIPrivacyFilterMasker`.

- [ ] **Step 1: Write failing tests for span replacement and report labels**

Test that detected spans are replaced from right to left and that offline reports display the mandatory dry-run warning.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_benchmark -v`

Expected: FAIL because span replacement and Markdown rendering do not exist.

- [ ] **Step 3: Implement the report and adapter**

The OPF adapter loads `pipeline("token-classification", model="openai/privacy-filter")` only when explicitly selected. The default masking baseline remains dependency-free and must not be labelled OPF.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_benchmark -v`

Expected: PASS.

### Task 4: English benchmark documentation

**Files:**
- Create: `BENCHMARK.md`
- Modify: `README.md`
- Modify: `PRODUCT_PLAN.md`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: benchmark CLI and report schema.
- Produces: exact execution commands, interpretation guidance, evidence table, and claim boundaries.

- [ ] **Step 1: Document the four-condition design**

Include the comparison matrix, formulas, acceptance rule, output table, optional OPF command, and the two key comparisons: minimum versus full, then minimum plus masking versus masking alone.

- [ ] **Step 2: Document limitations**

State that a small synthetic corpus is demonstration evidence only and that the structured masking baseline is not an OPF evaluation.

- [ ] **Step 3: Verify links and commands**

Run: `python poc/benchmark.py --help`

Expected: exit code 0 with documented options.

### Task 5: Full verification and dry run

**Files:**
- Generated and ignored: `poc/benchmark-report.json`
- Generated and ignored: `poc/benchmark-report.md`

**Interfaces:**
- Consumes: all previous tasks.
- Produces: fresh verification evidence and a locally inspectable technical dry run.

- [ ] **Step 1: Run all tests**

Run: `python -m unittest discover -s tests -v`

Expected: all tests pass.

- [ ] **Step 2: Run the offline benchmark**

Run: `python poc/benchmark.py --engine offline`

Expected: JSON and Markdown reports are written and labelled `TECHNICAL DRY RUN`.

- [ ] **Step 3: Inspect repository changes**

Run: `git diff --check && git status --short`

Expected: no whitespace errors and only intended files changed.
