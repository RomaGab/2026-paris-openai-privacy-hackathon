import sys
import unittest
from pathlib import Path


POC_DIR = Path(__file__).resolve().parents[1] / "poc"
sys.path.insert(0, str(POC_DIR))

from minimize import recommend_field_action


class DecisionStabilityRuleTests(unittest.TestCase):
    def test_zero_changes_allows_blocking(self):
        self.assertEqual(
            recommend_field_action(0),
            "block before the model call",
        )

    def test_changed_decision_requires_retention_even_when_accuracy_is_flat(self):
        self.assertEqual(
            recommend_field_action(2),
            "retain: changes measured decisions",
        )


if __name__ == "__main__":
    unittest.main()
