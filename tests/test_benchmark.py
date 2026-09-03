import sys
import unittest
from pathlib import Path


POC_DIR = Path(__file__).resolve().parents[1] / "poc"
sys.path.insert(0, str(POC_DIR))

from benchmark import (
    Observation,
    StructuredFieldMasker,
    build_variant_payloads,
    calculate_variant_metrics,
    get_corpus_profile,
    get_default_report_paths,
    render_markdown,
    replace_spans,
    run_benchmark,
)
from classifier import (
    ClassificationResult,
    _build_prompt,
    _extract_label,
    classify_measured,
)


TICKET = {
    "id": "T001",
    "issue_description": "I was charged twice.",
    "product_area": "Billing",
    "urgency": "high",
    "name": "Alice Martin",
    "email": "alice@example.com",
    "phone": "+33 6 12 34 56 78",
    "date_of_birth": "1988-04-12",
    "address": "12 Rue de Rivoli, Paris",
    "account_id": "ACC-10234",
    "expected_queue": "billing",
}


def observation(prediction, expected, tokens, payload, raw_pii):
    return Observation(
        ticket_id="T001",
        prediction=prediction,
        expected=expected,
        input_tokens=tokens,
        token_source="test",
        payload=payload,
        raw_structured_pii_values_sent=raw_pii,
    )


class VariantTests(unittest.TestCase):
    def test_banking77_profile_declares_public_source_and_synthetic_overlay(self):
        profile = get_corpus_profile("banking77")

        self.assertEqual(profile.name, "banking77")
        self.assertEqual(profile.data_path.name, "banking77_test_subset.json")
        self.assertEqual(len(profile.labels), 10)
        self.assertEqual(profile.minimum_fields, ("issue_description",))
        self.assertEqual(profile.license, "CC BY 4.0")
        self.assertTrue(profile.public_source_data)
        self.assertTrue(profile.synthetic_identity_overlay)

    def test_banking77_report_preserves_provenance_and_claim_boundary(self):
        report = run_benchmark(engine="offline", corpus_name="banking77")
        run = report["run"]

        self.assertEqual(run["corpus_name"], "banking77")
        self.assertEqual(run["test_set_size"], 50)
        self.assertTrue(run["public_source_data"])
        self.assertTrue(run["synthetic_identity_overlay"])
        self.assertEqual(run["license"], "CC BY 4.0")
        self.assertIn("PolyAI-LDN", run["source_url"])
        self.assertEqual(len(run["labels"]), 10)
        self.assertTrue(
            all(
                not metric["accepted_without_review"]
                for metric in report["metrics"].values()
            )
        )

        markdown = render_markdown(report)
        self.assertIn("Fixed 50-case subset", markdown)
        self.assertIn("CC BY 4.0", markdown)
        self.assertIn("synthetic structured identity overlay", markdown)
        self.assertIn("not a full BANKING77 benchmark result", markdown)

    def test_public_corpus_uses_separate_default_report_files(self):
        json_path, markdown_path = get_default_report_paths("banking77")

        self.assertEqual(json_path.name, "banking77-benchmark-report.json")
        self.assertEqual(markdown_path.name, "banking77-benchmark-report.md")

    def test_prompt_uses_declared_task_and_labels(self):
        prompt = _build_prompt(
            {"issue_description": "Where is my card?"},
            labels=("card_arrival", "request_refund"),
            task_name="banking support intent classifier",
        )

        self.assertIn("banking support intent classifier", prompt)
        self.assertIn("card_arrival, request_refund", prompt)
        self.assertNotIn("billing, account_security", prompt)

    def test_label_extraction_prefers_a_complete_declared_label(self):
        labels = ("card", "card_arrival", "request_refund")

        self.assertEqual(
            _extract_label("The answer is CARD_ARRIVAL.", labels),
            "card_arrival",
        )
        self.assertIsNone(_extract_label("unknown_intent", labels))

    def test_offline_classifier_reports_prediction_and_token_source(self):
        result = classify_measured(TICKET, use_openai=False)

        self.assertIsInstance(result, ClassificationResult)
        self.assertEqual(result.prediction, "billing")
        self.assertGreater(result.input_tokens, 0)
        self.assertIn(result.token_source, {"tiktoken", "whitespace_estimate"})

    def test_variants_separate_masking_from_minimization(self):
        variants = build_variant_payloads(TICKET, StructuredFieldMasker())

        self.assertEqual(
            list(variants),
            [
                "full_context",
                "masking_only",
                "minimum_context",
                "minimum_plus_masking",
            ],
        )
        self.assertEqual(variants["full_context"]["email"], "alice@example.com")
        self.assertIn("email", variants["masking_only"])
        self.assertEqual(variants["masking_only"]["email"], "[MASKED:email]")
        self.assertNotIn("email", variants["minimum_context"])
        self.assertEqual(
            set(variants["minimum_context"]),
            {"issue_description", "product_area", "urgency"},
        )

    def test_metrics_compare_every_variant_with_full_context(self):
        full_payload = {"issue_description": "x", "email": "a@example.com"}
        minimum_payload = {"issue_description": "x"}
        runs = {
            "full_context": [
                observation("billing", "billing", 60, full_payload, 1),
                observation("technical_support", "technical_support", 40, full_payload, 1),
            ],
            "masking_only": [
                observation("billing", "billing", 55, full_payload, 0),
                observation("technical_support", "technical_support", 35, full_payload, 0),
            ],
            "minimum_context": [
                observation("billing", "billing", 25, minimum_payload, 0),
                observation("technical_support", "technical_support", 15, minimum_payload, 0),
            ],
            "minimum_plus_masking": [
                observation("billing", "billing", 20, minimum_payload, 0),
                observation("general_inquiry", "technical_support", 15, minimum_payload, 0),
            ],
        }

        metrics = calculate_variant_metrics(runs)

        self.assertEqual(metrics["full_context"]["correct"], 2)
        self.assertEqual(metrics["minimum_context"]["accuracy"], 1.0)
        self.assertEqual(metrics["minimum_context"]["decision_changes_vs_full"], 0)
        self.assertEqual(metrics["minimum_context"]["token_reduction_vs_full"], 0.6)
        self.assertEqual(metrics["minimum_context"]["field_reduction_vs_full"], 0.5)
        self.assertEqual(metrics["minimum_context"]["raw_structured_pii_reduction_vs_full"], 1.0)
        self.assertFalse(metrics["minimum_plus_masking"]["accepted_without_review"])

    def test_metrics_separate_improvements_from_regressions(self):
        payload = {"issue_description": "x"}
        full = [
            observation("request_refund", "card_arrival", 20, payload, 0),
            observation("card_arrival", "card_arrival", 20, payload, 0),
        ]
        changed = [
            observation("card_arrival", "card_arrival", 10, payload, 0),
            observation("request_refund", "card_arrival", 10, payload, 0),
        ]
        runs = {
            "full_context": full,
            "masking_only": changed,
            "minimum_context": changed,
            "minimum_plus_masking": changed,
        }

        metrics = calculate_variant_metrics(runs)

        self.assertEqual(metrics["minimum_context"]["improvements_vs_full"], 1)
        self.assertEqual(metrics["minimum_context"]["regressions_vs_full"], 1)
        self.assertEqual(metrics["minimum_context"]["other_changes_vs_full"], 0)

    def test_replace_spans_uses_original_offsets(self):
        text = "Alice sent alice@example.com today"

        masked = replace_spans(
            text,
            [
                {"start": 0, "end": 5, "entity_group": "private_person"},
                {"start": 11, "end": 28, "entity_group": "private_email"},
            ],
        )

        self.assertEqual(
            masked,
            "[MASKED:private_person] sent [MASKED:private_email] today",
        )

    def test_offline_report_is_labelled_and_does_not_claim_opf(self):
        report = {
            "run": {
                "evidence_level": "technical_dry_run",
                "engine": "offline_rule_based",
                "model": None,
                "masker": "structured_field_masking",
                "generated_at": "2026-09-03T12:00:00+00:00",
                "test_set_size": 2,
                "corpus_sha256": "abc",
                "prompt_sha256": "def",
            },
            "metrics": {
                "full_context": {
                    "correct": 2,
                    "total": 2,
                    "accuracy": 1.0,
                    "decision_changes_vs_full": 0,
                    "input_tokens": 100,
                    "token_reduction_vs_full": 0.0,
                    "field_reduction_vs_full": 0.0,
                    "raw_structured_pii_values_sent": 2,
                    "raw_structured_pii_reduction_vs_full": 0.0,
                    "accepted_without_review": True,
                }
            },
            "limitations": ["Synthetic corpus."],
        }

        markdown = render_markdown(report)

        self.assertIn("TECHNICAL DRY RUN", markdown)
        self.assertIn("not an OpenAI Privacy Filter evaluation", markdown)
        self.assertIn("2/2", markdown)


if __name__ == "__main__":
    unittest.main()
