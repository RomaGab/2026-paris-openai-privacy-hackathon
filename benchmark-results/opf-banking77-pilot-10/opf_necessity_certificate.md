# Privacy-by-Design Evidence Report

**Declared purpose:** classify a banking support request into the correct intent
**Review status:** `accepted_without_review`
**Evidence level:** `real_model_run`

This is engineering evidence for a DPIA or privacy review. It is not a legal compliance decision.

## Four-condition benchmark

| Variant | Accuracy | Changes | Improvements | Regressions | Input tokens | Token reduction | Field reduction | Residual personal fields | OPF spans |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Full context | 90.0% | 0 | 0 | 0 | 2039 | 0.0% | 0.0% | 60 | 0 |
| OPF only | 90.0% | 0 | 0 | 0 | 2423 | -18.8% | 0.0% | 4 | 119 |
| Minimum context | 90.0% | 0 | 0 | 0 | 1208 | 40.8% | 90.0% | 0 | 0 |
| Minimum + OPF | 90.0% | 0 | 0 | 0 | 1208 | 40.8% | 90.0% | 0 | 0 |

## Field decisions

| Field | Privacy cost | Decision | Changes | Accuracy without | Tokens saved | Review reason |
|---|---|---|---:|---:|---:|---|
| `issue_description` | task-relevant, not personal | `retained_pending_review` | 10 | 0.0% | 269 | At least one individual decision changed; retain until human review. |
| `product_area` | task-relevant, not personal | `drop_candidate` | 0 | 90.0% | 80 | No individual decision changed in this single-field ablation. |
| `urgency` | task-relevant, not personal | `drop_candidate` | 0 | 90.0% | 50 | No individual decision changed in this single-field ablation. |
| `name` | direct identifier | `drop_candidate` | 0 | 90.0% | 90 | No individual decision changed in this single-field ablation. |
| `email` | direct identifier | `drop_candidate` | 0 | 90.0% | 110 | No individual decision changed in this single-field ablation. |
| `phone` | direct identifier | `drop_candidate` | 0 | 90.0% | 130 | No individual decision changed in this single-field ablation. |
| `date_of_birth` | quasi-identifier | `drop_candidate` | 0 | 90.0% | 130 | No individual decision changed in this single-field ablation. |
| `address` | direct identifier | `drop_candidate` | 0 | 90.0% | 110 | No individual decision changed in this single-field ablation. |
| `account_id` | direct identifier | `drop_candidate` | 0 | 90.0% | 140 | No individual decision changed in this single-field ablation. |
| `support_notes` | task-relevant, not personal | `drop_candidate` | 0 | 90.0% | 0 | No individual decision changed in this single-field ablation. |

## OPF provenance

- Model: `openai/privacy-filter`
- Requested revision: `7ffa9a043d54d1be65afb281eddf0ffbe629385b`
- Resolved revision: `7ffa9a043d54d1be65afb281eddf0ffbe629385b`
- OPF evidence level: `actual_opf_model`
- Detected spans in full context: `119`

## Reproducibility

- Corpus SHA-256: `07d5ffbbc7bf5869f83e65ef651eb6b20f643e436029e198be16516596edc7e5`
- Schema SHA-256: `c1a1e715a6708de57bac90784b45c298cc071e7d4968314903c1460335434dfb`
- Prompt contract SHA-256: `d7583a7abed6bd19e1aff0ff3b141ab674683bc076fb637bf50cc29b81f9c3d4`

## Limitations

- This report is empirical evidence for one declared purpose, dataset, prompt contract, model, and run.
- It is not a legal compliance decision or a universal proof that a field never matters.
- Single-field ablation can miss interactions between fields; the minimum-context branch tests their combined removal.
- OPF span counts measure detected entities, not guaranteed removal of every possible identifier.
- Raw record values, prompts, and detected PII text are intentionally omitted from the evidence artifacts.
