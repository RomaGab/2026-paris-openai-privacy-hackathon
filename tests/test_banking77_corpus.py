import sys
import json
import tempfile
import unittest
from pathlib import Path


POC_DIR = Path(__file__).resolve().parents[1] / "poc"
sys.path.insert(0, str(POC_DIR))

from banking77_corpus import (
    BANKING77_LICENSE,
    BANKING77_SOURCE_URL,
    build_benchmark_records,
    prepare_corpus,
    select_balanced_subset,
)


ROWS = [
    {"text": "card example three", "category": "card_arrival"},
    {"text": "refund example two", "category": "request_refund"},
    {"text": "card example one", "category": "card_arrival"},
    {"text": "refund example one", "category": "request_refund"},
    {"text": "card example two", "category": "card_arrival"},
    {"text": "refund example three", "category": "request_refund"},
]


class Banking77CorpusTests(unittest.TestCase):
    def test_selection_is_balanced_and_independent_of_source_order(self):
        intents = ("card_arrival", "request_refund")

        selected = select_balanced_subset(ROWS, intents, per_intent=2, seed="demo")
        reversed_selected = select_balanced_subset(
            list(reversed(ROWS)),
            intents,
            per_intent=2,
            seed="demo",
        )

        self.assertEqual(selected, reversed_selected)
        self.assertEqual(len(selected), 4)
        self.assertEqual(
            [row["category"] for row in selected],
            ["card_arrival", "card_arrival", "request_refund", "request_refund"],
        )

    def test_selection_rejects_an_incomplete_intent(self):
        with self.assertRaisesRegex(ValueError, "request_refund.*3.*available"):
            select_balanced_subset(
                ROWS,
                ("request_refund",),
                per_intent=4,
                seed="demo",
            )

    def test_records_preserve_public_labels_and_add_only_synthetic_identity(self):
        records = build_benchmark_records(
            [{"text": "Where is my card?", "category": "card_arrival"}]
        )

        self.assertEqual(
            records,
            [
                {
                    "id": "B77-0001",
                    "issue_description": "Where is my card?",
                    "product_area": "retail_banking",
                    "urgency": "standard",
                    "name": "Synthetic Person 0001",
                    "email": "synthetic.person.0001@example.com",
                    "phone": "+1 202-555-0101",
                    "date_of_birth": "1980-01-01",
                    "address": "101 Example Street, Test City",
                    "account_id": "SYNTHETIC-ACCOUNT-0001",
                    "expected_queue": "card_arrival",
                }
            ],
        )

    def test_preparation_writes_records_and_auditable_source_metadata(self):
        source_text = (
            "text,category\n"
            "one,card_arrival\n"
            "two,request_refund\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "test.csv"
            output_path = temp_path / "subset.json"
            metadata_path = temp_path / "subset.meta.json"
            source_path.write_text(source_text, encoding="utf-8")

            prepare_corpus(
                source_path,
                output_path,
                metadata_path,
                intents=("card_arrival", "request_refund"),
                per_intent=1,
                seed="fixture-seed",
            )

            records = json.loads(output_path.read_text(encoding="utf-8"))
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

        self.assertEqual(len(records), 2)
        self.assertEqual(
            [record["expected_queue"] for record in records],
            ["card_arrival", "request_refund"],
        )
        self.assertEqual(metadata["dataset"], "BANKING77")
        self.assertEqual(metadata["source_url"], BANKING77_SOURCE_URL)
        self.assertEqual(metadata["license"], BANKING77_LICENSE)
        self.assertEqual(
            metadata.get("license_url"),
            "https://creativecommons.org/licenses/by/4.0/",
        )
        self.assertIn("Casanueva", metadata.get("citation", ""))
        self.assertEqual(metadata["source_split"], "test")
        self.assertEqual(metadata["selection_seed"], "fixture-seed")
        self.assertEqual(metadata["selected_examples"], 2)
        self.assertTrue(metadata["synthetic_identity_overlay"])
        self.assertEqual(
            metadata["source_sha256"],
            "5751be77f1951a760a3669120751b6dadb020ea5a5a85a0d1251c9a2371ac404",
        )


if __name__ == "__main__":
    unittest.main()
