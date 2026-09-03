"""Prepare a fixed public BANKING77 subset for the minimization benchmark."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence


BANKING77_SOURCE_URL = (
    "https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/"
    "master/banking_data/test.csv"
)
BANKING77_LICENSE = "CC BY 4.0"
BANKING77_LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
BANKING77_CITATION = (
    "Casanueva, Temcinas, Gerz, Henderson, and Vulic. "
    "Efficient Intent Detection with Dual Sentence Encoders. ACL 2020."
)
BANKING77_SEED = "necessity-certificate-2026-09-03"
BANKING77_INTENTS = (
    "card_arrival",
    "cash_withdrawal_not_recognised",
    "compromised_card",
    "contactless_not_working",
    "declined_transfer",
    "passcode_forgotten",
    "request_refund",
    "transfer_not_received_by_recipient",
    "verify_my_identity",
    "wrong_exchange_rate_for_cash_withdrawal",
)


def _stable_rank(row: Mapping[str, str], seed: str) -> tuple[str, str]:
    text = row["text"]
    category = row["category"]
    digest = hashlib.sha256(
        f"{seed}\0{category}\0{text}".encode("utf-8")
    ).hexdigest()
    return digest, text


def select_balanced_subset(
    rows: Iterable[Mapping[str, str]],
    intents: Sequence[str] = BANKING77_INTENTS,
    per_intent: int = 5,
    seed: str = BANKING77_SEED,
) -> List[Dict[str, str]]:
    """Select a source-order-independent sample for every declared intent."""
    if per_intent < 1:
        raise ValueError("per_intent must be at least 1")

    materialized = [dict(row) for row in rows]
    selected: List[Dict[str, str]] = []
    counts = Counter(row.get("category") for row in materialized)
    for intent in intents:
        available = counts[intent]
        if available < per_intent:
            raise ValueError(
                f"{intent} requires {per_intent} rows but only {available} are available"
            )
        candidates = [
            row for row in materialized if row.get("category") == intent
        ]
        selected.extend(sorted(candidates, key=lambda row: _stable_rank(row, seed))[:per_intent])
    return selected


def build_benchmark_records(
    rows: Iterable[Mapping[str, str]],
) -> List[Dict[str, str]]:
    """Add unmistakably synthetic structured identifiers to public queries."""
    records: List[Dict[str, str]] = []
    for index, row in enumerate(rows, start=1):
        year = 1980 + ((index - 1) % 20)
        month = 1 + ((index - 1) % 12)
        day = 1 + ((index - 1) % 28)
        records.append(
            {
                "id": f"B77-{index:04d}",
                "issue_description": row["text"],
                "product_area": "retail_banking",
                "urgency": "standard",
                "name": f"Synthetic Person {index:04d}",
                "email": f"synthetic.person.{index:04d}@example.com",
                "phone": f"+1 202-555-{100 + index:04d}",
                "date_of_birth": f"{year:04d}-{month:02d}-{day:02d}",
                "address": f"{100 + index} Example Street, Test City",
                "account_id": f"SYNTHETIC-ACCOUNT-{index:04d}",
                "expected_queue": row["category"],
            }
        )
    return records


def prepare_corpus(
    source_path: Path,
    output_path: Path,
    metadata_path: Path,
    intents: Sequence[str] = BANKING77_INTENTS,
    per_intent: int = 5,
    seed: str = BANKING77_SEED,
) -> None:
    source_bytes = source_path.read_bytes()
    with source_path.open(encoding="utf-8", newline="") as source_file:
        rows = list(csv.DictReader(source_file))
    selected = select_balanced_subset(rows, intents, per_intent, seed)
    records = build_benchmark_records(selected)
    metadata = {
        "dataset": "BANKING77",
        "source_url": BANKING77_SOURCE_URL,
        "source_split": "test",
        "license": BANKING77_LICENSE,
        "license_url": BANKING77_LICENSE_URL,
        "citation": BANKING77_CITATION,
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "selection_method": "lowest SHA-256 ranks per intent",
        "selection_seed": seed,
        "selected_intents": list(intents),
        "examples_per_intent": per_intent,
        "selected_examples": len(records),
        "synthetic_identity_overlay": True,
        "ground_truth": "Original BANKING77 intent labels",
    }
    output_path.write_text(
        json.dumps(records, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_csv", type=Path)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).parent / "data" / "banking77_test_subset.json",
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=Path(__file__).parent / "data" / "banking77_test_subset.meta.json",
    )
    args = parser.parse_args()
    prepare_corpus(args.source_csv, args.out, args.metadata)
    print(f"BANKING77 benchmark subset written to {args.out}")
    print(f"Source and selection metadata written to {args.metadata}")


if __name__ == "__main__":
    main()
