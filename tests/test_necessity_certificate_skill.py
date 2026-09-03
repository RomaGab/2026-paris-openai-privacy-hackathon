"""Regression tests for the reusable Necessity Certificate skill."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


SCRIPT = (
    Path(__file__).parents[1]
    / "skills"
    / "necessity-certificate"
    / "scripts"
    / "necessity_certificate.py"
)
SPEC = importlib.util.spec_from_file_location("necessity_certificate_skill", SCRIPT)
assert SPEC and SPEC.loader
necessity = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(necessity)


def _signal_records():
    return [
        {"id": "1", "signal": "billing invoice", "email": "a@example.com", "label": "billing"},
        {"id": "2", "signal": "billing invoice", "email": "b@example.com", "label": "billing"},
        {"id": "3", "signal": "login password", "email": "c@example.com", "label": "security"},
        {"id": "4", "signal": "login password", "email": "d@example.com", "label": "security"},
    ]


class NecessityCertificateSkillTests(unittest.TestCase):
    def test_offline_engine_measures_repeated_task_signal(self):
        report = necessity.build_report(
            purpose="route a support request",
            table_name="tickets",
            input_fields=["signal", "email"],
            records=_signal_records(),
            label_field="label",
            label_values=["billing", "security"],
            privacy_cost_overrides={},
            model="gpt-4o-mini",
            use_openai=False,
        )

        self.assertEqual(report["baseline_accuracy"], 1.0)
        self.assertEqual(report["fields_retained"], ["signal"])
        self.assertEqual(report["fields_blocked"], ["email"])
        self.assertTrue(report["engine"].startswith("offline_bag_of_words_baseline"))

    def test_any_changed_decision_prevents_automatic_blocking(self):
        records = [
            {"id": "1", "signal": "one", "label": "a"},
            {"id": "2", "signal": "two", "label": "b"},
        ]
        pass_results = [(["a", "a"], 10), (["b", "b"], 8)]

        with patch.object(necessity, "run_pass", side_effect=pass_results):
            report = necessity.build_report(
                purpose="choose a label",
                table_name="items",
                input_fields=["signal"],
                records=records,
                label_field="label",
                label_values=["a", "b"],
                privacy_cost_overrides={},
                model="gpt-4o-mini",
                use_openai=False,
            )

        self.assertEqual(report["baseline_accuracy"], 0.5)
        self.assertEqual(report["evidence_cards"][0]["accuracy_without_field"], "50%")
        self.assertEqual(report["evidence_cards"][0]["observed_effect"], "2 decisions changed")
        self.assertEqual(report["fields_retained"], ["signal"])

    def test_ai_view_never_exposes_untested_primary_key(self):
        sql = necessity.ai_view_sql(
            table_name="tickets",
            pk_column="account_id",
            all_columns=["account_id", "signal", "email"],
            fields_retained=["signal"],
            privacy_cost_overrides={},
        )

        select_block = sql.split("FROM", 1)[0]
        self.assertIn("signal", select_block)
        self.assertNotIn("account_id", select_block)


if __name__ == "__main__":
    unittest.main()
