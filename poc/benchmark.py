"""Four-condition data-minimization benchmark.

Compares the same labelled task under four payload policies:

1. full_context
2. masking_only
3. minimum_context
4. minimum_plus_masking

The default structured-field masker is a dependency-free comparison baseline.
It is not OpenAI Privacy Filter. Select ``--masker opf`` to run the actual
``openai/privacy-filter`` model through Hugging Face Transformers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import OrderedDict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Protocol

from banking77_corpus import (
    BANKING77_INTENTS,
    BANKING77_LICENSE,
    BANKING77_SOURCE_URL,
)
from classifier import FIELDS, QUEUES, _build_prompt, classify_measured


DATA_PATH = Path(__file__).parent / "data" / "synthetic_tickets.json"
BANKING77_DATA_PATH = Path(__file__).parent / "data" / "banking77_test_subset.json"
DEFAULT_JSON_PATH = Path(__file__).parent / "benchmark-report.json"
DEFAULT_MARKDOWN_PATH = Path(__file__).parent / "benchmark-report.md"
BANKING77_JSON_PATH = Path(__file__).parent / "banking77-benchmark-report.json"
BANKING77_MARKDOWN_PATH = Path(__file__).parent / "banking77-benchmark-report.md"

MINIMUM_FIELDS = ("issue_description", "product_area", "urgency")
STRUCTURED_PII_FIELDS = {
    "name",
    "email",
    "phone",
    "date_of_birth",
    "address",
    "account_id",
}
VARIANT_NAMES = (
    "full_context",
    "masking_only",
    "minimum_context",
    "minimum_plus_masking",
)


@dataclass(frozen=True)
class CorpusProfile:
    name: str
    data_path: Path
    labels: tuple[str, ...]
    minimum_fields: tuple[str, ...]
    task_name: str
    description: str
    public_source_data: bool
    synthetic_identity_overlay: bool
    fully_synthetic: bool
    source_url: str
    license: str
    limitations: tuple[str, ...]


CORPUS_PROFILES = {
    "synthetic": CorpusProfile(
        name="synthetic",
        data_path=DATA_PATH,
        labels=tuple(QUEUES),
        minimum_fields=tuple(MINIMUM_FIELDS),
        task_name="support ticket router",
        description="16 synthetic support-ticket routing cases",
        public_source_data=False,
        synthetic_identity_overlay=False,
        fully_synthetic=True,
        source_url="",
        license="",
        limitations=(
            "The corpus is small, synthetic, and specific to support-ticket routing.",
            "The same engineering corpus was used to design and evaluate the allowlist; there is no independent holdout set yet.",
        ),
    ),
    "banking77": CorpusProfile(
        name="banking77",
        data_path=BANKING77_DATA_PATH,
        labels=tuple(BANKING77_INTENTS),
        minimum_fields=("issue_description",),
        task_name="banking support intent classifier",
        description="Fixed 50-case subset of the public BANKING77 test split",
        public_source_data=True,
        synthetic_identity_overlay=True,
        fully_synthetic=False,
        source_url=BANKING77_SOURCE_URL,
        license=BANKING77_LICENSE,
        limitations=(
            "This is a fixed 50-case, 10-intent BANKING77-derived subset evaluation, not a full BANKING77 benchmark result.",
            "The support queries and intent labels come from BANKING77; all structured identity fields are synthetic overlays.",
            "The minimum-context allowlist was designed before this public holdout evaluation.",
            "BANKING77 is public, so possible model pretraining exposure is unknown; this run measures relative context effects, not uncontaminated generalization.",
        ),
    ),
}


def get_corpus_profile(name: str) -> CorpusProfile:
    try:
        return CORPUS_PROFILES[name]
    except KeyError as exc:
        raise ValueError(f"Unknown corpus profile: {name}") from exc


def get_default_report_paths(corpus_name: str) -> tuple[Path, Path]:
    if corpus_name == "banking77":
        return BANKING77_JSON_PATH, BANKING77_MARKDOWN_PATH
    return DEFAULT_JSON_PATH, DEFAULT_MARKDOWN_PATH


@dataclass(frozen=True)
class Observation:
    ticket_id: str
    prediction: str
    expected: str
    input_tokens: int
    token_source: str
    payload: Dict[str, str]
    raw_structured_pii_values_sent: int
    prompt: str = ""


class RecordMasker(Protocol):
    name: str

    def mask_record(self, record: Mapping[str, str]) -> Dict[str, str]:
        """Return a masked copy of the outgoing record."""


class StructuredFieldMasker:
    """Mask values already classified as structured PII.

    This deterministic baseline does not detect PII in free text and must not
    be presented as an OpenAI Privacy Filter result.
    """

    name = "structured_field_masking"

    def mask_record(self, record: Mapping[str, str]) -> Dict[str, str]:
        return {
            field: f"[MASKED:{field}]" if field in STRUCTURED_PII_FIELDS else value
            for field, value in record.items()
        }


def replace_spans(text: str, spans: Iterable[Mapping[str, Any]]) -> str:
    """Replace detected spans while preserving offsets from the original text."""
    result = text
    valid_spans = []
    for span in spans:
        start = int(span["start"])
        end = int(span["end"])
        if 0 <= start < end <= len(text):
            valid_spans.append((start, end, str(span.get("entity_group", "pii"))))
    for start, end, label in sorted(valid_spans, reverse=True):
        result = result[:start] + f"[MASKED:{label}]" + result[end:]
    return result


class OpenAIPrivacyFilterMasker:
    """Optional adapter for the actual openai/privacy-filter model."""

    name = "openai_privacy_filter"

    def __init__(self) -> None:
        try:
            from transformers import pipeline
        except ImportError as exc:
            raise RuntimeError(
                "The OPF adapter requires: pip install -r poc/requirements-opf.txt"
            ) from exc
        self._classifier = pipeline(
            task="token-classification",
            model="openai/privacy-filter",
        )

    def mask_record(self, record: Mapping[str, str]) -> Dict[str, str]:
        masked = {}
        for field, value in record.items():
            spans = self._classifier(value, aggregation_strategy="simple")
            masked[field] = replace_spans(value, spans)
        return masked


def load_tickets(path: Path = DATA_PATH) -> List[Dict[str, str]]:
    return json.loads(path.read_text(encoding="utf-8"))


def full_payload(ticket: Mapping[str, str]) -> Dict[str, str]:
    return {field: ticket[field] for field in FIELDS if field in ticket}


def minimum_payload(
    ticket: Mapping[str, str],
    minimum_fields: Iterable[str] = MINIMUM_FIELDS,
) -> Dict[str, str]:
    return {field: ticket[field] for field in minimum_fields if field in ticket}


def build_variant_payloads(
    ticket: Mapping[str, str],
    masker: RecordMasker,
    minimum_fields: Iterable[str] = MINIMUM_FIELDS,
) -> "OrderedDict[str, Dict[str, str]]":
    full = full_payload(ticket)
    minimum = minimum_payload(ticket, minimum_fields)
    return OrderedDict(
        [
            ("full_context", full),
            ("masking_only", masker.mask_record(full)),
            ("minimum_context", minimum),
            ("minimum_plus_masking", masker.mask_record(minimum)),
        ]
    )


def count_raw_structured_pii_values(
    source_ticket: Mapping[str, str],
    outgoing_payload: Mapping[str, str],
) -> int:
    return sum(
        field in outgoing_payload
        and field in source_ticket
        and outgoing_payload[field] == source_ticket[field]
        for field in STRUCTURED_PII_FIELDS
    )


def _reduction(value: int, baseline: int) -> float:
    if baseline == 0:
        return 0.0
    return round(1 - (value / baseline), 6)


def calculate_variant_metrics(
    observations: Mapping[str, List[Observation]],
) -> Dict[str, Dict[str, Any]]:
    full_runs = observations["full_context"]
    full_predictions = [item.prediction for item in full_runs]
    full_tokens = sum(item.input_tokens for item in full_runs)
    full_fields = sum(len(item.payload) for item in full_runs)
    full_raw_pii = sum(item.raw_structured_pii_values_sent for item in full_runs)
    full_correct = sum(item.prediction == item.expected for item in full_runs)

    metrics: Dict[str, Dict[str, Any]] = {}
    for variant, runs in observations.items():
        correct = sum(item.prediction == item.expected for item in runs)
        tokens = sum(item.input_tokens for item in runs)
        fields = sum(len(item.payload) for item in runs)
        raw_pii = sum(item.raw_structured_pii_values_sent for item in runs)
        changes = sum(
            item.prediction != full_prediction
            for item, full_prediction in zip(runs, full_predictions)
        )
        improvements = sum(
            full_item.prediction != full_item.expected
            and item.prediction == item.expected
            for item, full_item in zip(runs, full_runs)
        )
        regressions = sum(
            full_item.prediction == full_item.expected
            and item.prediction != item.expected
            for item, full_item in zip(runs, full_runs)
        )
        other_changes = sum(
            item.prediction != full_item.prediction
            and (item.prediction == item.expected)
            == (full_item.prediction == full_item.expected)
            for item, full_item in zip(runs, full_runs)
        )
        total = len(runs)
        metrics[variant] = {
            "correct": correct,
            "total": total,
            "accuracy": round(correct / total, 6) if total else 0.0,
            "decision_changes_vs_full": changes,
            "improvements_vs_full": improvements,
            "regressions_vs_full": regressions,
            "other_changes_vs_full": other_changes,
            "decision_stability_vs_full": round(1 - (changes / total), 6) if total else 0.0,
            "input_tokens": tokens,
            "token_reduction_vs_full": _reduction(tokens, full_tokens),
            "field_instances_sent": fields,
            "field_reduction_vs_full": _reduction(fields, full_fields),
            "raw_structured_pii_values_sent": raw_pii,
            "raw_structured_pii_reduction_vs_full": _reduction(raw_pii, full_raw_pii),
            "accepted_without_review": changes == 0 and correct >= full_correct,
        }
    return metrics


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _resolve_engine(engine: str) -> bool:
    if engine == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("--engine openai requires OPENAI_API_KEY")
        return True
    if engine == "offline":
        return False
    return bool(os.environ.get("OPENAI_API_KEY"))


def _make_masker(masker_name: str) -> RecordMasker:
    if masker_name == "opf":
        return OpenAIPrivacyFilterMasker()
    return StructuredFieldMasker()


def run_benchmark(
    model: str = "gpt-4o-mini",
    engine: str = "auto",
    masker_name: str = "structured",
    data_path: Path | None = None,
    corpus_name: str = "synthetic",
) -> Dict[str, Any]:
    profile = get_corpus_profile(corpus_name)
    effective_data_path = data_path or profile.data_path
    tickets = load_tickets(effective_data_path)
    use_openai = _resolve_engine(engine)
    masker = _make_masker(masker_name)
    observations: Dict[str, List[Observation]] = {name: [] for name in VARIANT_NAMES}

    for ticket in tickets:
        for variant, outgoing_payload in build_variant_payloads(
            ticket,
            masker,
            minimum_fields=profile.minimum_fields,
        ).items():
            result = classify_measured(
                outgoing_payload,
                model=model,
                use_openai=use_openai,
                labels=profile.labels,
                task_name=profile.task_name,
            )
            observations[variant].append(
                Observation(
                    ticket_id=ticket["id"],
                    prediction=result.prediction,
                    expected=ticket["expected_queue"],
                    input_tokens=result.input_tokens,
                    token_source=result.token_source,
                    payload=outgoing_payload,
                    raw_structured_pii_values_sent=count_raw_structured_pii_values(
                        ticket,
                        outgoing_payload,
                    ),
                    prompt=_build_prompt(
                        outgoing_payload,
                        labels=profile.labels,
                        task_name=profile.task_name,
                    ),
                )
            )

    serialised_observations = {
        variant: [asdict(item) for item in runs]
        for variant, runs in observations.items()
    }
    evidence_level = "real_model_run" if use_openai else "technical_dry_run"
    limitations = [
        *profile.limitations,
        "Results are bounded to this corpus, prompt, model configuration, and run.",
        "No result is a legal conclusion or a universal proof that a field never matters.",
    ]
    if not use_openai:
        limitations.append(
            "The offline classifier is deterministic plumbing validation, not evidence about an LLM's data needs."
        )
        if profile.name == "banking77":
            limitations.append(
                "The offline classifier does not implement BANKING77 intent labels, so its accuracy is not a task result."
            )
    if masker.name == "structured_field_masking":
        limitations.append(
            "The masking condition uses declared structured fields and is not an OpenAI Privacy Filter evaluation."
        )

    token_sources = sorted(
        {
            item.token_source
            for runs in observations.values()
            for item in runs
        }
    )
    metrics = calculate_variant_metrics(observations)
    if not use_openai:
        for metric in metrics.values():
            metric["accepted_without_review"] = False
    return {
        "run": {
            "corpus_name": profile.name,
            "corpus_description": profile.description,
            "public_source_data": profile.public_source_data,
            "synthetic_identity_overlay": profile.synthetic_identity_overlay,
            "fully_synthetic": profile.fully_synthetic,
            "source_url": profile.source_url,
            "license": profile.license,
            "labels": list(profile.labels),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "evidence_level": evidence_level,
            "engine": f"openai:{model}" if use_openai else "offline_rule_based",
            "model": model if use_openai else None,
            "masker": masker.name,
            "test_set_size": len(tickets),
            "corpus": str(effective_data_path),
            "corpus_sha256": _sha256_bytes(effective_data_path.read_bytes()),
            "prompt_sha256": _sha256_bytes(
                _build_prompt(
                    {},
                    labels=profile.labels,
                    task_name=profile.task_name,
                ).encode("utf-8")
            ),
            "token_sources": token_sources,
            "synthetic_data": profile.fully_synthetic,
        },
        "variant_definitions": {
            "full_context": "All declared record fields.",
            "masking_only": "Full record with the selected masking layer applied.",
            "minimum_context": f"Only the allowlisted fields: {', '.join(profile.minimum_fields)}.",
            "minimum_plus_masking": "Minimum context with the selected masking layer applied to remaining text.",
        },
        "metrics": metrics,
        "observations": serialised_observations,
        "limitations": limitations,
    }


def _percent(value: float) -> str:
    return f"{value:.1%}"


def render_markdown(report: Mapping[str, Any]) -> str:
    run = report["run"]
    if run["evidence_level"] == "technical_dry_run":
        banner = "> **TECHNICAL DRY RUN:** This validates the benchmark plumbing. It is not LLM evidence."
    else:
        banner = "> **REAL MODEL RUN:** Metrics below were recorded from the declared API execution."

    masker_note = ""
    if run["masker"] == "structured_field_masking":
        masker_note = (
            "\n> The masking condition is a structured-field baseline. "
            "It is not an OpenAI Privacy Filter evaluation.\n"
        )
    elif run["masker"] == "openai_privacy_filter":
        masker_note = "\n> The masking conditions use `openai/privacy-filter`.\n"

    provenance_lines = []
    if run.get("corpus_description"):
        provenance_lines.append(f"- Corpus: {run['corpus_description']}")
    if run.get("public_source_data"):
        provenance_lines.extend(
            [
                f"- Public source: {run['source_url']}",
                f"- Dataset license: `{run['license']}`",
            ]
        )
    if run.get("synthetic_identity_overlay"):
        provenance_lines.append(
            "- Data provenance: Public queries and original labels with a synthetic structured identity overlay"
        )
    elif run.get("fully_synthetic"):
        provenance_lines.append("- Data provenance: Fully synthetic records and labels")

    lines = [
        "# Necessity Certificate Benchmark Report",
        "",
        banner,
        masker_note.rstrip(),
        "",
        "## Run metadata",
        "",
        f"- Generated: `{run['generated_at']}`",
        f"- Engine: `{run['engine']}`",
        f"- Model: `{run.get('model') or 'not applicable'}`",
        f"- Masker: `{run['masker']}`",
        f"- Evaluation cases: `{run['test_set_size']}`",
        *provenance_lines,
        f"- Corpus SHA-256: `{run['corpus_sha256']}`",
        f"- Prompt SHA-256: `{run['prompt_sha256']}`",
        "",
        "## Results",
        "",
        "| Variant | Correct | Accuracy | Changes vs full | Improvements | Regressions | Input tokens | Token reduction | Field reduction | Raw structured PII sent | Raw PII reduction | Accepted |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|",
    ]
    labels = {
        "full_context": "Full context",
        "masking_only": "Masking only",
        "minimum_context": "Minimum context",
        "minimum_plus_masking": "Minimum + masking",
    }
    for variant, metric in report["metrics"].items():
        lines.append(
            "| {label} | {correct}/{total} | {accuracy} | {changes} | {improvements} | {regressions} | {tokens} | {token_reduction} | {field_reduction} | {raw_pii} | {pii_reduction} | {accepted} |".format(
                label=labels.get(variant, variant),
                correct=metric["correct"],
                total=metric["total"],
                accuracy=_percent(metric["accuracy"]),
                changes=metric["decision_changes_vs_full"],
                improvements=metric.get("improvements_vs_full", 0),
                regressions=metric.get("regressions_vs_full", 0),
                tokens=metric["input_tokens"],
                token_reduction=_percent(metric["token_reduction_vs_full"]),
                field_reduction=_percent(metric["field_reduction_vs_full"]),
                raw_pii=metric["raw_structured_pii_values_sent"],
                pii_reduction=_percent(metric["raw_structured_pii_reduction_vs_full"]),
                accepted="yes" if metric["accepted_without_review"] else "review",
            )
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `minimum_context` versus `full_context` measures the contribution of purpose-specific minimization.",
            "- `minimum_plus_masking` versus `masking_only` measures the additional reduction from minimization when a masking layer is already present.",
            "- A minimized condition is accepted without review only when it causes zero individual decision changes and does not reduce ground-truth correctness.",
            "- Improvements and regressions distinguish beneficial decision changes from harmful ones; the strict no-change rule still routes every change to review.",
            "",
            "## Limitations",
            "",
        ]
    )
    lines.extend(f"- {limitation}" for limitation in report["limitations"])
    lines.append("")
    return "\n".join(line for line in lines if line is not None)


def write_reports(
    report: Mapping[str, Any],
    json_path: Path,
    markdown_path: Path,
) -> None:
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument(
        "--corpus",
        choices=tuple(CORPUS_PROFILES),
        default="synthetic",
        help="select the fully synthetic demo or public BANKING77-derived subset",
    )
    parser.add_argument(
        "--engine",
        choices=("auto", "offline", "openai"),
        default="auto",
        help="auto uses OpenAI only when OPENAI_API_KEY is set",
    )
    parser.add_argument(
        "--masker",
        choices=("structured", "opf"),
        default="structured",
        help="opf loads the actual openai/privacy-filter model",
    )
    parser.add_argument("--data", type=Path)
    parser.add_argument("--out-json", type=Path)
    parser.add_argument("--out-markdown", type=Path)
    args = parser.parse_args()

    default_json_path, default_markdown_path = get_default_report_paths(args.corpus)
    json_path = args.out_json or default_json_path
    markdown_path = args.out_markdown or default_markdown_path

    report = run_benchmark(
        model=args.model,
        engine=args.engine,
        masker_name=args.masker,
        data_path=args.data,
        corpus_name=args.corpus,
    )
    write_reports(report, json_path, markdown_path)
    print(render_markdown(report))
    print(f"JSON evidence written to {json_path}")
    print(f"Markdown certificate written to {markdown_path}")


if __name__ == "__main__":
    main()
