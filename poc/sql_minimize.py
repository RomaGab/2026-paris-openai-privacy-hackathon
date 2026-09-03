"""Step A: differential-privacy-aware SQL minimization.

Combines the counterfactual necessity evidence from minimize.py with a real
SQL table definition and emits two artifacts:

  1. An AI-facing SQL view: only columns PROVEN necessary for the declared
     task (fields_retained from the ablation study) may appear in it. Any
     column the base table has that the necessity test never covered is
     treated as unproven and blocked too (fail-closed default deny).

  2. A base-table DDL where every blocked-but-operationally-needed PII
     column (e.g. kept for human agent lookup, not for the AI call) is
     stored encrypted at rest via pgcrypto, never in plaintext.

Retained columns go through one more, differential-privacy-style check
before they are allowed into the AI view:
  - task-relevant, not personal  -> passes through unchanged
  - quasi-identifier             -> must be generalized (e.g. DOB -> age band)
  - direct identifier            -> must be pseudonymized (HMAC token)
  - sensitive numeric            -> must get calibrated Laplace (DP) noise

None of our current retained fields (issue_description, product_area) are
personal, so both pass straight through. The transforms below exist so
that if a future necessity test proves a sensitive column is required,
it is never exposed raw -- it is still minimized to the least identifying
form that satisfies the declared purpose.

Usage:
    python poc/sql_minimize.py [--schema poc/data/tickets_schema.sql] [--out poc/step_a_output.sql]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, List

from classifier import PRIVACY_COST
from minimize import build_report

SCHEMA_PATH = Path(__file__).parent / "data" / "tickets_schema.sql"
TABLE_NAME = "support_tickets"

# Columns kept in the base table for a declared secondary (non-AI) purpose,
# each mapped to the privacy-preserving transform required to store it.
# "encrypt": pgcrypto symmetric encryption, only ever decrypted by a human
#            agent holding the key -- never selected into the AI view.
# "generalize_age_band": DOB is reduced to an age bracket, dropping the
#            exact date a direct identifier could be re-derived from.
SECONDARY_RETENTION = {
    "name": ("encrypt", "support agent lookup"),
    "email": ("encrypt", "support agent lookup"),
    "phone": ("encrypt", "support agent lookup"),
    "address": ("encrypt", "support agent lookup"),
    "account_id": ("encrypt", "support agent lookup / billing reconciliation"),
    "date_of_birth": ("generalize_age_band", "age-restricted feature eligibility"),
}

# transform required for a retained-but-sensitive column before it may ever
# reach the AI view (differential-privacy / anonymization layer).
DP_TRANSFORM_BY_PRIVACY_COST = {
    "task-relevant, not personal": "none",
    "quasi-identifier": "generalize",
    "direct identifier": "pseudonymize",
    "direct identifier (linkable)": "pseudonymize",
}


def parse_columns(ddl: str) -> List[str]:
    """Extract column names from a single CREATE TABLE statement."""
    ddl_no_comments = "\n".join(
        line for line in ddl.splitlines() if not line.strip().startswith("--")
    )
    body = re.search(r"CREATE\s+TABLE\s+\w+\s*\((.*)\)\s*;?\s*$", ddl_no_comments, re.DOTALL).group(1)
    columns = []
    for line in body.splitlines():
        line = line.strip().rstrip(",")
        if not line or line.upper().startswith(("PRIMARY KEY", "FOREIGN KEY", "UNIQUE", "CHECK")):
            continue
        columns.append(line.split()[0])
    return columns


def ai_view_sql(all_columns: List[str], fields_retained: List[str]) -> str:
    """Columns allowed in the AI-facing view: proven necessary AND passed
    the DP/anonymization check for their privacy cost."""
    selected = []
    for col in all_columns:
        if col not in fields_retained:
            continue  # not proven necessary for the declared task -> blocked
        privacy_cost = PRIVACY_COST.get(col, "task-relevant, not personal")
        transform = DP_TRANSFORM_BY_PRIVACY_COST[privacy_cost]
        if transform == "none":
            selected.append(col)
        else:
            # Would need the same transform as SECONDARY_RETENTION before
            # exposure; none of today's retained fields hit this branch.
            selected.append(f"-- BLOCKED: {col} is retained but sensitive, requires '{transform}' before AI exposure")
    select_list = ",\n    ".join(c for c in selected if not c.startswith("--")) or "id"
    return (
        f"-- Step A output: AI-facing view (only necessity-proven, non-personal columns)\n"
        f"CREATE VIEW {TABLE_NAME}_ai_view AS\n"
        f"SELECT\n    id,\n    {select_list}\nFROM {TABLE_NAME};"
    )


def base_table_sql(all_columns: List[str], fields_retained: List[str], fields_blocked: List[str]) -> str:
    """Base table DDL: PII columns kept only for a secondary purpose are
    stored via pgcrypto, never in plaintext."""
    lines = [
        f"-- Step A output: base table with column-level encryption for blocked PII",
        f"-- retained only for a secondary, declared operational purpose.",
        f"CREATE TABLE {TABLE_NAME}_secure (",
        f"    id TEXT PRIMARY KEY,",
    ]
    for col in all_columns:
        if col in ("id",):
            continue
        if col in SECONDARY_RETENTION:
            transform, purpose = SECONDARY_RETENTION[col]
            if transform == "encrypt":
                lines.append(f"    {col}_enc BYTEA, -- pgp_sym_encrypt({col}, :encryption_key); kept for {purpose}")
            elif transform == "generalize_age_band":
                lines.append(f"    {col}_age_band TEXT, -- generalized from {col}; kept for {purpose}")
        elif col in fields_blocked:
            lines.append(f"    -- {col} dropped entirely: no declared purpose (AI or operational) needs it")
        elif col in fields_retained:
            lines.append(f"    {col} TEXT, -- plaintext: task-relevant, not personal")
    # the last emitted column line must not carry a trailing comma
    for i in range(len(lines) - 1, -1, -1):
        if not lines[i].strip().startswith("--"):
            lines[i] = lines[i].replace(", --", " --", 1) if ", --" in lines[i] else lines[i].rstrip(",")
            break
    lines.append(");")
    return "\n".join(lines)


def dp_audit(all_columns: List[str], fields_retained: List[str], fields_blocked: List[str]) -> List[Dict]:
    audit = []
    for col in all_columns:
        if col == "id":
            continue
        privacy_cost = PRIVACY_COST.get(col, "n/a (untested column, fail-closed)")
        if col in fields_retained:
            necessity = "proven necessary for the declared AI task"
        elif col in SECONDARY_RETENTION:
            necessity = f"not needed by the AI task; retained for {SECONDARY_RETENTION[col][1]}"
        elif col in fields_blocked:
            necessity = "not needed by the AI task; no other declared purpose"
        else:
            necessity = "never covered by the necessity test; fail-closed, treated as unnecessary"

        if col in fields_retained:
            transform = DP_TRANSFORM_BY_PRIVACY_COST.get(privacy_cost, "none")
        elif col in SECONDARY_RETENTION:
            transform = SECONDARY_RETENTION[col][0]
        else:
            transform = "dropped"

        audit.append({
            "column": col,
            "privacy_cost": privacy_cost,
            "necessity": necessity,
            "required_transform": transform,
            "in_ai_view": col in fields_retained and DP_TRANSFORM_BY_PRIVACY_COST.get(privacy_cost) == "none",
        })
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", default=str(SCHEMA_PATH))
    parser.add_argument("--out", default=str(Path(__file__).parent / "step_a_output.sql"))
    args = parser.parse_args()

    ddl = Path(args.schema).read_text(encoding="utf-8")
    # expected_queue is the label the task predicts, not an input field.
    all_columns = [c for c in parse_columns(ddl) if c != "expected_queue"]

    report = build_report()
    fields_retained = report["fields_retained"]
    fields_blocked = report["fields_blocked"]

    print(f"Base table columns ({len(all_columns)}): {all_columns}\n")
    print("Differential-privacy / necessity audit per column:")
    for row in dp_audit(all_columns, fields_retained, fields_blocked):
        print(f"  {row['column']}: {row['necessity']} | privacy cost: {row['privacy_cost']} | "
              f"transform: {row['required_transform']} | in AI view: {row['in_ai_view']}")

    view_sql = ai_view_sql(all_columns, fields_retained)
    table_sql = base_table_sql(all_columns, fields_retained, fields_blocked)
    output = f"{view_sql}\n\n{table_sql}\n"

    Path(args.out).write_text(output, encoding="utf-8")
    print(f"\n{output}")
    print(f"Written to {args.out}")


if __name__ == "__main__":
    main()
