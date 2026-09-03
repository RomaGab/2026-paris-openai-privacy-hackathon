# Roadmap

Written 3 September 2026 at the end of the hackathon build window. Each item names what would be measured, so that no future claim is made before its run exists.

## Delivered on 3 September 2026

- Four-condition benchmark (full record, masking only, minimum context, minimum plus masking) with a strict decision-stability rule: a field is dropped only when its removal changes zero individual decisions.
- Recorded real-model evidence on a synthetic support corpus (16 tickets) and on a fixed public BANKING77-derived subset (50 queries), with corpus and prompt hashes, exact payloads, and API-reported token counts. See [RESULTS_SUMMARY.md](RESULTS_SUMMARY.md).
- One rejected contract kept on record: the certificate refused an over-aggressive minimum.
- Necessity Certificate report (HTML and Markdown), MCP server on Cloudflare Workers, skill packaging, DemoDSL demo video.

## Next two weeks

- Run the real `openai/privacy-filter` adapter as the masking layer and record the first Privacy Filter numbers; the `opf-necessity-certificate` skill and its design spec exist, the run does not yet.
- Repeat every condition five times to measure run-to-run variability and report intervals instead of single values.
- Extend the public holdout from 10 to all 77 BANKING77 intents.
- Measure the first transformation rather than a removal: `account_id` derived locally into `subscription_plan`, with the task rerun on the derived fact.

## One to three months

- One continuous journey: Privacy Preflight wizard, data map, benchmark, enforced payload, exportable certificate for a DPIA. No manual file editing between screens.
- Execute the generated fail-closed SQL view against a real database and verify that the AI-facing view exposes only the contracted fields.
- A second task family (structured extraction) to test whether the method transfers beyond classification.

## Three to six months

- Pairwise ablations or Shapley attribution to detect field interactions: two fields that are unnecessary alone but necessary together.
- Per-field utility bits (output distribution shift with and without the field) and identity bits (anonymity-set size), the privacy-funnel framing, written up as a paper.

## Not claimed until implemented and measured

- Differential privacy: requires a noise mechanism, privacy accounting, and a measured utility cost.
- Breach or supplier-leak probabilities: the existing simulation is scenario analysis, not evidence.
- Legal compliance: the certificate is empirical, task-specific evidence, not a legal verdict.
