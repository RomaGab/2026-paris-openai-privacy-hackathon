"""Proof-carrying data minimization: minimum viable demo.

For each field in the declared ticket schema, this script:
  1. Runs the routing task on the complete record (baseline).
  2. Removes that one field and re-runs the identical task (ablation).
  3. Measures whether the expected decision changes on the declared test set.
  4. Emits an evidence card recommending whether the field should be
     blocked before the model call, or retained because removing it
     degrades the measured task outcome.

Usage:
    python poc/minimize.py [--model gpt-4o-mini] [--out poc/report.json]

Set OPENAI_API_KEY to route through the real OpenAI API instead of the
deterministic offline fallback classifier.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Dict, List

from classifier import FIELDS, PRIVACY_COST, classify, count_tokens

DATA_PATH = Path(__file__).parent / "data" / "synthetic_tickets.json"


def load_tickets() -> List[Dict[str, str]]:
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def payload(ticket: Dict[str, str], drop_field: str | None = None) -> Dict[str, str]:
    return {
        k: v for k, v in ticket.items()
        if k in FIELDS and k != drop_field
    }


def run_pass(tickets: List[Dict[str, str]], model: str, use_openai: bool, drop_field: str | None = None):
    predictions, tokens_sent = [], 0
    for ticket in tickets:
        record = payload(ticket, drop_field)
        predictions.append(classify(record, model=model, use_openai=use_openai))
        tokens_sent += count_tokens(json.dumps(record), model=model)
    return predictions, tokens_sent


def accuracy(predictions: List[str], tickets: List[Dict[str, str]]) -> float:
    correct = sum(p == t["expected_queue"] for p, t in zip(predictions, tickets))
    return correct / len(tickets)


def build_report(model: str = "gpt-4o-mini", use_openai: bool | None = None, verbose: bool = False) -> Dict:
    """Run the full baseline + per-field ablation study and return the report dict.

    This is the single source of necessity evidence reused by Step A
    (poc/sql_minimize.py) so that the SQL/encryption decisions are always
    derived from the same counterfactual test, not a second guess.
    """
    if use_openai is None:
        use_openai = bool(os.environ.get("OPENAI_API_KEY"))
    tickets = load_tickets()
    n = len(tickets)

    baseline_predictions, baseline_tokens = run_pass(tickets, model, use_openai)
    baseline_accuracy = accuracy(baseline_predictions, tickets)

    if verbose:
        print(f"Engine: {'OpenAI (' + model + ')' if use_openai else 'offline rule-based fallback'}")
        print(f"Declared test set: {n} synthetic tickets")
        print(f"Baseline exact-match accuracy: {baseline_accuracy:.0%}")
        print(f"Baseline tokens sent (full record, all tickets): {baseline_tokens}\n")

    evidence_cards = []
    retained_fields = []
    for field in FIELDS:
        ablated_predictions, ablated_tokens = run_pass(tickets, model, use_openai, drop_field=field)
        ablated_accuracy = accuracy(ablated_predictions, tickets)
        changed = sum(b != a for b, a in zip(baseline_predictions, ablated_predictions))
        degrades = ablated_accuracy < baseline_accuracy
        action = "retain: required for task outcome" if degrades else "block before the model call"
        if degrades:
            retained_fields.append(field)

        card = {
            "field": field,
            "declared_purpose": "route a support ticket",
            "privacy_cost": PRIVACY_COST[field],
            "counterfactual_test": f"removed in {n} declared synthetic cases",
            "observed_effect": f"{changed} routing decisions changed",
            "accuracy_with_field": f"{baseline_accuracy:.0%}",
            "accuracy_without_field": f"{ablated_accuracy:.0%}",
            "tokens_saved_per_pass": baseline_tokens - ablated_tokens,
            "operational_action": action,
        }
        evidence_cards.append(card)

        if verbose:
            print(f"Field: {field}")
            print(f"  Declared purpose: route a support ticket")
            print(f"  Privacy cost: {card['privacy_cost']}")
            print(f"  Counterfactual test: {card['counterfactual_test']}")
            print(f"  Observed effect: {card['observed_effect']} (accuracy {card['accuracy_with_field']} -> {card['accuracy_without_field']})")
            print(f"  Operational action: {action}\n")

    example = tickets[0]
    full_payload = payload(example)
    minimized_payload = {k: v for k, v in full_payload.items() if k in retained_fields}

    return {
        "engine": "openai:" + model if use_openai else "offline_rule_based",
        "test_set_size": n,
        "baseline_accuracy": baseline_accuracy,
        "baseline_tokens_total": baseline_tokens,
        "evidence_cards": evidence_cards,
        "fields_retained": retained_fields,
        "fields_blocked": [f for f in FIELDS if f not in retained_fields],
        "example_before_after": {
            "ticket_id": example["id"],
            "full_payload": full_payload,
            "minimized_payload": minimized_payload,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--out", default=str(Path(__file__).parent / "report.json"))
    args = parser.parse_args()

    report = build_report(model=args.model, verbose=True)
    out_path = Path(args.out)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=" * 60)
    print(f"Fields blocked before the model call: {report['fields_blocked']}")
    print(f"Fields retained (required for task outcome): {report['fields_retained']}")
    print(f"Full report written to {out_path}")


if __name__ == "__main__":
    main()
