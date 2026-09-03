"""Necessity Certificate: generic task-specific data minimization.

Generalizes poc/minimize.py + poc/sql_minimize.py from the fixed ticket-
routing demo to an arbitrary declared purpose, SQL schema, and labeled
dataset. See ../SKILL.md for the full workflow this script automates.

Given a declared purpose, a SQL schema (one CREATE TABLE), and a labeled
JSON dataset, this script:

  1. Runs the declared task on the complete record for every row (baseline).
  2. Removes each input column one at a time and reruns the identical task
     on every row (ablation).
  3. Measures whether the row's expected label changes when that column is
     removed, across the whole declared test set.
  4. Classifies every column's privacy cost (task-relevant / quasi-identifier
     / direct identifier / sensitive numeric) via a name-based heuristic,
     overridable per column.
  5. Emits, per column, an evidence card recording the counterfactual test,
     the observed effect, and the resulting operational action (block /
     retain / retain-pending-transform).
  6. Emits a minimized AI-facing SQL view (only columns proven necessary
     AND already safe to expose) and a secure base-table DDL (blocked-but-
     operationally-needed PII columns encrypted/generalized, never plain).
  7. Emits a self-contained HTML certificate for immediate inspection in
     Codex, populated from the same report as the JSON and Markdown outputs.

Usage:
    python necessity_certificate.py \\
        --purpose "route a support ticket to the right queue" \\
        --schema path/to/schema.sql \\
        --data path/to/records.json \\
        --label-field expected_queue \\
        --label-values billing,account_security,shipping_logistics,technical_support,general_inquiry \\
        --out-dir out/

Set OPENAI_API_KEY to run the real counterfactual test through an LLM.
Without it, the script falls back to a majority-class baseline -- a dry
run of the pipeline's plumbing only, NOT genuine necessity evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 1. Column privacy-cost classification (heuristic, override-able)
# ---------------------------------------------------------------------------

_DIRECT_ID_PATTERNS = re.compile(
    r"(name|e_?mail|phone|mobile|ssn|social_security|passport|"
    r"address|street|iban|account_(id|number)|customer_id|user_id|"
    r"card_number|credit_card|licen[cs]e|national_id)",
    re.IGNORECASE,
)
_QUASI_ID_PATTERNS = re.compile(
    r"(date_of_birth|dob|birth|zip|postal|gender|nationality|city|region|"
    r"ip_address|device_id|^age$|_age$)",
    re.IGNORECASE,
)
_SENSITIVE_NUMERIC_PATTERNS = re.compile(
    r"(salary|income|balance|credit_score|health|diagnosis|amount_owed)",
    re.IGNORECASE,
)

# task-relevant, not personal -> passes through unchanged if proven necessary
# quasi-identifier            -> must be generalized (e.g. DOB -> age band)
# direct identifier           -> must be pseudonymized (HMAC token) or encrypted at rest
# sensitive numeric           -> must get calibrated Laplace (DP) noise
DP_TRANSFORM_BY_PRIVACY_COST = {
    "task-relevant, not personal": "none",
    "quasi-identifier": "generalize",
    "direct identifier": "pseudonymize",
    "sensitive numeric": "dp_noise",
}
STORAGE_TRANSFORM_BY_PRIVACY_COST = {
    "task-relevant, not personal": "none",
    "quasi-identifier": "generalize",
    "direct identifier": "encrypt",
    "sensitive numeric": "encrypt",
}


def classify_privacy_cost(column: str, overrides: Dict[str, str]) -> str:
    if column in overrides:
        return overrides[column]
    if _DIRECT_ID_PATTERNS.search(column):
        return "direct identifier"
    if _QUASI_ID_PATTERNS.search(column):
        return "quasi-identifier"
    if _SENSITIVE_NUMERIC_PATTERNS.search(column):
        return "sensitive numeric"
    return "task-relevant, not personal"


# ---------------------------------------------------------------------------
# 2. Schema parsing
# ---------------------------------------------------------------------------

def parse_schema(ddl: str) -> Tuple[str, str, List[str]]:
    """Return (table_name, primary_key_column, all_column_names)."""
    ddl_no_comments = "\n".join(
        line for line in ddl.splitlines() if not line.strip().startswith("--")
    )
    match = re.search(r"CREATE\s+TABLE\s+(\w+)\s*\((.*)\)\s*;?\s*$", ddl_no_comments, re.DOTALL)
    if not match:
        raise ValueError("Expected exactly one CREATE TABLE statement in --schema")
    table_name, body = match.group(1), match.group(2)
    columns = []
    for line in body.splitlines():
        line = line.strip().rstrip(",")
        if not line or line.upper().startswith(("PRIMARY KEY", "FOREIGN KEY", "UNIQUE", "CHECK")):
            continue
        columns.append(line.split()[0])
    if not columns:
        raise ValueError("No columns found in the CREATE TABLE statement")
    return table_name, columns[0], columns


# ---------------------------------------------------------------------------
# 3. The declared task (LLM-backed, with an explicit offline fallback)
# ---------------------------------------------------------------------------

def build_prompt(purpose: str, label_field: str, label_values: Optional[List[str]], record: Dict) -> str:
    present_fields = "\n".join(f"- {k}: {v}" for k, v in record.items() if v is not None)
    constraint = (
        f"Reply with exactly one value from this list: {', '.join(label_values)}. "
        "Reply with the value only, nothing else."
        if label_values
        else f"Reply with your decision for '{label_field}' only, nothing else."
    )
    return (
        f"You must decide '{label_field}' for the following declared purpose: {purpose}.\n"
        f"{constraint}\n\nFields:\n{present_fields}"
    )


def run_task_llm(purpose, label_field, label_values, record, model) -> str:
    from openai import OpenAI  # imported lazily so the offline path has no hard dependency

    client = OpenAI()
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": build_prompt(purpose, label_field, label_values, record)}],
        temperature=0,
    )
    text = (response.choices[0].message.content or "").strip()
    if label_values:
        for value in label_values:
            if value.lower() in text.lower():
                return value
    return text


def count_tokens(text: str, model: str) -> int:
    try:
        import tiktoken

        try:
            encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except ImportError:
        return len(text.split())


# ---------------------------------------------------------------------------
# 4. Baseline + per-field ablation
# ---------------------------------------------------------------------------

def payload(record: Dict, input_fields: List[str], drop_field: Optional[str] = None) -> Dict:
    return {k: record.get(k) for k in input_fields if k != drop_field}


def run_pass(records, input_fields, purpose, label_field, label_values, model, use_openai,
             majority_label, drop_field=None):
    predictions, tokens_sent = [], 0
    for record in records:
        p = payload(record, input_fields, drop_field)
        if use_openai:
            prediction = run_task_llm(purpose, label_field, label_values, p, model)
        else:
            # Offline dry run: always predicts the majority class, so it can
            # only ever show "no field changes the decision". Good for
            # exercising the pipeline's plumbing, not for real evidence.
            prediction = majority_label
        predictions.append(prediction)
        tokens_sent += count_tokens(json.dumps(p, default=str), model)
    return predictions, tokens_sent


def accuracy(predictions: List[str], records: List[Dict], label_field: str) -> float:
    correct = sum(p == r.get(label_field) for p, r in zip(predictions, records))
    return correct / len(records) if records else 0.0


def build_report(purpose: str, table_name: str, input_fields: List[str], records: List[Dict],
                  label_field: str, label_values: Optional[List[str]], privacy_cost_overrides: Dict[str, str],
                  model: str, use_openai: bool, verbose: bool = False) -> Dict:
    n = len(records)
    labels = [r.get(label_field) for r in records if r.get(label_field) is not None]
    majority_label = Counter(labels).most_common(1)[0][0] if labels else None

    baseline_predictions, baseline_tokens = run_pass(
        records, input_fields, purpose, label_field, label_values, model, use_openai, majority_label
    )
    baseline_accuracy = accuracy(baseline_predictions, records, label_field)

    if verbose:
        engine = f"OpenAI ({model})" if use_openai else "offline majority-class baseline (dry run only)"
        print(f"Engine: {engine}")
        print(f"Declared purpose: {purpose}")
        print(f"Declared test set: {n} labeled records")
        print(f"Baseline exact-match accuracy: {baseline_accuracy:.0%}")
        print(f"Baseline tokens sent (full record, all records): {baseline_tokens}\n")

    evidence_cards = []
    fields_retained = []
    for field in input_fields:
        privacy_cost = classify_privacy_cost(field, privacy_cost_overrides)
        ablated_predictions, ablated_tokens = run_pass(
            records, input_fields, purpose, label_field, label_values, model, use_openai,
            majority_label, drop_field=field
        )
        ablated_accuracy = accuracy(ablated_predictions, records, label_field)
        changed = sum(b != a for b, a in zip(baseline_predictions, ablated_predictions))
        degrades = ablated_accuracy < baseline_accuracy
        if degrades:
            fields_retained.append(field)
            transform = DP_TRANSFORM_BY_PRIVACY_COST[privacy_cost]
            action = "retain: required for task outcome" if transform == "none" else (
                f"retain, but must be '{transform}'-transformed before it may reach the AI view"
            )
        else:
            action = "block before the model call"

        card = {
            "field": field,
            "declared_purpose": purpose,
            "privacy_cost": privacy_cost,
            "counterfactual_test": f"removed in {n} declared records",
            "observed_effect": f"{changed} decisions changed",
            "accuracy_with_field": f"{baseline_accuracy:.0%}",
            "accuracy_without_field": f"{ablated_accuracy:.0%}",
            "tokens_saved_per_pass": baseline_tokens - ablated_tokens,
            "operational_action": action,
        }
        evidence_cards.append(card)

        if verbose:
            print(f"Field: {field}")
            print(f"  Privacy cost: {privacy_cost}")
            print(f"  Counterfactual test: {card['counterfactual_test']}")
            print(f"  Observed effect: {card['observed_effect']} "
                  f"(accuracy {card['accuracy_with_field']} -> {card['accuracy_without_field']})")
            print(f"  Operational action: {action}\n")

    fields_blocked = [f for f in input_fields if f not in fields_retained]
    example = records[0] if records else {}
    full_payload = payload(example, input_fields)
    minimized_payload = {
        k: v for k, v in full_payload.items()
        if k in fields_retained and DP_TRANSFORM_BY_PRIVACY_COST[classify_privacy_cost(k, privacy_cost_overrides)] == "none"
    }

    return {
        "purpose": purpose,
        "table_name": table_name,
        "engine": ("openai:" + model) if use_openai else "offline_majority_class_baseline (dry run only)",
        "test_set_size": n,
        "baseline_accuracy": baseline_accuracy,
        "baseline_tokens_total": baseline_tokens,
        "evidence_cards": evidence_cards,
        "fields_retained": fields_retained,
        "fields_blocked": fields_blocked,
        "example_before_after": {
            "full_payload": full_payload,
            "minimized_payload": minimized_payload,
        },
    }


# ---------------------------------------------------------------------------
# 5. Minimized SQL artifacts
# ---------------------------------------------------------------------------

def ai_view_sql(table_name: str, pk_column: str, all_columns: List[str], fields_retained: List[str],
                 privacy_cost_overrides: Dict[str, str]) -> str:
    lines = []
    for col in all_columns:
        if col == pk_column or col not in fields_retained:
            continue
        privacy_cost = classify_privacy_cost(col, privacy_cost_overrides)
        transform = DP_TRANSFORM_BY_PRIVACY_COST[privacy_cost]
        if transform == "none":
            lines.append(col)
        else:
            lines.append(
                f"-- BLOCKED: {col} is retained but sensitive ({privacy_cost}); "
                f"requires '{transform}' before AI exposure (not yet implemented, fail-closed)"
            )
    selected_cols = [c for c in lines if not c.startswith("--")]
    header = "\n".join(f"    {c}" for c in lines if c.startswith("--"))
    select_clause = f"    {pk_column}" + (",\n    " + ",\n    ".join(selected_cols) if selected_cols else "")
    return (
        f"-- AI-facing view: only necessity-proven, already-safe-to-expose columns\n"
        f"CREATE VIEW {table_name}_ai_view AS\n"
        f"SELECT\n{select_clause}\nFROM {table_name};\n"
        + (f"{header}\n" if header else "")
    )


def base_table_sql(table_name: str, pk_column: str, all_columns: List[str], fields_retained: List[str],
                    fields_blocked: List[str], privacy_cost_overrides: Dict[str, str],
                    secondary_retention: Dict[str, str]) -> str:
    lines = [
        "-- Base table: PII columns kept only for a secondary, declared",
        "-- operational purpose are stored transformed, never in plaintext.",
        f"CREATE TABLE {table_name}_secure (",
        f"    {pk_column} TEXT PRIMARY KEY,",
    ]
    body_lines = []
    for col in all_columns:
        if col == pk_column:
            continue
        privacy_cost = classify_privacy_cost(col, privacy_cost_overrides)
        transform = STORAGE_TRANSFORM_BY_PRIVACY_COST[privacy_cost]

        if col in fields_retained and transform == "none":
            body_lines.append(f"    {col} TEXT, -- plaintext: task-relevant, not personal, proven necessary")
        elif col in secondary_retention:
            purpose = secondary_retention[col]
            if transform == "encrypt":
                body_lines.append(f"    {col}_enc BYTEA, -- pgp_sym_encrypt({col}, :encryption_key); kept for {purpose}")
            elif transform == "generalize":
                body_lines.append(f"    {col}_generalized TEXT, -- generalized from {col}; kept for {purpose}")
            else:
                body_lines.append(f"    {col}_dp TEXT, -- DP-noised from {col}; kept for {purpose}")
        elif col in fields_retained:
            # proven necessary for the AI task, but not yet safe to expose --
            # still stored transformed, pending the manual anonymization step.
            body_lines.append(f"    {col}_enc BYTEA, -- pgp_sym_encrypt({col}, :encryption_key); "
                               f"proven necessary, pending '{transform}' before AI exposure")
        elif col in fields_blocked:
            body_lines.append(f"    -- {col} dropped entirely: no declared purpose (AI or operational) needs it")

    if body_lines:
        for i in range(len(body_lines) - 1, -1, -1):
            if not body_lines[i].strip().startswith("--"):
                body_lines[i] = body_lines[i].replace(", --", " --", 1) if ", --" in body_lines[i] else body_lines[i].rstrip(",")
                break
    lines.extend(body_lines)
    lines.append(");")
    return "\n".join(lines)


def dp_audit(all_columns: List[str], pk_column: str, fields_retained: List[str], fields_blocked: List[str],
             privacy_cost_overrides: Dict[str, str], secondary_retention: Dict[str, str]) -> List[Dict]:
    audit = []
    for col in all_columns:
        if col == pk_column:
            continue
        privacy_cost = classify_privacy_cost(col, privacy_cost_overrides)
        transform = DP_TRANSFORM_BY_PRIVACY_COST[privacy_cost]
        if col in fields_retained:
            necessity = "proven necessary for the declared AI task"
            in_ai_view = transform == "none"
        elif col in secondary_retention:
            necessity = f"not needed by the AI task; retained for {secondary_retention[col]}"
            in_ai_view = False
        elif col in fields_blocked:
            necessity = "not needed by the AI task; no other declared purpose"
            in_ai_view = False
        else:
            necessity = "never covered by the necessity test; fail-closed, treated as unnecessary"
            in_ai_view = False
        audit.append({
            "column": col,
            "privacy_cost": privacy_cost,
            "necessity": necessity,
            "required_transform": transform,
            "in_ai_view": in_ai_view,
        })
    return audit


# ---------------------------------------------------------------------------
# 6. Report rendering
# ---------------------------------------------------------------------------

def render_markdown(report: Dict, audit: List[Dict]) -> str:
    lines = [
        "# Necessity Certificate",
        "",
        f"**Declared purpose:** {report['purpose']}",
        f"**Engine:** {report['engine']}",
        f"**Test set size:** {report['test_set_size']}",
        f"**Baseline accuracy:** {report['baseline_accuracy']:.0%}",
        "",
        "## Evidence cards",
        "",
    ]
    for card in report["evidence_cards"]:
        lines += [
            f"### `{card['field']}`",
            "```text",
            f"Source field: {card['field']}",
            f"Declared purpose: {card['declared_purpose']}",
            f"Privacy cost: {card['privacy_cost']}",
            f"Counterfactual test: {card['counterfactual_test']}",
            f"Observed effect: {card['observed_effect']} "
            f"(accuracy {card['accuracy_with_field']} -> {card['accuracy_without_field']})",
            f"Tokens saved per pass if blocked: {card['tokens_saved_per_pass']}",
            f"Operational action: {card['operational_action']}",
            "```",
            "",
        ]
    lines += [
        "## Column disposition (fail-closed by default)",
        "",
        "| column | privacy cost | necessity | required transform | in AI view |",
        "|---|---|---|---|---|",
    ]
    for row in audit:
        lines.append(
            f"| {row['column']} | {row['privacy_cost']} | {row['necessity']} | "
            f"{row['required_transform']} | {row['in_ai_view']} |"
        )
    lines += [
        "",
        f"**Fields retained (proven necessary):** {report['fields_retained']}",
        f"**Fields blocked before the model call:** {report['fields_blocked']}",
        "",
        "## Limits",
        "",
        "This is empirical evidence for the declared purpose, model, prompt, and test set shown "
        "above -- not a universal legal or mathematical proof. A different task, prompt, model "
        "version, or field interaction can change the result. Treat this as input to a DPIA or "
        "engineering review, not a legal verdict.",
    ]
    return "\n".join(lines)


def render_html(report: Dict, template_path: Path) -> str:
    """Embed a report in the Codex-style HTML template as standalone JSON."""
    html = template_path.read_text(encoding="utf-8")
    marker = re.compile(
        r'(<script type="application/json" id="fallback-report">\s*)(.*?)(\s*</script>)',
        re.DOTALL,
    )
    if not marker.search(html):
        raise ValueError(f"HTML template has no fallback-report data block: {template_path}")

    embedded_report = dict(report)
    embedded_report["_standalone"] = True
    # HTML parsers close script elements even when the closing tag occurs in
    # JSON text. Escaping every JSON solidus after '<' keeps values inert while
    # remaining valid JSON for JSON.parse().
    payload_json = json.dumps(embedded_report, indent=2, ensure_ascii=False).replace("</", "<\\/")
    return marker.sub(lambda match: f"{match.group(1)}{payload_json}{match.group(3)}", html, count=1)


def default_html_template_path() -> Path:
    """Return the repository's canonical report template."""
    return Path(__file__).resolve().parents[3] / "poc" / "report.html"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--purpose", required=True, help="Declared purpose of the AI task, in plain language.")
    parser.add_argument("--schema", required=True, help="Path to a SQL file with one CREATE TABLE statement.")
    parser.add_argument("--data", required=True, help="Path to a JSON array of labeled records.")
    parser.add_argument("--label-field", required=True, help="Column holding the expected/ground-truth decision.")
    parser.add_argument("--label-values", default=None,
                         help="Comma-separated allowed decision values, if the task is a classification.")
    parser.add_argument("--privacy-cost-overrides", default=None,
                         help="Path to a JSON file mapping column -> privacy cost category, overriding the heuristic.")
    parser.add_argument("--secondary-retention", default=None,
                         help="Path to a JSON file mapping column -> declared non-AI reason to keep it "
                              "(e.g. 'support agent lookup'). Columns not listed here are dropped entirely "
                              "if blocked from the AI view.")
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--out-dir", default="out")
    parser.add_argument("--html-template", default=None,
                        help="Optional path to the Codex-style HTML template. Defaults to poc/report.html.")
    args = parser.parse_args()

    ddl = Path(args.schema).read_text(encoding="utf-8")
    table_name, pk_column, all_columns = parse_schema(ddl)

    records = json.loads(Path(args.data).read_text(encoding="utf-8"))
    input_fields = [c for c in all_columns if c not in (pk_column, args.label_field)]

    label_values = [v.strip() for v in args.label_values.split(",")] if args.label_values else None
    privacy_cost_overrides = json.loads(Path(args.privacy_cost_overrides).read_text(encoding="utf-8")) \
        if args.privacy_cost_overrides else {}
    secondary_retention = json.loads(Path(args.secondary_retention).read_text(encoding="utf-8")) \
        if args.secondary_retention else {}

    use_openai = bool(os.environ.get("OPENAI_API_KEY"))

    report = build_report(
        purpose=args.purpose,
        table_name=table_name,
        input_fields=input_fields,
        records=records,
        label_field=args.label_field,
        label_values=label_values,
        privacy_cost_overrides=privacy_cost_overrides,
        model=args.model,
        use_openai=use_openai,
        verbose=True,
    )

    audit = dp_audit(all_columns, pk_column, report["fields_retained"], report["fields_blocked"],
                      privacy_cost_overrides, secondary_retention)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "evidence_cards.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    view_sql = ai_view_sql(table_name, pk_column, all_columns, report["fields_retained"], privacy_cost_overrides)
    table_sql = base_table_sql(table_name, pk_column, all_columns, report["fields_retained"],
                                report["fields_blocked"], privacy_cost_overrides, secondary_retention)
    (out_dir / "minimized_schema.sql").write_text(f"{view_sql}\n\n{table_sql}\n", encoding="utf-8")

    (out_dir / "necessity_certificate.md").write_text(render_markdown(report, audit), encoding="utf-8")

    html_template = Path(args.html_template) if args.html_template else default_html_template_path()
    html_path = out_dir / "necessity_certificate.html"
    html_path.write_text(render_html(report, html_template), encoding="utf-8")

    print("=" * 60)
    print(f"Fields blocked before the model call: {report['fields_blocked']}")
    print(f"Fields retained (required for task outcome): {report['fields_retained']}")
    print(f"Artifacts written to {out_dir}/ "
          f"(evidence_cards.json, minimized_schema.sql, necessity_certificate.md, necessity_certificate.html)")
    print(f"Open the visual certificate in Codex: {html_path.resolve()}")


if __name__ == "__main__":
    main()
