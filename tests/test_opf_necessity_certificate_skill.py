"""Behavior tests for the OPF Necessity Certificate orchestration skill."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = (
    Path(__file__).parents[1]
    / "skills"
    / "opf-necessity-certificate"
    / "scripts"
    / "opf_necessity_certificate.py"
)
SPEC = importlib.util.spec_from_file_location("opf_necessity_certificate_skill", SCRIPT)
assert SPEC and SPEC.loader
certificate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = certificate
SPEC.loader.exec_module(certificate)


SCHEMA = """CREATE TABLE tickets (
    id TEXT PRIMARY KEY,
    signal TEXT,
    notes TEXT,
    email TEXT,
    label TEXT
);"""

RECORDS = [
    {
        "id": "1",
        "signal": "billing invoice",
        "notes": "standard",
        "email": "alice@example.com",
        "label": "billing",
    },
    {
        "id": "2",
        "signal": "login password",
        "notes": "standard",
        "email": "bob@example.com",
        "label": "security",
    },
]


class DeterministicPredictor:
    name = "deterministic_test_predictor"
    evidence_level = "technical_test_fixture"

    def predict(self, payload, config):
        signal = str(payload.get("signal", ""))
        prediction = "security" if "password" in signal else "billing"
        return certificate.Decision(
            prediction=prediction,
            input_tokens=10 + (5 * len(payload)),
            token_source="test_counter",
        )


class DeterministicMasker:
    model_id = "openai/privacy-filter"
    requested_revision = "fixture-revision"
    resolved_revision = "fixture-revision"
    evidence_level = "technical_test_fixture"
    runtime = {"transformers": "test", "torch": "test"}

    def mask_record(self, record):
        masked = dict(record)
        spans = []
        if "email" in masked:
            masked["email"] = "[MASKED:EMAIL]"
            spans.append({"field": "email", "label": "EMAIL", "score": 1.0})
        return certificate.MaskingResult(record=masked, spans=spans)


class EmailDependentPredictor(DeterministicPredictor):
    def predict(self, payload, config):
        prediction = "security" if str(payload.get("email", "")).startswith("bob") else "billing"
        return certificate.Decision(prediction, 10 + (5 * len(payload)), "test_counter")


class RealEmailDependentPredictor(EmailDependentPredictor):
    name = "real_test_predictor"
    evidence_level = "real_model_run"


class LeakyActualMasker(DeterministicMasker):
    evidence_level = "actual_opf_model"
    resolved_revision = "resolved-commit"

    def mask_record(self, record):
        return certificate.MaskingResult(record=dict(record), spans=[])


class OrchestrationTests(unittest.TestCase):
    def config(self):
        return certificate.CertificateConfig(
            purpose="route a support request",
            label_field="label",
            label_values=("billing", "security"),
            task_model="test-model",
            engine="offline",
        )

    def report(self):
        return certificate.run_certificate(
            config=self.config(),
            schema_sql=SCHEMA,
            records=RECORDS,
            predictor=DeterministicPredictor(),
            masker=DeterministicMasker(),
        )

    def test_field_ablation_and_four_variants_are_problem_specific(self):
        report = certificate.run_certificate(
            config=self.config(),
            schema_sql=SCHEMA,
            records=RECORDS,
            predictor=DeterministicPredictor(),
            masker=DeterministicMasker(),
        )

        decisions = {item["field"]: item for item in report["field_evidence"]}
        self.assertEqual(decisions["signal"]["decision"], "retained_pending_review")
        self.assertEqual(decisions["signal"]["decision_changes"], 1)
        self.assertEqual(decisions["notes"]["decision"], "drop_candidate")
        self.assertEqual(decisions["email"]["decision"], "drop_candidate")
        self.assertEqual(report["minimum_fields"], ["signal"])
        self.assertEqual(
            list(report["benchmark"]["variants"]),
            [
                "full_context",
                "opf_only",
                "minimum_context",
                "minimum_plus_opf",
            ],
        )
        self.assertEqual(report["purpose"], "route a support request")
        self.assertEqual(report["opf"]["detected_spans_full_context"], 2)
        self.assertEqual(report["status"], "review_required")
        self.assertIn(
            "technical test masker",
            report["benchmark"]["variant_definitions"]["opf_only"],
        )

    def test_serialized_evidence_never_contains_raw_record_values(self):
        report = self.report()

        serialized = json.dumps(report)
        self.assertNotIn("alice@example.com", serialized)
        self.assertNotIn("billing invoice", serialized)
        self.assertIn("email", serialized)
        self.assertIn("corpus_sha256", serialized)

    def test_empty_dataset_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "non-empty"):
            certificate.run_certificate(
                config=self.config(),
                schema_sql=SCHEMA,
                records=[],
                predictor=DeterministicPredictor(),
                masker=DeterministicMasker(),
            )

    def test_missing_label_is_rejected(self):
        bad_records = [{"id": "1", "signal": "billing invoice"}]

        with self.assertRaisesRegex(ValueError, "label"):
            certificate.run_certificate(
                config=self.config(),
                schema_sql=SCHEMA,
                records=bad_records,
                predictor=DeterministicPredictor(),
                masker=DeterministicMasker(),
            )

    def test_opf_loader_fails_instead_of_substituting_a_masker(self):
        def unavailable_pipeline(**kwargs):
            raise OSError("model unavailable")

        with self.assertRaisesRegex(RuntimeError, "openai/privacy-filter"):
            certificate.OpenAIPrivacyFilterMasker(
                pipeline_factory=unavailable_pipeline,
            )

    def test_opf_adapter_masks_only_the_offsets_returned_by_the_model(self):
        calls = []

        class Config:
            _commit_hash = "resolved-commit"

        class Model:
            config = Config()

        class Pipeline:
            model = Model()

            def __call__(self, text, aggregation_strategy):
                self.aggregation_strategy = aggregation_strategy
                return [
                    {
                        "start": 0,
                        "end": 5,
                        "entity_group": "PRIVATE_PERSON",
                        "score": 0.99,
                    }
                ]

        def pipeline_factory(**kwargs):
            calls.append(kwargs)
            return Pipeline()

        masker = certificate.OpenAIPrivacyFilterMasker(
            revision="requested-commit",
            pipeline_factory=pipeline_factory,
        )
        result = masker.mask_record({"message": "Alice called"})

        self.assertEqual(calls[0]["model"], "openai/privacy-filter")
        self.assertEqual(calls[0]["revision"], "requested-commit")
        self.assertEqual(result.record["message"], "[MASKED:PRIVATE_PERSON] called")
        self.assertEqual(result.spans[0]["field"], "message")
        self.assertNotIn("Alice", json.dumps(result.spans))
        self.assertEqual(masker.resolved_revision, "resolved-commit")

    def test_label_values_can_be_inferred_without_copying_record_content(self):
        labels = certificate.infer_label_values(RECORDS, "label")

        self.assertEqual(labels, ("billing", "security"))

    def test_openai_predictor_requires_an_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"):
                certificate.create_predictor(self.config(), engine="openai")

    def test_invalid_privacy_override_is_rejected(self):
        config = certificate.CertificateConfig(
            purpose="route a support request",
            label_field="label",
            label_values=("billing", "security"),
            engine="offline",
            privacy_cost_overrides={"email": "definitely private"},
        )

        with self.assertRaisesRegex(ValueError, "Invalid privacy-cost"):
            certificate.run_certificate(
                config=config,
                schema_sql=SCHEMA,
                records=RECORDS,
                predictor=DeterministicPredictor(),
                masker=DeterministicMasker(),
            )

    def test_sql_blocks_personal_fields_even_when_ablation_retains_them(self):
        report = certificate.run_certificate(
            config=self.config(),
            schema_sql=SCHEMA,
            records=RECORDS,
            predictor=EmailDependentPredictor(),
            masker=DeterministicMasker(),
        )

        sql = certificate.render_sql(report)
        select_block = sql.split("FROM", 1)[0]

        self.assertIn("BLOCKED pending OPF transform: email", sql)
        self.assertNotIn("    email\n", select_block)

    def test_auto_acceptance_rejects_known_personal_fields_left_unmasked(self):
        report = certificate.run_certificate(
            config=self.config(),
            schema_sql=SCHEMA,
            records=RECORDS,
            predictor=RealEmailDependentPredictor(),
            masker=LeakyActualMasker(),
        )

        combined = report["benchmark"]["variants"]["minimum_plus_opf"]
        self.assertEqual(combined["decision_changes_vs_full"], 0)
        self.assertEqual(combined["residual_personal_fields"], 2)
        self.assertEqual(report["status"], "review_required")

    def test_html_displays_problem_specific_benchmark_and_provenance(self):
        html = certificate.render_html(self.report())

        self.assertIn("route a support request", html)
        self.assertIn("Full context", html)
        self.assertIn("OPF only", html)
        self.assertIn("Minimum context", html)
        self.assertIn("Minimum + OPF", html)
        self.assertIn("40.0%", html)
        self.assertIn("fixture-revision", html)
        self.assertIn("review_required", html)
        self.assertIn("corpus_sha256", html)
        self.assertIn('id="report-data"', html)
        self.assertNotIn("alice@example.com", html)

    def test_html_escapes_declared_purpose_in_markup_and_embedded_json(self):
        unsafe_config = certificate.CertificateConfig(
            purpose="route </script><img src=x onerror=alert(1)>",
            label_field="label",
            label_values=("billing", "security"),
            task_model="test-model",
            engine="offline",
        )
        report = certificate.run_certificate(
            config=unsafe_config,
            schema_sql=SCHEMA,
            records=RECORDS,
            predictor=DeterministicPredictor(),
            masker=DeterministicMasker(),
        )

        html = certificate.render_html(report)

        self.assertNotIn("</script><img", html)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", html)
        self.assertIn("<\\/script>", html)

    def test_write_artifacts_emits_one_consistent_evidence_package(self):
        with tempfile.TemporaryDirectory() as directory:
            out_dir = Path(directory)
            paths = certificate.write_artifacts(self.report(), out_dir)

            self.assertEqual(
                {path.name for path in paths},
                {
                    "opf_necessity_certificate.json",
                    "opf_necessity_certificate.md",
                    "opf_necessity_certificate.html",
                    "field_decisions.csv",
                    "minimized_schema.sql",
                    "benchmark_chart.svg",
                },
            )
            for path in paths:
                self.assertTrue(path.is_file())
                self.assertNotIn("alice@example.com", path.read_text(encoding="utf-8"))

            self.assertIn(
                "CREATE VIEW tickets_ai_view",
                (out_dir / "minimized_schema.sql").read_text(encoding="utf-8"),
            )
            self.assertTrue(
                (out_dir / "benchmark_chart.svg")
                .read_text(encoding="utf-8")
                .startswith("<svg")
            )


if __name__ == "__main__":
    unittest.main()
