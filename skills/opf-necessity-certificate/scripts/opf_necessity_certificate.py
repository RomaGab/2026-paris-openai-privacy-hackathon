"""Orchestrate field necessity tests with the actual OpenAI Privacy Filter."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence


OPF_MODEL_ID = "openai/privacy-filter"
VARIANT_NAMES = (
    "full_context",
    "opf_only",
    "minimum_context",
    "minimum_plus_opf",
)
PRIVACY_COSTS = {
    "task-relevant, not personal",
    "quasi-identifier",
    "direct identifier",
    "sensitive numeric",
}

_DIRECT_ID = re.compile(
    r"(name|e_?mail|phone|mobile|ssn|passport|address|street|iban|"
    r"account_(id|number)|customer_id|user_id|card_number|national_id)",
    re.IGNORECASE,
)
_QUASI_ID = re.compile(
    r"(date_of_birth|dob|birth|zip|postal|gender|nationality|city|region|"
    r"ip_address|device_id|^age$|_age$)",
    re.IGNORECASE,
)
_SENSITIVE_NUMERIC = re.compile(
    r"(salary|income|balance|credit_score|health|diagnosis|amount_owed)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CertificateConfig:
    purpose: str
    label_field: str
    label_values: tuple[str, ...]
    task_model: str = "gpt-4o-mini"
    engine: str = "openai"
    privacy_cost_overrides: Mapping[str, str] | None = None


@dataclass(frozen=True)
class Decision:
    prediction: str
    input_tokens: int
    token_source: str


@dataclass(frozen=True)
class MaskingResult:
    record: dict[str, Any]
    spans: list[dict[str, Any]]


class Predictor(Protocol):
    name: str
    evidence_level: str

    def predict(self, payload: Mapping[str, Any], config: CertificateConfig) -> Decision:
        """Return one task decision and its input-token accounting."""


class Masker(Protocol):
    model_id: str
    requested_revision: str | None
    resolved_revision: str | None
    evidence_level: str
    runtime: Mapping[str, str]

    def mask_record(self, record: Mapping[str, Any]) -> MaskingResult:
        """Mask one outgoing record and return non-content span metadata."""


def classify_privacy_cost(field: str, overrides: Mapping[str, str]) -> str:
    if field in overrides:
        return overrides[field]
    if _DIRECT_ID.search(field):
        return "direct identifier"
    if _QUASI_ID.search(field):
        return "quasi-identifier"
    if _SENSITIVE_NUMERIC.search(field):
        return "sensitive numeric"
    return "task-relevant, not personal"


def parse_schema(ddl: str) -> tuple[str, str, list[str]]:
    without_comments = "\n".join(
        line for line in ddl.splitlines() if not line.strip().startswith("--")
    )
    match = re.search(
        r"CREATE\s+TABLE\s+(\w+)\s*\((.*)\)\s*;?\s*$",
        without_comments,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        raise ValueError("Expected exactly one CREATE TABLE statement")
    table_name, body = match.group(1), match.group(2)
    columns: list[str] = []
    for raw_line in body.splitlines():
        line = raw_line.strip().rstrip(",")
        if not line or line.upper().startswith(
            ("PRIMARY KEY", "FOREIGN KEY", "UNIQUE", "CHECK", "CONSTRAINT")
        ):
            continue
        columns.append(line.split()[0].strip('"'))
    if not columns:
        raise ValueError("No columns found in CREATE TABLE statement")
    return table_name, columns[0], columns


def _replace_spans(text: str, spans: Iterable[Mapping[str, Any]]) -> str:
    replacements: list[tuple[int, int, str]] = []
    for span in spans:
        start = int(span.get("start", -1))
        end = int(span.get("end", -1))
        label = str(span.get("entity_group") or span.get("entity") or "PII")
        if 0 <= start < end <= len(text):
            replacements.append((start, end, label))
    result = text
    for start, end, label in sorted(replacements, reverse=True):
        result = result[:start] + f"[MASKED:{label}]" + result[end:]
    return result


class OpenAIPrivacyFilterMasker:
    """Fail-closed adapter for the actual openai/privacy-filter model."""

    model_id = OPF_MODEL_ID
    evidence_level = "actual_opf_model"

    def __init__(
        self,
        revision: str | None = None,
        pipeline_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.requested_revision = revision
        if pipeline_factory is None:
            try:
                import torch
                import transformers
            except ImportError as exc:
                raise RuntimeError(
                    "openai/privacy-filter requires Transformers and PyTorch; "
                    "install references/requirements.txt"
                ) from exc
            pipeline_factory = transformers.pipeline
            self.runtime = {
                "transformers": transformers.__version__,
                "torch": torch.__version__,
            }
        else:
            self.runtime = {"transformers": "injected", "torch": "injected"}

        kwargs: dict[str, Any] = {
            "task": "token-classification",
            "model": self.model_id,
        }
        if revision:
            kwargs["revision"] = revision
        try:
            self._classifier = pipeline_factory(**kwargs)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load actual {self.model_id}; no fallback masker was used: {exc}"
            ) from exc

        model = getattr(self._classifier, "model", None)
        config = getattr(model, "config", None)
        self.resolved_revision = (
            getattr(config, "_commit_hash", None)
            or revision
            or "unresolved"
        )

    def mask_record(self, record: Mapping[str, Any]) -> MaskingResult:
        masked: dict[str, Any] = {}
        span_metadata: list[dict[str, Any]] = []
        for field, value in record.items():
            if not isinstance(value, str) or not value:
                masked[field] = value
                continue
            raw_spans = self._classifier(value, aggregation_strategy="simple")
            normalized: list[dict[str, Any]] = []
            for span in raw_spans:
                label = str(span.get("entity_group") or span.get("entity") or "PII")
                normalized.append(dict(span))
                span_metadata.append(
                    {
                        "field": field,
                        "label": label,
                        "score": round(float(span.get("score", 0.0)), 6),
                    }
                )
            masked[field] = _replace_spans(value, normalized)
        return MaskingResult(record=masked, spans=span_metadata)


def infer_label_values(
    records: Sequence[Mapping[str, Any]], label_field: str
) -> tuple[str, ...]:
    labels: list[str] = []
    seen: set[str] = set()
    for record in records:
        if label_field not in record:
            raise ValueError(f"Every record must contain label field '{label_field}'")
        label = str(record[label_field])
        if label not in seen:
            labels.append(label)
            seen.add(label)
    if not labels:
        raise ValueError("At least one label value is required")
    return tuple(labels)


def _build_prompt(payload: Mapping[str, Any], config: CertificateConfig) -> str:
    fields = "\n".join(
        f"- {field}: {value}" for field, value in payload.items() if value is not None
    )
    labels = ", ".join(config.label_values)
    return (
        f"Perform this declared task: {config.purpose}\n"
        f"Reply with exactly one label from this list: {labels}. "
        "Reply with the label only.\n\n"
        f"Fields:\n{fields}"
    )


def _extract_label(text: str, labels: Sequence[str]) -> str:
    normalized = text.strip().lower()
    canonical = {label.lower(): label for label in labels}
    if normalized in canonical:
        return canonical[normalized]
    for label in sorted(labels, key=len, reverse=True):
        pattern = rf"(?<![a-z0-9_]){re.escape(label.lower())}(?![a-z0-9_])"
        if re.search(pattern, normalized):
            return label
    return "__invalid__"


def _count_tokens(text: str, model: str) -> tuple[int, str]:
    try:
        import tiktoken

        try:
            encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text)), "tiktoken"
    except Exception:
        return len(text.split()), "whitespace_estimate"


class OpenAIPredictor:
    evidence_level = "real_model_run"

    def __init__(self, model: str) -> None:
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("--engine openai requires OPENAI_API_KEY")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("The OpenAI engine requires the openai Python package") from exc
        self.model = model
        self.name = f"openai:{model}"
        self._client = OpenAI()

    def predict(self, payload: Mapping[str, Any], config: CertificateConfig) -> Decision:
        prompt = _build_prompt(payload, config)
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        text = (response.choices[0].message.content or "").strip()
        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        if prompt_tokens is None:
            token_count, token_source = _count_tokens(prompt, self.model)
        else:
            token_count, token_source = int(prompt_tokens), "api_usage"
        return Decision(
            prediction=_extract_label(text, config.label_values),
            input_tokens=token_count,
            token_source=token_source,
        )


class OfflineLabelTokenPredictor:
    """Deterministic plumbing check that must never be presented as model evidence."""

    name = "offline_label_token_matcher"
    evidence_level = "technical_dry_run"

    def predict(self, payload: Mapping[str, Any], config: CertificateConfig) -> Decision:
        prompt = _build_prompt(payload, config)
        searchable = " ".join(str(value) for value in payload.values()).lower()
        prediction = config.label_values[0]
        for label in config.label_values:
            words = re.findall(r"[a-z0-9]+", label.lower())
            if words and all(word in searchable for word in words):
                prediction = label
                break
        token_count, token_source = _count_tokens(prompt, config.task_model)
        return Decision(prediction, token_count, token_source)


def create_predictor(
    config: CertificateConfig, engine: str | None = None
) -> Predictor:
    selected = engine or config.engine
    if selected == "openai":
        return OpenAIPredictor(config.task_model)
    if selected == "offline":
        return OfflineLabelTokenPredictor()
    raise ValueError(f"Unknown engine: {selected}")


def _sha256_json(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_inputs(
    config: CertificateConfig,
    schema_sql: str,
    records: Sequence[Mapping[str, Any]],
) -> tuple[str, str, list[str], dict[str, str]]:
    if not config.purpose.strip():
        raise ValueError("Declared purpose must be non-empty")
    if not records:
        raise ValueError("Dataset must be a non-empty JSON array")
    table_name, primary_key, columns = parse_schema(schema_sql)
    if config.label_field not in columns:
        raise ValueError(f"Label field '{config.label_field}' is absent from the schema")
    missing_labels = [index for index, row in enumerate(records) if config.label_field not in row]
    if missing_labels:
        raise ValueError(f"Every record must contain label field '{config.label_field}'")
    observed_labels = {str(row[config.label_field]) for row in records}
    if not config.label_values:
        raise ValueError("At least one label value is required")
    unknown_labels = observed_labels.difference(config.label_values)
    if unknown_labels:
        raise ValueError(f"Observed labels are absent from label_values: {sorted(unknown_labels)}")
    overrides = dict(config.privacy_cost_overrides or {})
    unknown_fields = set(overrides).difference(columns)
    if unknown_fields:
        raise ValueError(f"Privacy overrides reference unknown fields: {sorted(unknown_fields)}")
    invalid_costs = {value for value in overrides.values() if value not in PRIVACY_COSTS}
    if invalid_costs:
        raise ValueError(f"Invalid privacy-cost categories: {sorted(invalid_costs)}")
    return table_name, primary_key, columns, overrides


def _payload(record: Mapping[str, Any], fields: Sequence[str]) -> dict[str, Any]:
    return {field: record.get(field) for field in fields}


def evaluate_records(
    records: Sequence[Mapping[str, Any]],
    fields: Sequence[str],
    config: CertificateConfig,
    predictor: Predictor,
    masker: Masker | None = None,
    privacy_cost_overrides: Mapping[str, str] | None = None,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    observations: list[dict[str, Any]] = []
    span_categories: Counter[str] = Counter()
    overrides = privacy_cost_overrides or {}
    for index, source_record in enumerate(records, start=1):
        source_payload = _payload(source_record, fields)
        outgoing = source_payload
        spans: list[dict[str, Any]] = []
        if masker is not None:
            result = masker.mask_record(source_payload)
            outgoing = result.record
            spans = result.spans
            span_categories.update(str(span.get("label", "PII")) for span in spans)
        decision = predictor.predict(outgoing, config)
        residual_personal_fields = sum(
            classify_privacy_cost(field, overrides) != "task-relevant, not personal"
            and outgoing.get(field) == source_payload.get(field)
            and source_payload.get(field) is not None
            for field in fields
        )
        observations.append(
            {
                "case_id": f"case_{index:04d}",
                "prediction": decision.prediction,
                "expected": str(source_record[config.label_field]),
                "input_tokens": int(decision.input_tokens),
                "token_source": decision.token_source,
                "field_count": len(fields),
                "residual_personal_fields": residual_personal_fields,
                "detected_spans": len(spans),
            }
        )
    return observations, span_categories


def _reduction(value: int, baseline: int) -> float:
    return round(1 - (value / baseline), 6) if baseline else 0.0


def calculate_variant_metrics(
    observations: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, dict[str, Any]]:
    full = observations["full_context"]
    full_tokens = sum(int(item["input_tokens"]) for item in full)
    full_fields = sum(int(item["field_count"]) for item in full)
    full_personal = sum(int(item["residual_personal_fields"]) for item in full)
    metrics: dict[str, dict[str, Any]] = {}
    for name in VARIANT_NAMES:
        runs = observations[name]
        correct = sum(item["prediction"] == item["expected"] for item in runs)
        changes = sum(
            item["prediction"] != base["prediction"]
            for item, base in zip(runs, full)
        )
        improvements = sum(
            base["prediction"] != base["expected"]
            and item["prediction"] == item["expected"]
            for item, base in zip(runs, full)
        )
        regressions = sum(
            base["prediction"] == base["expected"]
            and item["prediction"] != item["expected"]
            for item, base in zip(runs, full)
        )
        other_changes = changes - improvements - regressions
        tokens = sum(int(item["input_tokens"]) for item in runs)
        fields = sum(int(item["field_count"]) for item in runs)
        residual_personal = sum(int(item["residual_personal_fields"]) for item in runs)
        detected_spans = sum(int(item["detected_spans"]) for item in runs)
        total = len(runs)
        token_sources = sorted({str(item["token_source"]) for item in runs})
        metrics[name] = {
            "correct": correct,
            "total": total,
            "accuracy": round(correct / total, 6) if total else 0.0,
            "decision_changes_vs_full": changes,
            "improvements_vs_full": improvements,
            "regressions_vs_full": regressions,
            "other_changes_vs_full": other_changes,
            "decision_stability_vs_full": round(1 - (changes / total), 6) if total else 0.0,
            "input_tokens": tokens,
            "token_sources": token_sources,
            "token_reduction_vs_full": _reduction(tokens, full_tokens),
            "field_instances_sent": fields,
            "field_reduction_vs_full": _reduction(fields, full_fields),
            "residual_personal_fields": residual_personal,
            "residual_personal_field_reduction_vs_full": _reduction(
                residual_personal, full_personal
            ),
            "opf_detected_spans": detected_spans,
        }
    return metrics


def _field_evidence(
    field: str,
    full: Sequence[Mapping[str, Any]],
    without: Sequence[Mapping[str, Any]],
    privacy_cost: str,
) -> dict[str, Any]:
    full_correct = sum(item["prediction"] == item["expected"] for item in full)
    without_correct = sum(item["prediction"] == item["expected"] for item in without)
    total = len(full)
    changes = sum(
        item["prediction"] != base["prediction"]
        for item, base in zip(without, full)
    )
    improvements = sum(
        base["prediction"] != base["expected"]
        and item["prediction"] == item["expected"]
        for item, base in zip(without, full)
    )
    regressions = sum(
        base["prediction"] == base["expected"]
        and item["prediction"] != item["expected"]
        for item, base in zip(without, full)
    )
    return {
        "field": field,
        "privacy_cost": privacy_cost,
        "decision": "drop_candidate" if changes == 0 else "retained_pending_review",
        "decision_changes": changes,
        "improvements": improvements,
        "regressions": regressions,
        "other_changes": changes - improvements - regressions,
        "accuracy_with_field": round(full_correct / total, 6) if total else 0.0,
        "accuracy_without_field": round(without_correct / total, 6) if total else 0.0,
        "tokens_saved_if_dropped": sum(int(item["input_tokens"]) for item in full)
        - sum(int(item["input_tokens"]) for item in without),
        "review_reason": (
            "No individual decision changed in this single-field ablation."
            if changes == 0
            else "At least one individual decision changed; retain until human review."
        ),
    }


def run_certificate(
    config: CertificateConfig,
    schema_sql: str,
    records: Sequence[Mapping[str, Any]],
    predictor: Predictor,
    masker: Masker,
) -> dict[str, Any]:
    table_name, primary_key, columns, overrides = _validate_inputs(
        config, schema_sql, records
    )
    input_fields = [
        field
        for field in columns
        if field not in {primary_key, config.label_field}
    ]
    if not input_fields:
        raise ValueError("Schema must contain at least one model input field")

    full, _ = evaluate_records(
        records, input_fields, config, predictor, privacy_cost_overrides=overrides
    )
    field_evidence: list[dict[str, Any]] = []
    for field in input_fields:
        remaining = [candidate for candidate in input_fields if candidate != field]
        without, _ = evaluate_records(
            records, remaining, config, predictor, privacy_cost_overrides=overrides
        )
        field_evidence.append(
            _field_evidence(
                field,
                full,
                without,
                classify_privacy_cost(field, overrides),
            )
        )

    minimum_fields = [
        item["field"]
        for item in field_evidence
        if item["decision"] == "retained_pending_review"
    ]
    opf_only, full_span_categories = evaluate_records(
        records,
        input_fields,
        config,
        predictor,
        masker=masker,
        privacy_cost_overrides=overrides,
    )
    minimum, _ = evaluate_records(
        records, minimum_fields, config, predictor, privacy_cost_overrides=overrides
    )
    minimum_plus_opf, minimum_span_categories = evaluate_records(
        records,
        minimum_fields,
        config,
        predictor,
        masker=masker,
        privacy_cost_overrides=overrides,
    )
    observations = {
        "full_context": full,
        "opf_only": opf_only,
        "minimum_context": minimum,
        "minimum_plus_opf": minimum_plus_opf,
    }
    metrics = calculate_variant_metrics(observations)
    candidate = metrics["minimum_plus_opf"]
    real_evidence = (
        predictor.evidence_level == "real_model_run"
        and masker.evidence_level == "actual_opf_model"
        and masker.model_id == OPF_MODEL_ID
    )
    accepted = (
        real_evidence
        and candidate["decision_changes_vs_full"] == 0
        and candidate["accuracy"] >= metrics["full_context"]["accuracy"]
        and candidate["residual_personal_fields"] == 0
    )
    status = "accepted_without_review" if accepted else "review_required"

    prompt_contract = {
        "purpose": config.purpose,
        "label_field": config.label_field,
        "label_values": list(config.label_values),
        "input_fields": input_fields,
    }
    limitations = [
        "This report is empirical evidence for one declared purpose, dataset, prompt contract, model, and run.",
        "It is not a legal compliance decision or a universal proof that a field never matters.",
        "Single-field ablation can miss interactions between fields; the minimum-context branch tests their combined removal.",
        "OPF span counts measure detected entities, not guaranteed removal of every possible identifier.",
        "Raw record values, prompts, and detected PII text are intentionally omitted from the evidence artifacts.",
    ]
    if not real_evidence:
        limitations.insert(
            0,
            "Technical test fixture or offline predictor used; this run cannot be accepted without review.",
        )

    masking_description = (
        "actual OPF masking"
        if masker.evidence_level == "actual_opf_model" and masker.model_id == OPF_MODEL_ID
        else "an injected technical test masker"
    )
    return {
        "report_kind": "privacy_by_design_evidence",
        "status": status,
        "purpose": config.purpose,
        "table_name": table_name,
        "run": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "engine": config.engine,
            "predictor": predictor.name,
            "predictor_evidence_level": predictor.evidence_level,
            "task_model": config.task_model,
            "test_set_size": len(records),
            "corpus_sha256": _sha256_json(records),
            "schema_sha256": hashlib.sha256(schema_sql.encode("utf-8")).hexdigest(),
            "prompt_contract_sha256": _sha256_json(prompt_contract),
        },
        "opf": {
            "model_id": masker.model_id,
            "requested_revision": masker.requested_revision,
            "resolved_revision": masker.resolved_revision,
            "evidence_level": masker.evidence_level,
            "runtime": dict(masker.runtime),
            "detected_spans_full_context": sum(full_span_categories.values()),
            "detected_span_categories_full_context": dict(full_span_categories),
            "detected_spans_minimum_context": sum(minimum_span_categories.values()),
            "detected_span_categories_minimum_context": dict(minimum_span_categories),
        },
        "input_fields": input_fields,
        "minimum_fields": minimum_fields,
        "field_evidence": field_evidence,
        "benchmark": {
            "variant_definitions": {
                "full_context": "All declared input fields, without OPF.",
                "opf_only": f"All declared input fields after {masking_description}.",
                "minimum_context": "Only fields retained by the necessity test, without OPF.",
                "minimum_plus_opf": f"Necessity-minimized fields after {masking_description}.",
            },
            "variants": metrics,
        },
        "field_flow": {
            "full_context_fields": input_fields,
            "minimum_context_fields": minimum_fields,
            "raw_values_embedded": False,
        },
        "limitations": limitations,
    }


_VARIANT_LABELS = {
    "full_context": "Full context",
    "opf_only": "OPF only",
    "minimum_context": "Minimum context",
    "minimum_plus_opf": "Minimum + OPF",
}


def _percent(value: float) -> str:
    return f"{value:.1%}"


def render_markdown(report: Mapping[str, Any]) -> str:
    run = report["run"]
    opf = report["opf"]
    lines = [
        "# Privacy-by-Design Evidence Report",
        "",
        f"**Declared purpose:** {report['purpose']}",
        f"**Review status:** `{report['status']}`",
        f"**Evidence level:** `{run['predictor_evidence_level']}`",
        "",
        "This is engineering evidence for a DPIA or privacy review. It is not a legal compliance decision.",
        "",
        "## Four-condition benchmark",
        "",
        "| Variant | Accuracy | Changes | Improvements | Regressions | Input tokens | Token reduction | Field reduction | Residual personal fields | OPF spans |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, metric in report["benchmark"]["variants"].items():
        lines.append(
            f"| {_VARIANT_LABELS[name]} | {_percent(metric['accuracy'])} | "
            f"{metric['decision_changes_vs_full']} | {metric['improvements_vs_full']} | "
            f"{metric['regressions_vs_full']} | {metric['input_tokens']} | "
            f"{_percent(metric['token_reduction_vs_full'])} | "
            f"{_percent(metric['field_reduction_vs_full'])} | "
            f"{metric['residual_personal_fields']} | {metric['opf_detected_spans']} |"
        )
    lines.extend(
        [
            "",
            "## Field decisions",
            "",
            "| Field | Privacy cost | Decision | Changes | Accuracy without | Tokens saved | Review reason |",
            "|---|---|---|---:|---:|---:|---|",
        ]
    )
    for item in report["field_evidence"]:
        lines.append(
            f"| `{item['field']}` | {item['privacy_cost']} | `{item['decision']}` | "
            f"{item['decision_changes']} | {_percent(item['accuracy_without_field'])} | "
            f"{item['tokens_saved_if_dropped']} | {item['review_reason']} |"
        )
    lines.extend(
        [
            "",
            "## OPF provenance",
            "",
            f"- Model: `{opf['model_id']}`",
            f"- Requested revision: `{opf['requested_revision'] or 'default'}`",
            f"- Resolved revision: `{opf['resolved_revision']}`",
            f"- OPF evidence level: `{opf['evidence_level']}`",
            f"- Detected spans in full context: `{opf['detected_spans_full_context']}`",
            "",
            "## Reproducibility",
            "",
            f"- Corpus SHA-256: `{run['corpus_sha256']}`",
            f"- Schema SHA-256: `{run['schema_sha256']}`",
            f"- Prompt contract SHA-256: `{run['prompt_contract_sha256']}`",
            "",
            "## Limitations",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in report["limitations"])
    lines.append("")
    return "\n".join(lines)


def render_csv(report: Mapping[str, Any]) -> str:
    output = io.StringIO()
    fieldnames = [
        "field",
        "privacy_cost",
        "decision",
        "decision_changes",
        "improvements",
        "regressions",
        "accuracy_with_field",
        "accuracy_without_field",
        "tokens_saved_if_dropped",
        "review_reason",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(report["field_evidence"])
    return output.getvalue()


def render_sql(report: Mapping[str, Any]) -> str:
    decisions = {item["field"]: item for item in report["field_evidence"]}
    approved = [
        field
        for field in report["minimum_fields"]
        if decisions[field]["privacy_cost"] == "task-relevant, not personal"
    ]
    pending = [
        field
        for field in report["minimum_fields"]
        if field not in approved
    ]
    table = str(report["table_name"])
    comments = [
        "-- Fail-closed AI view derived from the measured field decisions.",
        "-- Personal retained fields stay blocked here until an OPF transform is enforced.",
    ]
    comments.extend(
        f"-- BLOCKED pending OPF transform: {field}" for field in pending
    )
    if approved:
        select_clause = ",\n    ".join(approved)
        query = (
            f"CREATE VIEW {table}_ai_view AS\n"
            f"SELECT\n    {select_clause}\n"
            f"FROM {table};"
        )
    else:
        query = (
            f"CREATE VIEW {table}_ai_view AS\n"
            "SELECT NULL AS no_approved_fields\n"
            f"FROM {table}\nWHERE FALSE;"
        )
    return "\n".join([*comments, query, ""])


def render_svg(report: Mapping[str, Any]) -> str:
    variants = report["benchmark"]["variants"]
    full_tokens = max(int(variants["full_context"]["input_tokens"]), 1)
    colors = ["#8b5cf6", "#3b82f6", "#14b8a6", "#22c55e"]
    rows: list[str] = []
    for index, name in enumerate(VARIANT_NAMES):
        metric = variants[name]
        y = 70 + (index * 82)
        accuracy_width = round(float(metric["accuracy"]) * 280, 2)
        token_width = round((int(metric["input_tokens"]) / full_tokens) * 280, 2)
        label = html.escape(_VARIANT_LABELS[name])
        rows.extend(
            [
                f'<text x="20" y="{y}" class="label">{label}</text>',
                f'<rect x="190" y="{y - 18}" width="{accuracy_width}" height="18" rx="5" fill="{colors[index]}"/>',
                f'<text x="480" y="{y - 4}" class="value">{_percent(metric["accuracy"])}</text>',
                f'<rect x="590" y="{y - 18}" width="{token_width}" height="18" rx="5" fill="{colors[index]}" opacity="0.72"/>',
                f'<text x="880" y="{y - 4}" text-anchor="end" class="value">{metric["input_tokens"]}</text>',
            ]
        )
    return "\n".join(
        [
            '<svg xmlns="http://www.w3.org/2000/svg" width="920" height="390" viewBox="0 0 920 390" role="img" aria-label="Accuracy and input token comparison">',
            "<style>.title{font:700 18px system-ui;fill:#f8fafc}.axis{font:600 12px system-ui;fill:#94a3b8}.label{font:600 13px system-ui;fill:#e2e8f0}.value{font:600 12px ui-monospace,monospace;fill:#cbd5e1}</style>",
            '<rect width="920" height="390" rx="18" fill="#0f172a"/>',
            '<text x="20" y="30" class="title">Measured utility and input volume</text>',
            '<text x="190" y="50" class="axis">Accuracy</text>',
            '<text x="590" y="50" class="axis">Input tokens</text>',
            *rows,
            "</svg>",
        ]
    )


def _template_path() -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / "report.html"


def render_html(report: Mapping[str, Any]) -> str:
    template = _template_path().read_text(encoding="utf-8")
    variants = report["benchmark"]["variants"]
    candidate = variants["minimum_plus_opf"]
    status_class = "accepted" if report["status"] == "accepted_without_review" else "review"
    summary_cards = "".join(
        [
            f'<article class="metric"><span>Baseline accuracy</span><strong>{_percent(variants["full_context"]["accuracy"])}</strong></article>',
            f'<article class="metric"><span>Combined token reduction</span><strong>{_percent(candidate["token_reduction_vs_full"])}</strong></article>',
            f'<article class="metric"><span>Combined field reduction</span><strong>{_percent(candidate["field_reduction_vs_full"])}</strong></article>',
            f'<article class="metric"><span>OPF detections</span><strong>{report["opf"]["detected_spans_full_context"]}</strong></article>',
        ]
    )
    variant_rows = []
    for name, metric in variants.items():
        variant_rows.append(
            "<tr>"
            f"<th>{html.escape(_VARIANT_LABELS[name])}</th>"
            f"<td>{_percent(metric['accuracy'])}</td>"
            f"<td>{metric['decision_changes_vs_full']}</td>"
            f"<td class=\"good\">{metric['improvements_vs_full']}</td>"
            f"<td class=\"bad\">{metric['regressions_vs_full']}</td>"
            f"<td>{metric['input_tokens']}</td>"
            f"<td>{_percent(metric['token_reduction_vs_full'])}</td>"
            f"<td>{_percent(metric['field_reduction_vs_full'])}</td>"
            f"<td>{metric['residual_personal_fields']}</td>"
            f"<td>{metric['opf_detected_spans']}</td>"
            "</tr>"
        )
    field_rows = []
    for item in report["field_evidence"]:
        decision_class = "drop" if item["decision"] == "drop_candidate" else "keep"
        field_rows.append(
            "<tr>"
            f"<th><code>{html.escape(str(item['field']))}</code></th>"
            f"<td>{html.escape(str(item['privacy_cost']))}</td>"
            f"<td><span class=\"pill {decision_class}\">{html.escape(str(item['decision']))}</span></td>"
            f"<td>{item['decision_changes']}</td>"
            f"<td>{item['improvements']}</td>"
            f"<td>{item['regressions']}</td>"
            f"<td>{_percent(item['accuracy_without_field'])}</td>"
            f"<td>{item['tokens_saved_if_dropped']}</td>"
            f"<td>{html.escape(str(item['review_reason']))}</td>"
            "</tr>"
        )
    run = report["run"]
    opf = report["opf"]
    metadata = "".join(
        f"<dt>{html.escape(label)}</dt><dd><code>{html.escape(str(value))}</code></dd>"
        for label, value in [
            ("Task model", run["task_model"]),
            ("Predictor", run["predictor"]),
            ("Predictor evidence", run["predictor_evidence_level"]),
            ("OPF model", opf["model_id"]),
            ("OPF revision", opf["resolved_revision"]),
            ("OPF evidence", opf["evidence_level"]),
            ("Corpus SHA-256", run["corpus_sha256"]),
            ("Schema SHA-256", run["schema_sha256"]),
            ("Prompt contract SHA-256", run["prompt_contract_sha256"]),
        ]
    )
    full_fields = ", ".join(report["field_flow"]["full_context_fields"])
    minimum_fields = ", ".join(report["field_flow"]["minimum_context_fields"]) or "No fields auto-approved"
    field_flow = (
        '<div class="flow-card"><span>Full context</span>'
        f"<code>{html.escape(full_fields)}</code></div>"
        '<div class="arrow">→ OPF + necessity →</div>'
        '<div class="flow-card safe"><span>Minimum + OPF</span>'
        f"<code>{html.escape(minimum_fields)}</code></div>"
        '<p class="flow-note">Field names only. Raw values are not embedded in this report.</p>'
    )
    limitations = "".join(
        f"<li>{html.escape(str(item))}</li>" for item in report["limitations"]
    )
    report_json = json.dumps(report, ensure_ascii=False, indent=2).replace("</", "<\\/")
    replacements = {
        "{{PURPOSE}}": html.escape(str(report["purpose"])),
        "{{STATUS}}": html.escape(str(report["status"])),
        "{{STATUS_CLASS}}": status_class,
        "{{SUMMARY_CARDS}}": summary_cards,
        "{{VARIANT_ROWS}}": "".join(variant_rows),
        "{{FIELD_ROWS}}": "".join(field_rows),
        "{{METADATA}}": metadata,
        "{{FIELD_FLOW}}": field_flow,
        "{{CHART}}": render_svg(report),
        "{{LIMITATIONS}}": limitations,
        "{{REPORT_JSON}}": report_json,
    }
    rendered = template
    for marker, value in replacements.items():
        rendered = rendered.replace(marker, value)
    return rendered


def write_artifacts(report: Mapping[str, Any], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    artifacts = [
        ("opf_necessity_certificate.json", json.dumps(report, indent=2, ensure_ascii=False) + "\n"),
        ("opf_necessity_certificate.md", render_markdown(report)),
        ("opf_necessity_certificate.html", render_html(report)),
        ("field_decisions.csv", render_csv(report)),
        ("minimized_schema.sql", render_sql(report)),
        ("benchmark_chart.svg", render_svg(report)),
    ]
    paths: list[Path] = []
    for name, content in artifacts:
        path = out_dir / name
        path.write_text(content, encoding="utf-8")
        paths.append(path)
    return paths


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read valid JSON from {path}: {exc}") from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--purpose", required=True)
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--label-field", required=True)
    parser.add_argument(
        "--label-values",
        help="Comma-separated labels. Defaults to first-seen order in the dataset.",
    )
    parser.add_argument("--privacy-cost-overrides", type=Path)
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--engine", choices=("openai", "offline"), default="openai")
    parser.add_argument("--opf-revision")
    parser.add_argument("--out-dir", type=Path, default=Path("out/opf-certificate"))
    args = parser.parse_args(argv)

    try:
        schema_sql = args.schema.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Could not read schema from {args.schema}: {exc}") from exc
    records = _load_json(args.data)
    if not isinstance(records, list):
        raise ValueError("Dataset must be a JSON array")
    label_values = (
        tuple(value.strip() for value in args.label_values.split(",") if value.strip())
        if args.label_values
        else infer_label_values(records, args.label_field)
    )
    overrides = _load_json(args.privacy_cost_overrides) if args.privacy_cost_overrides else {}
    if not isinstance(overrides, dict):
        raise ValueError("Privacy-cost overrides must be a JSON object")
    config = CertificateConfig(
        purpose=args.purpose,
        label_field=args.label_field,
        label_values=label_values,
        task_model=args.model,
        engine=args.engine,
        privacy_cost_overrides=overrides,
    )
    predictor = create_predictor(config)
    masker = OpenAIPrivacyFilterMasker(revision=args.opf_revision)
    report = run_certificate(config, schema_sql, records, predictor, masker)
    paths = write_artifacts(report, args.out_dir)
    for path in paths:
        print(path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
