# Evidence report semantics

The JSON file is the source of truth for every rendered artifact.

## Status

- `accepted_without_review`: a real task-model run and actual OPF run produced zero individual decision changes in the minimum-plus-OPF branch, with no accuracy loss.
- `review_required`: every other outcome, including offline runs, test fixtures, improvements, regressions, or unresolved decision changes.

Neither status is a legal compliance conclusion.

## Field decision

- `drop_candidate`: removing the field alone caused zero prediction changes on the declared dataset.
- `retained_pending_review`: removing the field changed at least one prediction. This does not claim universal necessity.

Privacy-cost categories are `task-relevant, not personal`, `quasi-identifier`, `direct identifier`, and `sensitive numeric`.

## Benchmark variants

- `full_context`: all declared input fields, no OPF.
- `opf_only`: all declared input fields after OPF.
- `minimum_context`: retained fields, no OPF.
- `minimum_plus_opf`: retained fields after OPF.

Compare variants at the individual-decision level. Keep improvements, regressions, and other changes separate.

## Provenance and privacy

`corpus_sha256`, `schema_sha256`, and `prompt_contract_sha256` bind the report to its evaluated inputs without reproducing them. The report omits raw record values, prompts, and the text of detected spans. OPF metadata records model ID, requested and resolved revisions, runtime versions, and aggregate detected categories.
